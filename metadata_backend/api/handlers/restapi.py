"""Handle HTTP methods for server."""
import json
from math import ceil
from typing import AsyncGenerator, Dict, List

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from multidict import CIMultiDict

from ...conf.conf import schema_types
from ...helpers.logger import LOG
from ...helpers.schema_loader import JSONSchemaLoader, SchemaNotFoundException
from ..middlewares import get_session
from ..operators import FolderOperator, UserOperator


class RESTAPIHandler:
    """Handler for REST API methods."""

    def _check_schema_exists(self, schema_type: str) -> None:
        """Check if schema type exists.

        :param schema_type: schema type.
        :raises: HTTPNotFound if schema does not exist.
        """
        if schema_type not in schema_types.keys():
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
            param = int(req.query.get(name, default))
        except ValueError:
            reason = f"{name} parameter must be a number, now it is {req.query.get(name)}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if param < 1:
            reason = f"{name} parameter must be over 0"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return param

    async def _handle_check_ownedby_user(self, req: Request, collection: str, accession_id: str) -> bool:
        """Check if object belongs to user.

        For this we need to check the object is in exactly 1 folder and we need to check
        that folder belongs to a user. If the folder is published that means it can be
        browsed by other users as well.

        :param req: HTTP request
        :param collection: collection or schema of document
        :param doc_id: document accession id
        :raises: HTTPUnauthorized if accession id does not belong to user
        :returns: bool
        """
        db_client = req.app["db_client"]
        current_user = get_session(req)["user_info"]
        user_op = UserOperator(db_client)
        _check = False

        if collection != "folders":

            folder_op = FolderOperator(db_client)
            check, folder_id, published = await folder_op.check_object_in_folder(collection, accession_id)
            if published:
                _check = True
            elif check:
                # if the draft object is found in folder we just need to check if the folder belongs to user
                _check = await user_op.check_user_has_doc("folders", current_user, folder_id)
            elif collection.startswith("template"):
                # if collection is template but not found in a folder
                # we also check if object is in templates of the user
                # they will be here if they will not be deleted after publish
                _check = await user_op.check_user_has_doc(collection, current_user, accession_id)
            else:
                _check = False
        else:
            _check = await user_op.check_user_has_doc(collection, current_user, accession_id)

        if not _check:
            reason = f"The ID: {accession_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        return _check

    async def _get_collection_objects(
        self, folder_op: AsyncIOMotorClient, collection: str, seq: List
    ) -> AsyncGenerator:
        """Get objects ids based on folder and collection.

        Considering that many objects will be returned good to have a generator.

        :param req: HTTP request
        :param collection: collection or schema of document
        :param seq: list of folders
        :returns: AsyncGenerator
        """
        for el in seq:
            result = await folder_op.get_collection_objects(el, collection)

            yield result

    async def _handle_user_objects_collection(self, req: Request, collection: str) -> List:
        """Retrieve list of objects accession ids belonging to user in collection.

        :param req: HTTP request
        :param collection: collection or schema of document
        :returns: List
        """
        db_client = req.app["db_client"]
        current_user = get_session(req)["user_info"]
        user_op = UserOperator(db_client)
        folder_op = FolderOperator(db_client)

        user = await user_op.read_user(current_user)
        res = self._get_collection_objects(folder_op, collection, user["folders"])

        dt = []
        async for r in res:
            dt.extend(r)

        return dt

    async def _filter_by_user(self, req: Request, collection: str, seq: List) -> AsyncGenerator:
        """For a list of objects check if these are owned by a user.

        This can be called using a partial from functools.

        :param req: HTTP request
        :param collection: collection or schema of document
        :param seq: list of folders
        :returns: AsyncGenerator
        """
        for el in seq:
            if await self._handle_check_ownedby_user(req, collection, el["accessionId"]):
                yield el

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
            schema = JSONSchemaLoader().get_schema(schema_type)
            LOG.info(f"{schema_type} schema loaded.")
            return web.Response(
                body=ujson.dumps(schema, escape_forward_slashes=False), status=200, content_type="application/json"
            )

        except SchemaNotFoundException as error:
            reason = f"{error} ({schema_type})"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def _header_links(self, url: str, page: int, size: int, total_objects: int) -> CIMultiDict[str]:
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
