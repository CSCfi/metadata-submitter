"""Handle HTTP methods for server."""
import json
import mimetypes
from collections import Counter
from math import ceil
from pathlib import Path
from typing import Dict, List, Tuple, Union, cast

from aiohttp import BodyPartReader, web
from aiohttp.web import Request, Response
from jsonpatch import JsonPatch
from xmlschema import XMLSchemaException

from ..conf.conf import schema_types
from ..helpers.logger import LOG
from ..helpers.parser import XMLToJSONParser
from ..helpers.schema_loader import JSONSchemaLoader, SchemaNotFoundException, XMLSchemaLoader
from ..helpers.validator import JSONValidator, XMLValidator
from .operators import FolderOperator, Operator, XMLOperator


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

    def _header_links(self, url: str, page: int, size: int, total_objects: int) -> Dict[str, str]:
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
        link_headers = {"Link": f"{links}"}
        LOG.debug("Link headers created")
        return link_headers

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
                reason = f"{param_name} must a number, now it was " f"{req.query.get(param_name)}"
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
        data, page_num, page_size, total_objects = await Operator(db_client).query_metadata_database(
            collection, req.query, page, per_page
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
        LOG.info(f"Querying for objects in {collection} " f"resulted in {total_objects} objects ")
        return web.Response(body=result, status=200, headers=link_headers, content_type="application/json")

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
        :returns: JSON or XML response containing metadata object
        """
        accession_id = req.match_info["accessionId"]
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        req_format = req.query.get("format", "json").lower()
        db_client = req.app["db_client"]
        operator = XMLOperator(db_client) if req_format == "xml" else Operator(db_client)
        data, content_type = await operator.read_metadata_object(collection, accession_id)
        data = data if req_format == "xml" else json.dumps(data)
        LOG.info(f"GET object with accesssion ID {accession_id} " f"from schema {collection}.")
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
            JSONValidator(content, schema_type).validate
            operator = Operator(db_client)
        accession_id = await operator.create_metadata_object(collection, content)
        body = json.dumps({"accessionId": accession_id})
        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = {"Location": f"{url}{accession_id}"}
        LOG.info(f"POST object with accesssion ID {accession_id} " f"in schema {collection} was successful.")
        return web.Response(body=body, status=201, headers=location_headers, content_type="application/json")

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
        :returns: HTTP No Content response
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        accession_id = req.match_info["accessionId"]
        db_client = req.app["db_client"]
        accession_id = await Operator(db_client).delete_metadata_object(collection, accession_id)
        LOG.info(f"DELETE object with accession ID {accession_id} " f"in schema {collection} was successful.")
        return web.Response(status=204)

    async def put_object(self, req: Request) -> Response:
        """Replace metadata object in database.

        For JSON request body we validate that it consists of all the
        required fields before replacing in the DB.

        :param req: PUT request
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
            JSONValidator(content, schema_type).validate
            operator = Operator(db_client)
        accession_id = await operator.replace_metadata_object(collection, accession_id, content)
        body = json.dumps({"accessionId": accession_id})
        LOG.info(f"PUT object with accession ID {accession_id} " f"in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def patch_object(self, req: Request) -> Response:
        """Update metadata object in database.

        We do not support patch for XML.

        :param req: PATCH request
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
        accession_id = await operator.update_metadata_object(collection, accession_id, content)
        body = json.dumps({"accessionId": accession_id})
        LOG.info(f"PATCH object with accession ID {accession_id} " f"in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def get_folders(self, req: Request) -> Response:
        """Get all possible object folders from database.

        :param req: GET Request
        :returns: JSON list of folders available for the user
        """
        db_client = req.app["db_client"]
        operator = FolderOperator(db_client)
        folders = await operator.query_folders({})
        body = json.dumps({"folders": folders})
        LOG.info(f"GET folders. Retrieved {len(folders)} folders.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def post_folder(self, req: Request) -> Response:
        """Save object folder to database.

        :param req: POST request
        :returns: JSON response containing folder ID for submitted folder
        """
        db_client = req.app["db_client"]
        content = await self._get_data(req)
        JSONValidator(content, "folders").validate
        operator = FolderOperator(db_client)
        folder = await operator.create_folder(content)
        body = json.dumps({"folderId": folder})
        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = {"Location": f"{url}/{folder}"}
        LOG.info(f"POST new folder with ID {folder} was successful.")
        return web.Response(body=body, status=201, headers=location_headers, content_type="application/json")

    async def get_folder(self, req: Request) -> Response:
        """Get one object folder by its folder id.

        :param req: GET request
        :raises: HTTP 404 if folder not found and 400 if something else fails
        :returns: JSON response containing object folder
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]
        operator = FolderOperator(db_client)
        folder = await operator.read_folder(folder_id)
        LOG.info(f"GET folder with folder ID {folder_id} was successful.")
        return web.Response(body=json.dumps(folder), status=200, content_type="application/json")

    async def patch_folder(self, req: Request) -> Response:
        """Update object folder with a specific folder id.

        :param req: PATCH request
        :raises: HTTP 400 if something fails during processing the request
        :returns: JSON response containing folder ID for updated folder
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]

        # Check patch operations in request are valid
        patch_ops = await self._get_data(req)
        allowed_paths = ["/name", "/description", "/metadataObjects"]
        for op in patch_ops:
            if all(i not in op["path"] for i in allowed_paths):
                reason = f"Request contains '{op['path']}' key that cannot be" " updated to folders."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
        patch = JsonPatch(patch_ops)

        operator = FolderOperator(db_client)
        folder = await operator.update_folder(folder_id, patch)
        body = json.dumps({"folderId": folder})
        LOG.info(f"PATCH folder with ID {folder} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_folder(self, req: Request) -> Response:
        """Delete object folder from database.

        :param req: DELETE request
        :returns: HTTP No Content response
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]
        operator = FolderOperator(db_client)
        folder = await operator.delete_folder(folder_id)
        LOG.info(f"DELETE folder with ID {folder} was successful.")
        return web.Response(status=204)


class SubmissionAPIHandler:
    """Handler for non-rest API methods."""

    async def submit(self, req: Request) -> Response:
        """Handle submission.xml containing submissions to server.

        First submission info is parsed and then for every action in submission
        (such as "add", or "modify") corresponding operation is performed.
        Finally submission info itself is added.

        :param req: Multipart POST request with submission.xml and files
        :raises: HTTP Exceptions with status code 201 or 400
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
        actions = {}
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
                actions[attr["schema"]] = action
        # Go through parsed files and do the actual action
        # Only "add" action is supported for now.
        results: List[Dict] = []
        db_client = req.app["db_client"]
        for file in files:
            content_xml = file[0]
            schema_type = file[1]
            if schema_type == "submission":
                LOG.debug("file has schema of submission type, continuing ...")
                continue  # No need to use submission xml
            action = actions[schema_type]
            if action == "add":
                results.append(
                    {
                        "accessionId": await XMLOperator(db_client).create_metadata_object(schema_type, content_xml),
                        "schema": schema_type,
                    }
                )
                LOG.debug(f"added some content in {schema_type} ...")
            else:
                reason = f"action {action} is not supported yet"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
        body = json.dumps(results)
        LOG.info(f"Processed a submission of {len(results)} actions.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def validate(self, req: Request) -> Response:
        """Validate xml file sent to endpoint.

        :param req: Multipart POST request with submission.xml and files
        :raises: HTTP Exception with status code 400 if schema load fails
        :returns: JSON response indicating if validation was successful or not
        """
        files = await _extract_xml_upload(req, extract_one=True)
        xml_content, schema_type = files[0]

        try:
            schema = XMLSchemaLoader().get_schema(schema_type)
            LOG.info(f"{schema_type} schema loaded.")
            validator = XMLValidator(schema, xml_content)

        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} ({schema_type})"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        return web.Response(body=validator.resp_body, content_type="application/json")


class StaticHandler:
    """Handler for static routes, mostly frontend and 404."""

    def __init__(self, frontend_static_files: Path) -> None:
        """Initialize path to frontend static files folder."""
        self.path = frontend_static_files

    async def frontend(self, req: Request) -> Response:
        """Serve requests related to frontend SPA.

        :param req: GET request
        :raises: HTTP Exceptions if error happens
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
        LOG.debug("static paths for SPA set.")
        return self.path / "static"


# Private functions shared between handlers
async def _extract_xml_upload(req: Request, extract_one: bool = False) -> List[Tuple[str, str]]:
    """Extract submitted xml-file(s) from multi-part request.

    Files are sorted to spesific order by their schema priorities (e.g.
    submission should be processed before study).

    :param req: POST request containing "multipart/form-data" upload
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
