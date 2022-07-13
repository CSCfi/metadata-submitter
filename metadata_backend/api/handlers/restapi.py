"""Handle HTTP methods for server."""
import json
from math import ceil
from typing import AsyncGenerator, Dict, List, Tuple

import aiohttp_session
import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from multidict import CIMultiDict

from ...conf.conf import schema_types
from ...helpers.logger import LOG
from ...helpers.schema_loader import JSONSchemaLoader, SchemaNotFoundException
from ...services.datacite_service_handler import DataciteServiceHandler
from ...services.metax_service_handler import MetaxServiceHandler
from ...services.rems_service_handler import RemsServiceHandler
from ..operators import Operator, SubmissionOperator, UserOperator


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
        except ValueError:
            reason = f"{name} parameter must be a number, now it is {req.query.get(name)}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
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

    async def _handle_check_ownership(self, req: Request, collection: str, accession_id: str) -> Tuple[bool, str]:
        """Check if object belongs to project.

        For this we need to check the object is in exactly 1 submission and we need to check
        that submission belongs to a project.

        :param req: HTTP request
        :param collection: collection or schema of document
        :param doc_id: document accession id
        :raises: HTTPUnauthorized if accession id does not belong to user
        :returns: bool and possible project id
        """
        session = await aiohttp_session.get_session(req)

        db_client = req.app["db_client"]

        current_user = session["user_info"]
        user_op = UserOperator(db_client)
        _check = False

        project_id = ""
        if collection != "submissions":

            submission_op = SubmissionOperator(db_client)
            check, submission_id, _ = await submission_op.check_object_in_submission(collection, accession_id)
            # if published:
            #     _check = True
            if check:
                # if the draft object is found in submission we just need to check if the submission belongs to user
                _check, project_id = await user_op.check_user_has_doc(req, "submissions", current_user, submission_id)
            elif collection.startswith("template"):
                # if collection is template but not found in a submission
                # we also check if object is in templates of the user
                # they will be here if they will not be deleted after publish
                _check, project_id = await user_op.check_user_has_doc(req, collection, current_user, accession_id)
            else:
                _check = False
        else:
            _check, project_id = await user_op.check_user_has_doc(req, collection, current_user, accession_id)

        if not _check:
            reason = f"{collection} {accession_id}."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        return _check, project_id

    async def _get_collection_objects(
        self, submission_op: AsyncIOMotorClient, collection: str, seq: List
    ) -> AsyncGenerator:
        """Get objects ids based on submission and collection.

        Considering that many objects will be returned good to have a generator.

        :param req: HTTP request
        :param collection: collection or schema of document
        :param seq: list of submissions
        :returns: AsyncGenerator
        """
        for el in seq:
            result = await submission_op.get_collection_objects(el, collection)

            yield result

    async def _get_data(self, req: Request) -> Dict:
        """Get the data content from a request.

        :param req: POST/PUT/PATCH request
        :raises: HTTPBadRequest if request does not have proper JSON data
        :returns: JSON content of the request
        """
        try:
            content = await req.json()
            return content
        except json.decoder.JSONDecodeError as e:
            reason = "JSON is not correctly formatted." f" See: {e}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def get_schema_types(self, req: Request) -> Response:
        """Get all possible metadata schema types from database.

        Basically returns which objects user can submit and query for.
        :param req: GET Request
        :returns: JSON list of schema types
        """
        types_json = ujson.dumps([x["description"] for x in schema_types.values()], escape_forward_slashes=False)
        LOG.info(f"GET schema types. Retrieved {len(schema_types)} schemas.")
        return web.Response(body=types_json, status=200, content_type="application/json")

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
            LOG.info(f"{schema_type} schema loaded.")
            return web.Response(
                body=ujson.dumps(schema, escape_forward_slashes=False), status=200, content_type="application/json"
            )

        except SchemaNotFoundException as error:
            reason = f"{error} ({schema_type})"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    def _header_links(self, url: str, page: int, size: int, total_objects: int) -> CIMultiDict[str]:
        """Create link header for pagination.

        :param url: base url for request
        :param page: current page
        :param size: results per page
        :param total_objects: total objects to compute the total pages
        :returns: JSON with query results
        """
        total_pages = ceil(total_objects / size)
        prev_link = f'<{url}?page={page-1}&per_page={size}>; rel="prev", ' if page > 1 else ""
        next_link = f'<{url}?page={page+1}&per_page={size}>; rel="next", ' if page < total_pages else ""
        last_link = f'<{url}?page={total_pages}&per_page={size}>; rel="last"' if page < total_pages else ""
        comma = ", " if page > 1 and page < total_pages else ""
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
        rems_handler: RemsServiceHandler,
    ) -> None:
        """Endpoints should have access to metax and datacite services."""
        self.metax_handler = metax_handler
        self.datacite_handler = datacite_handler
        self.rems_handler = rems_handler

    @staticmethod
    async def get_user_external_id(request: web.Request) -> str:
        """Get current user's external id.

        :param request: current HTTP request made by the user
        :returns: Current users external ID
        """
        session = await aiohttp_session.get_session(request)
        current_user = session["user_info"]
        user_op = UserOperator(request.app["db_client"])
        user = await user_op.read_user(current_user)
        metadata_provider_user = user["externalId"]
        return metadata_provider_user

    async def create_metax_dataset(self, request: Request, collection: str, object: Dict) -> str:
        """Handle connection to Metax api handler for dataset creation.

        Dataset or Study object is assigned with DOI
        and it's data is sent to Metax api handler.
        Object database entry is updated with metax ID returned by Metax service.

        :param request: HTTP request with user session
        :param collection: object's schema
        :param object: metadata object
        :returns: Metax ID
        """
        LOG.info("Creating draft dataset to Metax.")
        if not self.metax_handler.enabled:
            LOG.error("Metax integration is disabled.")
            return ""
        operator = Operator(request.app["db_client"])
        new_info = {}
        if "doi" in object:
            new_info["doi"] = object["doi"]
        external_id = await self.get_user_external_id(request)
        metax_id = await self.metax_handler.post_dataset_as_draft(external_id, collection, object)
        new_info["metaxIdentifier"] = metax_id
        await operator.update_identifiers(collection, object["accessionId"], new_info)

        return metax_id

    async def create_draft_doi(self, collection: str) -> str:
        """Create draft DOI for study and dataset.

        The Draft DOI will be created only on POST and the data added to the
        submission. Any update of this should not be possible.

        :param collection: either study or dataset
        :returns: Dict with DOI of the study or dataset as well as the types.
        """
        _doi_data = await self.datacite_handler.create_draft(prefix=collection)

        LOG.debug(f"doi created with doi: {_doi_data['fullDOI']}")

        return _doi_data["fullDOI"]

    async def check_dac_ok(self, submission: dict) -> bool:
        """Check that DAC in object is ok."""
        if "dac" not in submission:
            raise web.HTTPBadRequest(reason="DAC is missing.")

        dac = submission["dac"]

        if "workflowId" in dac and "organizationId" in dac and "licenses" in dac:
            await self.rems_handler.validate_workflow_licenses(
                dac["organizationId"], dac["workflowId"], dac["licenses"]
            )
        else:
            raise web.HTTPBadRequest(
                reason="DAC is missing one or more of the required fields: "
                "'workflowId', 'organizationId', or 'licenses'."
            )

        return True
