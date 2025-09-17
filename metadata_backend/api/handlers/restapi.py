"""Handle HTTP methods for server."""

import json
from asyncio import sleep
from math import ceil
from typing import Any

from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...conf.conf import POLLING_INTERVAL, WORKFLOWS, get_workflow, schema_types
from ...database.postgres.models import IngestStatus
from ...helpers.logger import LOG
from ...helpers.schema_loader import JSONSchemaLoader, SchemaFileNotFoundException
from ...services.admin_service_handler import AdminServiceHandler
from ...services.datacite_service_handler import DataciteServiceHandler
from ...services.metax_service_handler import MetaxServiceHandler
from ...services.pid_ms_handler import PIDServiceHandler
from ...services.rems_service_handler import RemsServiceHandler
from ..models import Rems
from ..resources import get_file_service
from .common import to_json


class RESTAPIHandler:
    """Handler for REST API methods."""

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

    @staticmethod
    async def _json_data(req: Request) -> dict[str, Any]:
        """Get the JSON data content from a request.

        :param req: HTTP request
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
    def _json_response(data: dict[str, Any] | list[dict[str, Any]] | list[str]) -> Response:
        """Reusable json response, serializing data with ujson.

        :param data: Data to be serialized and made into HTTP 200 response
        """
        return web.Response(body=to_json(data), status=200, content_type="application/json")

    async def get_schema_types(self, _: Request) -> Response:
        """Get all possible metadata schema types from database.

        Basically returns which objects user can submit and query for.

        :returns: JSON list of schema types
        """
        data = [x["description"] for x in schema_types.values()]
        LOG.info("GET schema types. Retrieved %d schemas.", len(schema_types))
        return self._json_response(data)

    async def get_json_schema(self, req: Request) -> Response:
        """
        Get JSON Schema for a specific schema type.

        :param req: GET Request
        :raises: HTTPBadRequest if request does not find the schema
        :returns: JSON list of schema types
        """
        schema_type = req.match_info["schema"]

        if schema_type not in set(schema_types.keys()):
            reason = f"Specified schema {schema_type} was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        try:
            if schema_type == "datacite":
                submission = JSONSchemaLoader().get_schema("submission")
                schema = submission["properties"]["doiInfo"]
            else:
                schema = JSONSchemaLoader().get_schema(schema_type)
            LOG.info("%s JSON schema loaded.", schema_type)
            return self._json_response(schema)

        except SchemaFileNotFoundException as error:
            reason = f"{error} Occurred for JSON schema: '{schema_type}'."
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
        workflow = get_workflow(workflow_name)
        return self._json_response(workflow.workflow)

    @staticmethod
    def _pagination_header_links(url: str, page: int, size: int, total_objects: int) -> CIMultiDict[str]:
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

    async def check_rems_ok(self, rems: Rems) -> None:
        """Check REMS workflow and licenses.

        :param rems: the REMS data
        """
        await self.rems_handler.validate_workflow_licenses(rems.organization_id, rems.workflow_id, rems.licenses)

    async def start_file_polling(self, req: Request, files: dict[str, str], data: dict[str, str], status: str) -> None:
        """Regularly poll files to see if they have required status.

        :param req: HTTP request
        :param files: List of files to be polled
        :param data: Includes 'user' and 'submissionId'
        :param status: The expected file status that is polled
        """
        status_found = {f: False for f in files.keys()}

        file_service = get_file_service(req)

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
                        file_id = files[inbox_path]
                        await file_service.update_ingest_status(file_id, IngestStatus(status))
                        if status == "verified":
                            await self.admin_handler.post_accession_id(
                                req,
                                {
                                    "user": data["user"],
                                    "filepath": inbox_path,
                                    "accessionId": file_id,
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
