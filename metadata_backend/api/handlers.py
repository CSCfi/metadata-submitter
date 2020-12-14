"""Handle HTTP methods for server."""
import json
import mimetypes
from collections import Counter
from math import ceil
from pathlib import Path
from typing import Dict, List, Tuple, Union, cast, AsyncGenerator

from aiohttp import BodyPartReader, web
from aiohttp.web import Request, Response
from multidict import CIMultiDict
from motor.motor_asyncio import AsyncIOMotorClient
from multidict import MultiDict, MultiDictProxy
from xmlschema import XMLSchemaException

from ..conf.conf import schema_types
from ..helpers.logger import LOG
from ..helpers.parser import XMLToJSONParser
from ..helpers.schema_loader import JSONSchemaLoader, SchemaNotFoundException, XMLSchemaLoader
from ..helpers.validator import JSONValidator, XMLValidator
from .operators import FolderOperator, Operator, XMLOperator, UserOperator

from ..conf.conf import aai_config


class RESTApiHandler:
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
        current_user = req.app["Session"]["user_info"]
        user_op = UserOperator(db_client)

        if collection != "folders":

            folder_op = FolderOperator(db_client)
            check, folder_id, published = await folder_op.check_object_in_folder(collection, accession_id)

            if published:
                return True
            elif check:
                # if the draft object is found in folder we just need to check if the folder belongs to user
                return await user_op.check_user_has_doc("folders", current_user, folder_id)
            elif collection.startswith("draft"):
                # if collection is draft but not found in a folder we also check if object is in drafts of the user
                # they will be here if they will not be deleted after publish
                return await user_op.check_user_has_doc(collection, current_user, accession_id)
            else:
                return False
        else:
            return await user_op.check_user_has_doc(collection, current_user, accession_id)

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
        """Retrieve list of  objects accession ids belonging to user in collection.

        :param req: HTTP request
        :param collection: collection or schema of document
        :returns: List
        """
        db_client = req.app["db_client"]
        current_user = req.app["Session"]["user_info"]
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

    async def _handle_query(self, req: Request) -> Response:
        """Handle query results.

        :param req: GET request with query parameters
        :returns: JSON with query results
        """
        collection = req.match_info["schema"]
        req_format = req.query.get("format", "json").lower()
        if req_format == "xml":
            reason = "xml-formatted query results are not supported"
            raise web.HTTPBadRequest(reason=reason)

        def get_page_param(param_name: str, default: int) -> int:
            """Handle page parameter value extracting."""
            try:
                param = int(req.query.get(param_name, default))
            except ValueError:
                reason = f"{param_name} must be a number, now it is " f"{req.query.get(param_name)}"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            if param < 1:
                reason = f"{param_name} must over 1"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            return param

        page = get_page_param("page", 1)
        per_page = get_page_param("per_page", 10)
        db_client = req.app["db_client"]

        filter_list = await self._handle_user_objects_collection(req, collection)
        data, page_num, page_size, total_objects = await Operator(db_client).query_metadata_database(
            collection, req.query, page, per_page, filter_list
        )

        result = json.dumps(
            {
                "page": {
                    "page": page_num,
                    "size": page_size,
                    "totalPages": ceil(total_objects / per_page),
                    "totalObjects": total_objects,
                },
                "objects": data,
            }
        )
        url = f"{req.scheme}://{req.host}{req.path}"
        link_headers = self._header_links(url, page_num, per_page, total_objects)
        LOG.debug(f"Pagination header links: {link_headers}")
        LOG.info(f"Querying for objects in {collection} resulted in {total_objects} objects ")
        return web.Response(
            body=result,
            status=200,
            headers=link_headers,
            content_type="application/json",
        )

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
        types_json = json.dumps([x["description"] for x in schema_types.values()])
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
            return web.Response(body=json.dumps(schema), status=200, content_type="application/json")

        except SchemaNotFoundException as error:
            reason = f"{error} ({schema_type})"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def get_object(self, req: Request) -> Response:
        """Get one metadata object by its accession id.

        Returns original xml object from backup if format query parameter is
        set, otherwise json.

        :param req: GET request
        :raises: HTTPUnauthorized if object not owned by user
        :returns: JSON or XML response containing metadata object
        """
        accession_id = req.match_info["accessionId"]
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        req_format = req.query.get("format", "json").lower()
        db_client = req.app["db_client"]
        operator = XMLOperator(db_client) if req_format == "xml" else Operator(db_client)

        check_user = await self._handle_check_ownedby_user(req, collection, accession_id)
        if not check_user:
            reason = f"The object {accession_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        data, content_type = await operator.read_metadata_object(collection, accession_id)

        data = data if req_format == "xml" else json.dumps(data)
        LOG.info(f"GET object with accesssion ID {accession_id} from schema {collection}.")
        return web.Response(body=data, status=200, content_type=content_type)

    async def post_object(self, req: Request) -> Response:
        """Save metadata object to database.

        For JSON request body we validate it is consistent with the
        associated JSON schema.

        :param req: POST request
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        db_client = req.app["db_client"]
        content: Union[Dict, str]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            files = await _extract_xml_upload(req, extract_one=True)
            content, _ = files[0]
            operator = XMLOperator(db_client)
        else:
            content = await self._get_data(req)
            if not req.path.startswith("/drafts"):
                JSONValidator(content, schema_type).validate
            operator = Operator(db_client)

        accession_id = await operator.create_metadata_object(collection, content)

        body = json.dumps({"accessionId": accession_id})
        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}{accession_id}")
        LOG.info(f"POST object with accesssion ID {accession_id} in schema {collection} was successful.")
        return web.Response(
            body=body,
            status=201,
            headers=location_headers,
            content_type="application/json",
        )

    async def query_objects(self, req: Request) -> Response:
        """Query metadata objects from database.

        :param req: GET request with query parameters (can be empty).
        :returns: Query results as JSON
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        return await self._handle_query(req)

    async def delete_object(self, req: Request) -> Response:
        """Delete metadata object from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if object not owned by user
        :returns: HTTPNoContent response
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        accession_id = req.match_info["accessionId"]
        db_client = req.app["db_client"]

        check_user = await self._handle_check_ownedby_user(req, collection, accession_id)
        if not check_user:
            reason = f"The object {accession_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        folder_op = FolderOperator(db_client)
        exists, folder_id, published = await folder_op.check_object_in_folder(collection, accession_id)
        if exists:
            if published:
                reason = "published objects cannot be deleted."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)
            folder_op.remove_object(folder_id, collection, accession_id)
        else:
            user_op = UserOperator(db_client)
            current_user = req.app["Session"]["user_info"]
            check_user = await user_op.check_user_has_doc(collection, current_user, accession_id)
            if check_user:
                collection = "drafts"
            else:
                reason = "This object does not seem to belong to anything."
                LOG.error(reason)
                raise web.HTTPUnprocessableEntity(reason=reason)

        accession_id = await Operator(db_client).delete_metadata_object(collection, accession_id)

        LOG.info(f"DELETE object with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(status=204)

    async def put_object(self, req: Request) -> Response:
        """Replace metadata object in database.

        For JSON request body we validate that it consists of all the
        required fields before replacing in the DB.

        :param req: PUT request
        :raises: HTTPUnauthorized if object not owned by user
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        db_client = req.app["db_client"]
        content: Union[Dict, str]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            files = await _extract_xml_upload(req, extract_one=True)
            content, _ = files[0]
            operator = XMLOperator(db_client)
        else:
            content = await self._get_data(req)
            if not req.path.startswith("/drafts"):
                JSONValidator(content, schema_type).validate
            operator = Operator(db_client)

        check_user = await self._handle_check_ownedby_user(req, collection, accession_id)
        if not check_user:
            reason = f"The object {accession_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        accession_id = await operator.replace_metadata_object(collection, accession_id, content)

        body = json.dumps({"accessionId": accession_id})
        LOG.info(f"PUT object with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def patch_object(self, req: Request) -> Response:
        """Update metadata object in database.

        We do not support patch for XML.

        :param req: PATCH request
        :raises: HTTPUnauthorized if object not owned by user
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        db_client = req.app["db_client"]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            reason = "XML patching is not possible."
            raise web.HTTPUnsupportedMediaType(reason=reason)
        else:
            content = await self._get_data(req)
            operator = Operator(db_client)

        check_user = await self._handle_check_ownedby_user(req, collection, accession_id)
        if not check_user:
            reason = f"The object {accession_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        accession_id = await operator.update_metadata_object(collection, accession_id, content)

        body = json.dumps({"accessionId": accession_id})
        LOG.info(f"PATCH object with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def get_folders(self, req: Request) -> Response:
        """Get all possible object folders from database.

        :param req: GET Request
        :returns: JSON list of folders available for the user
        """
        db_client = req.app["db_client"]

        user_operator = UserOperator(db_client)

        current_user = req.app["Session"]["user_info"]
        user = await user_operator.read_user(current_user)

        operator = FolderOperator(db_client)
        folders = await operator.query_folders(
            {
                "$redact": {
                    "$cond": {
                        "if": {"$or": [{"$eq": ["$published", True]}, {"$in": ["$folderId", user["folders"]]}]},
                        "then": "$$DESCEND",
                        "else": "$$PRUNE",
                    }
                }
            },
            {"$project": {"_id": 0}},
        )

        body = json.dumps({"folders": folders})
        LOG.info(f"GET folders. Retrieved {len(folders)} folders.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def post_folder(self, req: Request) -> Response:
        """Save object folder to database.

        Also assigns the folder to the current user.

        :param req: POST request
        :returns: JSON response containing folder ID for submitted folder
        """
        db_client = req.app["db_client"]
        content = await self._get_data(req)
        JSONValidator(content, "folders").validate

        operator = FolderOperator(db_client)
        folder = await operator.create_folder(content)

        user_op = UserOperator(db_client)
        current_user = req.app["Session"]["user_info"]
        await user_op.assign_objects(current_user, "folders", [folder])

        body = json.dumps({"folderId": folder})

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{folder}")
        LOG.info(f"POST new folder with ID {folder} was successful.")
        return web.Response(body=body, status=201, headers=location_headers, content_type="application/json")

    async def get_folder(self, req: Request) -> Response:
        """Get one object folder by its folder id.

        :param req: GET request
        :raises: HTTPNotFound if folder not owned by user
        :returns: JSON response containing object folder
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]

        check_user = await self._handle_check_ownedby_user(req, "folders", folder_id)
        if not check_user:
            reason = f"The folder {folder_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        operator = FolderOperator(db_client)
        folder = await operator.read_folder(folder_id)

        LOG.info(f"GET folder with ID {folder_id} was successful.")
        return web.Response(body=json.dumps(folder), status=200, content_type="application/json")

    async def patch_folder(self, req: Request) -> Response:
        """Update object folder with a specific folder id.

        :param req: PATCH request
        :raises: HTTPUnauthorized if folder not owned by user, HTTPBadRequest if JSONpatch operation
        is not allowed
        :returns: JSON response containing folder ID for updated folder
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]

        # Check patch operations in request are valid
        patch_ops = await self._get_data(req)
        allowed_paths = ["/name", "/description"]
        array_paths = ["/metadataObjects/-", "/drafts/-"]
        for op in patch_ops:
            if all(i not in op["path"] for i in allowed_paths + array_paths):
                reason = f"Request contains '{op['path']}' key that cannot be updated to folders."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            if op["op"] in ["remove", "copy", "test", "move"]:
                reason = f"{op['op']} on {op['path']} is not allowed."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)
            if op["op"] == "replace" and op["path"] in array_paths:
                reason = f"{op['op']} on {op['path']} is not allowed."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)

        check_user = await self._handle_check_ownedby_user(req, "folders", folder_id)
        if not check_user:
            reason = f"The folder {folder_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        operator = FolderOperator(db_client)
        folder = await operator.update_folder(folder_id, patch_ops if isinstance(patch_ops, list) else [patch_ops])

        body = json.dumps({"folderId": folder})
        LOG.info(f"PATCH folder with ID {folder} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def publish_folder(self, req: Request) -> Response:
        """Update object folder specifically into published state.

        :param req: PATCH request
        :raises: HTTPUnauthorized if folder not owned by user
        :returns: JSON response containing folder ID for updated folder
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]

        check_user = await self._handle_check_ownedby_user(req, "folders", folder_id)
        if not check_user:
            reason = f"The folder {folder_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        operator = FolderOperator(db_client)
        old_folder = await operator.read_folder(folder_id)
        LOG.info(f"GET folder with ID {folder_id} was successful.")

        # Delete the drafts within the folder from the database
        for draft in old_folder["drafts"]:
            schema_type, accession_id = draft["schema"], draft["accessionId"]
            collection = schema_type[6:] if schema_type.startswith("draft") else schema_type
            self._check_schema_exists(collection)
            accession_id = await Operator(db_client).delete_metadata_object(schema_type, accession_id)
            LOG.info(f"DELETE draft with accession ID {accession_id} in schema {collection} was successful.")

        # Patch the folder into a published state
        patch = [
            {"op": "replace", "path": "/published", "value": True},
            {"op": "replace", "path": "/drafts", "value": []},
        ]
        new_folder = await operator.update_folder(folder_id, patch)

        body = json.dumps({"folderId": new_folder})
        LOG.info(f"Patching folder with ID {new_folder} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_folder(self, req: Request) -> Response:
        """Delete object folder from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if folder not owned by user
        :returns: HTTP No Content response
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]

        check_user = await self._handle_check_ownedby_user(req, "folders", folder_id)
        if not check_user:
            reason = f"The folder {folder_id} does not belong to current user."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        operator = FolderOperator(db_client)
        folder = await operator.delete_folder(folder_id)

        user_op = UserOperator(db_client)
        current_user = req.app["Session"]["user_info"]
        await user_op.remove_objects(current_user, "folders", [folder_id])

        LOG.info(f"DELETE folder with ID {folder} was successful.")
        return web.Response(status=204)

    async def get_user(self, req: Request) -> Response:
        """Get one user by its user ID.

        :param req: GET request
        :raises: HTTPUnauthorized if not current user
        :returns: JSON response containing user object
        """
        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} was requested")
            raise web.HTTPUnauthorized(reason="Only current user retrieval is allowed")
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)

        current_user = req.app["Session"]["user_info"]
        user = await operator.read_user(current_user)

        LOG.info(f"GET user with ID {user_id} was successful.")
        return web.Response(body=json.dumps(user), status=200, content_type="application/json")

    async def patch_user(self, req: Request) -> Response:
        """Update user object with a specific user ID.

        :param req: PATCH request
        :raises: HTTPUnauthorized if not current user
        :returns: JSON response containing user ID for updated user object
        """
        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} patch was requested")
            raise web.HTTPUnauthorized(reason="Only current user operations are allowed")
        db_client = req.app["db_client"]

        # Check patch operations in request are valid
        patch_ops = await self._get_data(req)
        allowed_paths = ["/drafts/-", "/folders/-"]
        for op in patch_ops:
            if all(i not in op["path"] for i in allowed_paths):
                reason = f"Request contains '{op['path']}' key that cannot be updated to user object"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            if op["op"] in ["remove", "copy", "test", "move", "replace"]:
                reason = f"{op['op']} on {op['path']} is not allowed."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)

        operator = UserOperator(db_client)

        current_user = req.app["Session"]["user_info"]
        user = await operator.update_user(current_user, patch_ops if isinstance(patch_ops, list) else [patch_ops])

        body = json.dumps({"userId": user})
        LOG.info(f"PATCH user with ID {user} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_user(self, req: Request) -> Response:
        """Delete user from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if not current user
        :returns: HTTPNoContent response
        """
        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} delete was requested")
            raise web.HTTPUnauthorized(reason="Only current user deleteion is allowed")
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)

        current_user = req.app["Session"]["user_info"]
        user = await operator.delete_user(current_user)
        LOG.info(f"DELETE user with ID {user} was successful.")

        req.app["Session"]["access_token"] = None
        req.app["Session"]["user_info"] = None
        req.app["Session"]["oidc_state"] = None
        req.app["Session"] = {}
        req.app["Cookies"] = set({})

        response = web.HTTPSeeOther(f"{aai_config['domain']}/")
        response.headers["Location"] = "/"
        LOG.debug("Logged out user ")
        raise response


class SubmissionAPIHandler:
    """Handler for non-rest API methods."""

    async def submit(self, req: Request) -> Response:
        """Handle submission.xml containing submissions to server.

        First submission info is parsed and then for every action in submission
        (add/modify/validate) corresponding operation is performed.
        Finally submission info itself is added.

        :param req: Multipart POST request with submission.xml and files
        :raises: HTTPBadRequest if request is missing some parameters or cannot be processed
        :returns: XML-based receipt from submission
        """
        files = await _extract_xml_upload(req)
        schema_types = Counter(file[1] for file in files)
        if "submission" not in schema_types:
            reason = "There must be a submission.xml file in submission."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if schema_types["submission"] > 1:
            reason = "You should submit only one submission.xml file."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        submission_xml = files[0][0]
        submission_json = XMLToJSONParser().parse("submission", submission_xml)

        # Check what actions should be performed, collect them to dictionary
        actions: Dict[str, List] = {}
        for action_set in submission_json["actions"]["action"]:
            for action, attr in action_set.items():
                if not attr:
                    reason = f"""You also need to provide necessary
                                  information for submission action.
                                  Now {action} was provided without any
                                  extra information."""
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                LOG.debug(f"submission has action {action}")
                if attr["schema"] in actions:
                    set = []
                    set.append(actions[attr["schema"]])
                    set.append(action)
                    actions[attr["schema"]] = set
                else:
                    actions[attr["schema"]] = action

        # Go through parsed files and do the actual action
        results: List[Dict] = []
        db_client = req.app["db_client"]
        for file in files:
            content_xml = file[0]
            schema_type = file[1]
            if schema_type == "submission":
                LOG.debug("file has schema of submission type, continuing ...")
                continue  # No need to use submission xml
            action = actions[schema_type]
            if isinstance(action, List):
                for item in action:
                    result = await self._execute_action(schema_type, content_xml, db_client, item)
                    results.append(result)
            else:
                result = await self._execute_action(schema_type, content_xml, db_client, action)
                results.append(result)

        body = json.dumps(results)
        LOG.info(f"Processed a submission of {len(results)} actions.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def validate(self, req: Request) -> Response:
        """Handle validating an xml file sent to endpoint.

        :param req: Multipart POST request with submission.xml and files
        :returns: JSON response indicating if validation was successful or not
        """
        files = await _extract_xml_upload(req, extract_one=True)
        xml_content, schema_type = files[0]
        validator = await self._perform_validation(schema_type, xml_content)
        return web.Response(body=validator.resp_body, content_type="application/json")

    async def _perform_validation(self, schema_type: str, xml_content: str) -> XMLValidator:
        """Validate an xml.

        :param schema_type: Schema type of the object to validate.
        :param xml_content: Metadata object
        :raises: HTTPBadRequest if schema load fails
        :returns: JSON response indicating if validation was successful or not
        """
        try:
            schema = XMLSchemaLoader().get_schema(schema_type)
            LOG.info(f"{schema_type} schema loaded.")
            return XMLValidator(schema, xml_content)

        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} ({schema_type})"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def _execute_action(self, schema: str, content: str, db_client: AsyncIOMotorClient, action: str) -> Dict:
        """Complete the command in the action set of the submission file.

        Only "add/modify/validate" actions are supported.

        :param schema: Schema type of the object in question
        :param content: Metadata object referred to in submission
        :param db_client: Database client for database operations
        :param action: Type of action to be done
        :raises: HTTPBadRequest if an incorrect or non-supported action is called
        :returns: Dict containing specific action that was completed
        """
        if action == "add":
            result = {
                "accessionId": await XMLOperator(db_client).create_metadata_object(schema, content),
                "schema": schema,
            }
            LOG.debug(f"added some content in {schema} ...")
            return result

        elif action == "modify":
            data_as_json = XMLToJSONParser().parse(schema, content)
            if "accessionId" in data_as_json:
                accession_id = data_as_json["accessionId"]
            else:
                alias = data_as_json["alias"]
                query = MultiDictProxy(MultiDict([("alias", alias)]))
                data, _, _, _ = await Operator(db_client).query_metadata_database(schema, query, 1, 1, [])
                if len(data) > 1:
                    reason = "Alias in provided XML file corresponds with more than one existing metadata object."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                accession_id = data[0]["accessionId"]
            data_as_json.pop("accessionId", None)
            result = {
                "accessionId": await Operator(db_client).update_metadata_object(schema, accession_id, data_as_json),
                "schema": schema,
            }
            LOG.debug(f"modified some content in {schema} ...")
            return result

        elif action == "validate":
            validator = await self._perform_validation(schema, content)
            return json.loads(validator.resp_body)

        else:
            reason = f"Action {action} in xml is not supported."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)


class StaticHandler:
    """Handler for static routes, mostly frontend and 404."""

    def __init__(self, frontend_static_files: Path) -> None:
        """Initialize path to frontend static files folder."""
        self.path = frontend_static_files

    async def frontend(self, req: Request) -> Response:
        """Serve requests related to frontend SPA.

        :param req: GET request
        :returns: Response containing frontpage static file
        """
        index_path = self.path / "index.html"
        LOG.debug("Serve Frontend SPA.")
        return Response(body=index_path.read_bytes(), content_type="text/html")

    def setup_static(self) -> Path:
        """Set path for static js files and correct return mimetypes.

        :returns: Path to static js files folder
        """
        mimetypes.init()
        mimetypes.types_map[".js"] = "application/javascript"
        mimetypes.types_map[".js.map"] = "application/json"
        mimetypes.types_map[".svg"] = "image/svg+xml"
        mimetypes.types_map[".css"] = "text/css"
        mimetypes.types_map[".css.map"] = "application/json"
        LOG.debug("static paths for SPA set.")
        return self.path / "static"


# Private functions shared between handlers
async def _extract_xml_upload(req: Request, extract_one: bool = False) -> List[Tuple[str, str]]:
    """Extract submitted xml-file(s) from multi-part request.

    Files are sorted to spesific order by their schema priorities (e.g.
    submission should be processed before study).

    :param req: POST request containing "multipart/form-data" upload
    :raises: HTTPBadRequest if request is not valid for multipart or multiple files sent. HTTPNotFound if
    schema was not found.
    :returns: content and schema type for each uploaded file, sorted by schema
    type.
    """
    files: List[Tuple[str, str]] = []
    try:
        reader = await req.multipart()
    except AssertionError:
        reason = "Request does not have valid multipart/form content"
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)
    while True:
        part = await reader.next()
        # Following is probably error in aiohttp type hints, fixing so
        # mypy doesn't complain about it. No runtime consequences.
        part = cast(BodyPartReader, part)
        if not part:
            break
        if extract_one and files:
            reason = "Only one file can be sent to this endpoint at a time."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if part.name:
            schema_type = part.name.lower()
            if schema_type not in schema_types:
                reason = f"Specified schema {schema_type} was not found."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)
            data = []
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                data.append(chunk)
            xml_content = "".join(x.decode("UTF-8") for x in data)
            files.append((xml_content, schema_type))
            LOG.debug(f"processed file in {schema_type}")
    return sorted(files, key=lambda x: schema_types[x[1]]["priority"])
