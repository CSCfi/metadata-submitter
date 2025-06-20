"""Handle HTTP methods for server."""

import json
from asyncio import sleep
from collections.abc import AsyncIterator, Iterator
from math import ceil
from typing import Any

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...conf.conf import POLLING_INTERVAL, WORKFLOWS, schema_types
from ...helpers.logger import LOG
from ...helpers.schema_loader import JSONSchemaLoader, SchemaNotFoundException
from ...helpers.validator import JSONValidator
from ...helpers.workflow import Workflow
from ...services.admin_service_handler import AdminServiceHandler
from ...services.datacite_service_handler import DataciteServiceHandler
from ...services.metax_service_handler import MetaxServiceHandler
from ...services.pid_ms_handler import PIDServiceHandler
from ...services.rems_service_handler import RemsServiceHandler
from ..auth import get_authorized_user_id
from ..operators.file import FileOperator
from ..operators.object import ObjectOperator
from ..operators.submission import SubmissionOperator
from ..services.project import ProjectService


class RESTAPIHandler:
    """Handler for REST API methods."""

    def _check_schema_exists(self, schema_type: str) -> None:
        """Check if schema type exists.

        :param schema_type: schema type.
        :raises: HTTPNotFound if schema does not exist.
        """
        if schema_type not in set(schema_types.keys()):
            reason = f"Specified schema {schema_type} was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

    def _get_page_param(self, req: Request, name: str, default: int) -> int:
        """Handle page parameter value extracting.

        :param req: GET Request
        :param param_name: Name of the parameter
        :param default: Default value in case parameter not specified in request
        :returns: Page parameter value
        """
        try:
            param = int(req.query.get(name, str(default)))
        except ValueError as exc:
            reason = f"{name} parameter must be a number, now it is {req.query.get(name)}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason) from exc
        if param < 1:
            reason = f"{name} parameter must be over 0"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return param

    def _get_param(self, req: Request, name: str) -> str:
        """Extract mandatory query parameter from URL.

        :param req: GET Request
        :param name: name of query param to get
        :returns: project ID parameter value
        """
        param = req.query.get(name, "")
        if param == "":
            reason = f"mandatory query parameter {name} is not set"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return param

    async def _handle_check_ownership(self, req: Request, collection: str, accession_id: str) -> None:
        """Check if object belongs to project.

        For this we need to check the object is in exactly 1 submission and we need to check
        that submission belongs to a project.

        :param req: HTTP request
        :param collection: collection or schema of document
        :param accession_id: document accession id
        :raises: HTTPUnauthorized if accession id does not belong to user
        :returns: bool and possible project id
        """

        user_id = get_authorized_user_id(req)

        db_client = req.app["db_client"]
        project_service: ProjectService = req.app["project_service"]

        project_id: str | None = None

        submission_op = SubmissionOperator(db_client)
        if collection != "submission":
            submission_id, _ = await submission_op.check_object_in_submission(collection, accession_id)
            if submission_id:
                # if the draft object is found in submission we just need to check if the submission belongs to user
                project_id = await submission_op.get_submission_field_str(submission_id, "projectId")
        else:
            project_id = await submission_op.get_submission_field_str(accession_id, "projectId")

        if project_id is not None:
            await project_service.verify_user_project(user_id, project_id)
        else:
            reason = f"{collection} {accession_id}."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def _get_data(self, req: Request) -> dict[str, Any]:
        """Get the data content from a request.

        :param req: POST/PUT/PATCH request
        :raises: HTTPBadRequest if request does not have proper JSON data
        :returns: JSON content of the request
        """
        try:
            content: dict[str, Any] = await req.json()
            return content
        except json.decoder.JSONDecodeError as e:
            reason = f"JSON is not correctly formatted, err: {e}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

    @staticmethod
    def _json_response(data: dict[str, Any] | list[dict[str, Any]]) -> Response:
        """Reusable json response, serializing data with ujson.

        :param data: Data to be serialized and made into HTTP 200 response
        """
        return web.Response(
            body=ujson.dumps(data, escape_forward_slashes=False), status=200, content_type="application/json"
        )

    async def get_schema_types(self, _: Request) -> Response:
        """Get all possible metadata schema types from database.

        Basically returns which objects user can submit and query for.

        :returns: JSON list of schema types
        """
        data = [x["description"] for x in schema_types.values()]
        LOG.info("GET schema types. Retrieved %d schemas.", len(schema_types))
        return self._json_response(data)

    async def get_json_schema(self, req: Request) -> Response:
        """Get all JSON Schema for a specific schema type.

        Basically returns which objects user can submit and query for.
        :param req: GET Request
        :raises: HTTPBadRequest if request does not find the schema
        :returns: JSON list of schema types
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)

        try:
            if schema_type == "datacite":
                submission = JSONSchemaLoader().get_schema("submission")
                schema = submission["properties"]["doiInfo"]
            else:
                schema = JSONSchemaLoader().get_schema(schema_type)
            LOG.info("%s JSON schema loaded.", schema_type)
            return self._json_response(schema)

        except SchemaNotFoundException as error:
            reason = f"{error} Occured for JSON schema: '{schema_type}'."
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def get_workflows(self, _: Request) -> Response:
        """Get all JSON workflows.

        Workflows tell what are the requirements for different 'types of submissions' (aka workflow)

        :returns: JSON list of workflows
        """
        LOG.info("GET workflows. Retrieved %d workflows.", len(WORKFLOWS))
        response = {workflow.name: workflow.description for workflow in WORKFLOWS.values()}
        return self._json_response(response)

    async def get_workflow_request(self, req: Request) -> Response:
        """Get a single workflow definition by name.

        :param req: GET Request
        :raises: HTTPNotFound if workflow doesn't exist
        :returns: workflow as a JSON object
        """
        workflow_name = req.match_info["workflow"]
        LOG.info("GET workflow: %r.", workflow_name)
        workflow = self.get_workflow(workflow_name)
        return self._json_response(workflow.workflow)

    def get_workflow(self, workflow_name: str) -> Workflow:
        """Get a single workflow definition by name.

        :param workflow_name: Name of the workflow
        :raises: HTTPNotFound if workflow doesn't exist
        :returns: Workflow
        """
        if workflow_name not in WORKFLOWS:
            reason = f"Workflow {workflow_name} was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)
        return WORKFLOWS[workflow_name]

    def _header_links(self, url: str, page: int, size: int, total_objects: int) -> CIMultiDict[str]:
        """Create link header for pagination.

        :param url: base url for request
        :param page: current page
        :param size: results per page
        :param total_objects: total objects to compute the total pages
        :returns: JSON with query results
        """
        total_pages = ceil(total_objects / size)
        prev_link = f'<{url}?page={page - 1}&per_page={size}>; rel="prev", ' if page > 1 else ""
        next_link = f'<{url}?page={page + 1}&per_page={size}>; rel="next", ' if page < total_pages else ""
        last_link = f'<{url}?page={total_pages}&per_page={size}>; rel="last"' if page < total_pages else ""
        comma = ", " if 1 < page < total_pages else ""
        first_link = f'<{url}?page=1&per_page={size}>; rel="first"{comma}' if page > 1 else ""
        links = f"{prev_link}{next_link}{first_link}{last_link}"
        link_headers = CIMultiDict(Link=f"{links}")
        LOG.debug("Link headers created")
        return link_headers

    @staticmethod
    def iter_submission_objects(submission: dict[str, Any]) -> Iterator[tuple[str, str]]:
        """Iterate over a submission's objects.

        :param submission: Submission data

        yields accession_id, schema
        """
        for _obj in submission["metadataObjects"]:
            accession_id = _obj["accessionId"]
            schema = _obj["schema"]

            yield accession_id, schema

    async def iter_submission_objects_data(
        self, submission: dict[str, Any], obj_op: ObjectOperator
    ) -> AsyncIterator[tuple[str, str, dict[str, Any]]]:
        """Iterate over a submission's objects and retrieve their data.

        :param submission: Submission data
        :param obj_op: Object ObjectOperator

        yields accession_id, schema, object_data
        """
        for accession_id, schema in self.iter_submission_objects(submission):
            object_data, _ = await obj_op.read_metadata_object(schema, accession_id)

            if not isinstance(object_data, dict):
                LOG.error("Object with accession ID %r is not a Dict. This might be a bug", accession_id)
                continue

            yield accession_id, schema, object_data


class RESTAPIIntegrationHandler(RESTAPIHandler):
    """Endpoints that use service integrations."""

    def __init__(
        self,
        metax_handler: MetaxServiceHandler,
        datacite_handler: DataciteServiceHandler,
        pid_handler: PIDServiceHandler,
        rems_handler: RemsServiceHandler,
        admin_handler: AdminServiceHandler,
    ) -> None:
        """Endpoints should have access to metax, datacite, rems, and admin services."""
        self.metax_handler = metax_handler
        self.datacite_handler = datacite_handler
        self.pid_handler = pid_handler
        self.rems_handler = rems_handler
        self.admin_handler = admin_handler

    async def create_metax_dataset(
        self, obj_op: ObjectOperator, collection: str, obj: dict[str, Any], external_id: str
    ) -> str:
        """Handle connection to Metax api handler for dataset creation.

        Dataset or Study object is assigned with DOI
        and it's data is sent to Metax api handler.
        Object database entry is updated with metax ID returned by Metax service.

        :param obj_op: Object ObjectOperator
        :param collection: object's schema
        :param obj: metadata object
        :param external_id: user id
        :returns: Metax ID
        """
        LOG.info("Creating draft dataset to Metax.")
        new_info = {}
        if "doi" in obj:
            new_info["doi"] = obj["doi"]
        metax_id = await self.metax_handler.post_dataset_as_draft(external_id, collection, obj)
        new_info["metaxIdentifier"] = metax_id
        await obj_op.update_identifiers(collection, obj["accessionId"], new_info)

        return metax_id

    async def check_rems_ok(self, submission: dict[str, Any]) -> bool:
        """Check that REMS DAC in object is ok.

        :param submission: Submission data
        :returns: bool
        """
        if "rems" not in submission:
            raise web.HTTPBadRequest(reason="REMS field is missing.")

        dac = submission["rems"]

        if "workflowId" in dac and "organizationId" in dac and "licenses" in dac:
            await self.rems_handler.validate_workflow_licenses(
                dac["organizationId"], dac["workflowId"], dac["licenses"]
            )
        else:
            raise web.HTTPBadRequest(
                reason="REMS DAC is missing one or more of the required fields: "
                "'workflowId', 'organizationId', or 'licenses'."
            )

        return True

    async def update_object_in_submission(
        self, submission_op: SubmissionOperator, submission_id: str, schema: str, schema_data: dict[str, Any]
    ) -> str:
        """Update object in submission from database.

        The object's schema can be REMS or Datacite.

        :param submission_op: Submission Operator
        :param submission_id: ID of the submission
        :param schema: schema type to be updated
        :param schema_data: data of the schema to be updated
        :returns: submission_id
        """
        submission = await submission_op.read_submission(submission_id)

        op = "add"
        if schema in submission:
            op = "replace"
        patch = [
            {"op": op, "path": f"/{schema}", "value": schema_data},
        ]

        submission[schema] = schema_data
        JSONValidator(submission, "submission").validate

        upd_submission_id = await submission_op.update_submission(submission_id, patch)
        LOG.info("PUT %r in submission with ID: %r was successful.", schema, submission_id)
        return upd_submission_id

    async def start_file_polling(
        self, req: Request, files: dict[str, str], file_op: FileOperator, data: dict[str, str], status: str
    ) -> None:
        """Regularly poll files to see if they have required status.

        :param req: HTTP request
        :param files: List of files to be polled
        :param file_op: File Operator
        :param data: Includes 'user' and 'submissionId'
        :param status: The expected file status that is polled
        """
        status_found = {f: False for f in files.keys()}

        while True:
            inbox_files = await self.admin_handler.get_user_files(req, data["user"])
            for inbox_file in inbox_files:
                if "inboxPath" not in inbox_file or "fileStatus" not in inbox_file:
                    reason = "'inboxPath' or 'fileStatus' are missing from file data."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)

                inbox_path = inbox_file["inboxPath"]
                if not status_found.get(inbox_path, True):
                    if inbox_file["fileStatus"] == status:
                        status_found[inbox_path] = True
                        accessionId = files[inbox_path]
                        await file_op.update_file_submission(
                            accessionId, data["submissionId"], {"files.$.status": status}
                        )
                        if status == "verified":
                            await self.admin_handler.post_accession_id(
                                req,
                                {
                                    "user": data["user"],
                                    "filepath": inbox_path,
                                    "accessionId": accessionId,
                                },
                            )
                    elif inbox_file["fileStatus"] == "error":
                        reason = f"File {inbox_path} in submission {data['submissionId']} has status 'error'"
                        LOG.exception(reason)
                        raise web.HTTPInternalServerError(reason=reason)

            success = all(status_found.values())
            if success:
                break

            num_waiting = sum((not x for x in status_found.values()))
            LOG.debug("%d files were not yet %s for submission %s", num_waiting, status, data["submissionId"])
            await sleep(POLLING_INTERVAL)
