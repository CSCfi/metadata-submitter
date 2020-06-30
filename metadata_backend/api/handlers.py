"""Handle HTTP methods for server."""
import json
import mimetypes
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple, Union, cast
from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError

from aiohttp import BodyPartReader, web
from aiohttp.web import Request, Response
from xmlschema import XMLSchemaValidationError

from ..conf.conf import schema_types
from ..helpers.parser import XMLToJSONParser
from ..helpers.schema_loader import SchemaLoader, SchemaNotFoundException
from .operators import Operator, XMLOperator


class RESTApiHandler:
    """Handler for REST API methods."""

    async def get_schema_types(self, req: Request) -> Response:
        """Get all possible metadata schema types from database.

        Basically returns which objects user can submit and query for.
        :param req: GET Request
        :returns JSON list of schema types
        """
        types_json = json.dumps([x["description"] for x in
                                 schema_types.values()])
        return web.Response(body=types_json, status=200)

    async def get_object(self, req: Request) -> Response:
        """Get one metadata object by its accession id.

        Returns original xml object from backup if format query parameter is
        set, otherwise json.

        :param req: GET request
        :returns: JSON or XML response containing metadata object
        """
        accession_id = req.match_info['accessionId']
        schema_type = req.match_info['schema']
        if schema_type not in schema_types.keys():
            reason = f"Theres no schema {schema_type}"
            raise web.HTTPNotFound(reason=reason)
        format = req.query.get("format", "json").lower()
        operator = XMLOperator() if format == "xml" else Operator()
        data, content_type = await operator.read_metadata_object(schema_type,
                                                                 accession_id)
        return web.Response(body=data, status=200, content_type=content_type)

    async def post_object(self, req: Request) -> Response:
        """Save metadata object to database.

        :param req: POST request
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info['schema']
        if schema_type not in schema_types.keys():
            reason = f"Theres no schema {schema_type}"
            raise web.HTTPNotFound(reason=reason)
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            files = await _extract_xml_upload(req, extract_one=True)
            content, _ = files[0]
            operator = XMLOperator()
        else:
            content = await req.json()
            operator = Operator()
        accession_id = await operator.create_metadata_object(schema_type,
                                                             content)
        body = json.dumps({"accessionId": accession_id})
        return web.Response(body=body, status=201,
                            content_type="application/json")

    async def query_objects(self, req: Request) -> Response:
        """Query metadata objects from database.

        :param req: GET request with query parameters (can be empty).
        :returns: Query results as JSON
        """
        schema_type = req.match_info['schema']
        if schema_type not in schema_types.keys():
            reason = f"Theres no schema {schema_type}"
            raise web.HTTPNotFound(reason=reason)
        format = req.query.get("format", "json").lower()
        if format == "xml":
            reason = "xml-formatted query results are not supported"
            raise web.HTTPBadRequest(reason=reason)
        result = Operator().query_metadata_database(schema_type,
                                                    req.query)
        return web.Response(body=result, status=200,
                            content_type="application/json")

    async def delete_object(self, req: Request) -> Response:
        """Delete metadata object from database.

        :param req: POST request
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info['schema']
        if schema_type not in schema_types.keys():
            reason = f"Theres no schema {schema_type}"
            raise web.HTTPBadRequest(reason=reason)
        accession_id = req.match_info['accessionId']
        Operator().delete_metadata_object(schema_type, accession_id)
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
            raise web.HTTPBadRequest(reason=reason)

        if schema_types["submission"] > 1:
            reason = "You should submit only one submission.xml file."
            raise web.HTTPBadRequest(reason=reason)

        submission_xml = files[0][0]
        submission_json = XMLToJSONParser().parse("submission", submission_xml)
        # Check what actions should be performed, collect them to dictionary
        actions = {}
        for action_set in submission_json["actions"]['action']:
            for action, attr in action_set.items():
                if not attr:
                    reason = (f"""You also need to provide necessary
                                  information for submission action.
                                  Now {action} was provided without any
                                  extra information.""")
                    raise web.HTTPBadRequest(reason=reason)
                actions[attr["schema"]] = action
        # Go through parsed files and do the actual action
        # Only "add" action is supported for now.
        results: List[Dict] = []
        for file in files:
            content_xml = file[0]
            schema_type = file[1]
            if schema_type == "submission":
                continue  # No need to use submission xml
            action = actions[schema_type]
            if action == "add":
                results.append({
                    "accessionId":
                    XMLOperator().create_metadata_object(schema_type,
                                                         content_xml),
                    "schema": schema_type
                })
            else:
                reason = f"action {action} is not supported yet"
                raise web.HTTPBadRequest(reason=reason)
        body = json.dumps(results)
        return web.Response(body=body, status=201,
                            content_type="application/json")

    async def validate(self, req: Request) -> Response:
        """Validate xml file sent to endpoint.

        :param req: Multipart POST request with submission.xml and files
        :raises: HTTP Exception with status code 400 if schema load fails
        :returns: JSON response indicating if validation was successful or not
        """
        files = await _extract_xml_upload(req, extract_one=True)
        xml_content, schema_type = files[0]
        try:
            schema = SchemaLoader().get_schema(schema_type)
            schema.validate(xml_content)

        except SchemaNotFoundException as error:
            reason = f"{error} ({schema_type})"
            raise web.HTTPBadRequest(reason=reason)

        except ParseError as error:
            detail = f"Faulty XML file was given.\nERROR: {error}"
            body = json.dumps({"isValid": False, "detail": detail})
            return web.Response(body=body,
                                content_type="application/json")

        except XMLSchemaValidationError as error:
            # Parsing reason and instance from the validation error message
            reason = error.reason
            instance = ElementTree.tostring(error.elem, encoding="unicode")
            body = json.dumps({"isValid": False, "detail":
                              {"reason": reason, "instance": instance}})
            return web.Response(body=body,
                                content_type="application/json")
        body = json.dumps({"isValid": True})
        return web.Response(body=body, content_type="application/json")


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
        return Response(body=index_path.read_bytes(),
                        content_type="text/html")

    def setup_static(self) -> Path:
        """Set path for static js files and correct return mimetypes.

        :returns: Path to static js files folder
        """
        mimetypes.init()
        mimetypes.types_map[".js"] = "application/javascript"
        mimetypes.types_map[".js.map"] = "application/json"
        return self.path / "static"


# Private functions shared between handlers
async def _extract_xml_upload(req: Request, extract_one: bool = False
                              ) -> List[Tuple[str, str]]:
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
            raise web.HTTPBadRequest(reason=reason)
        schema_type = part.name.lower()
        if schema_type not in schema_types:
            reason = f"Theres no schema {schema_type}"
            raise web.HTTPNotFound(reason=reason)
        data = []
        while True:
            chunk = await part.read_chunk()
            if not chunk:
                break
            data.append(chunk)
        xml_content = ''.join(x.decode('UTF-8') for x in data)
        files.append((xml_content, schema_type))
    return sorted(files, key=lambda x: schema_types[x[1]]["priority"])
