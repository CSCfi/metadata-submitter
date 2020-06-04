"""Handle HTTP methods for server."""
import json
from collections import Counter
from datetime import datetime
from typing import List, Tuple, cast

from aiohttp import BodyPartReader, web
from aiohttp.web import Request, Response

from ..conf.conf import object_types
from ..helpers.parser import XMLToJSONParser
from .translator import ActionToCRUDTranslator


class RESTApiHandler:
    """Handler for REST API methods."""

    async def get_objects(self, req: Request) -> Response:
        """Get all possible metadata object types from database.

        Basically returns which objects user can submit and query for.
        :param req: GET Request
        :returns JSON list of object types
        """
        types_json = json.dumps(list(object_types.keys()))
        return web.Response(body=types_json, status=200)

    async def get_object(self, req: Request) -> Response:
        """Get one metadata object by its accession id.

        Returns xml object if format query parameter is set, otherwise json.

        :param req: Multi-part POST request
        :returns: JSON or XML response containing metadata object
        """
        translator = ActionToCRUDTranslator()
        accession_id = req.match_info['accessionId']
        schema = req.match_info['schema']
        format = req.query.get("format", "json").lower()
        use_xml, type = (True, "text/xml") if format == "xml" \
            else (False, "application/json")
        object = translator.get_object_with_accession_id(schema, accession_id,
                                                         use_xml)
        return web.Response(body=object, status=200, content_type=type)

    async def post_object(self, req: Request) -> Response:
        """Save metadata object to database.

        If request is xml file upload, it is first parsed to json. Otherwise
        json from body is used.

        :param req: POST request
        :returns: JSON response containing accessionId for submitted object
        """
        translator = ActionToCRUDTranslator()
        type = req.match_info['schema']
        if req.content_type == "multipart/form-data":
            files = await _extract_xml_upload(req)
            content_xml, _ = files[0]
            parser = XMLToJSONParser()
            content_json = parser.parse(type, content_xml)
            accession_id = translator.add(content_json, type, content_xml)
        else:
            content_json = await req.json()
            accession_id = translator.add(content_json, type)
        body = json.dumps({"accessionId": accession_id})
        return web.Response(body=body, status=201,
                            content_type="application/json")


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
        types = Counter(file[1] for file in files)

        if "submission" not in types:
            reason = "There must be a submission.xml file in submission."
            raise web.HTTPBadRequest(reason=reason)

        if types["submission"] > 1:
            reason = "You should submit only one submission.xml file."
            raise web.HTTPBadRequest(reason=reason)

        parser = XMLToJSONParser()
        submission_xml = files[0][0]
        submission_json = parser.parse("submission", submission_xml)

        successful: List = []
        unsuccessful: List = []

        translator = ActionToCRUDTranslator()
        for action_info in submission_json["action_infos"]:
            try:
                action = action_info["action"]
                if getattr(translator, action)(action_info):
                    successful.append(action)
                else:
                    unsuccessful.append(action)
                    break
            except AttributeError as error:
                reason = (f"Unfortunately this feature has not yet been "
                          f"implemented. More info: {error}")
                raise web.HTTPBadRequest(reason=reason)

        receipt = self.generate_receipt(successful, unsuccessful)
        return web.Response(body=receipt, status=201, content_type="text/xml")

    async def validate(self, req: Request) -> Response:
        """Validate xml file sent to endpoint."""
        return web.Response(text="Validated!")

    @staticmethod
    def generate_receipt(successful: List, unsuccessful: List) -> str:
        """Generate receipt XML after all submissions have ran through.

        Not currently valid receipt (against schema), will be changed later.

        :param successful: Successful submissions and their info
        :param unsuccessful: Unsuccessful submissions and their info
        :returns: XML-based receipt
        """
        date = datetime.now()
        infos = "<SUBMISSION accession=\"ERA521986\" alias=\"submission_1\" />"
        receipt = (f"<RECEIPT receiptDate = \"{date}\" success = \"true\" >"
                   f"{infos}"
                   f"</RECEIPT>")
        return receipt


# Private functions shared between handlers
async def _extract_xml_upload(req: Request) -> List[Tuple]:
    """Extract submitted xml-file(s) from multi-part request.

    :param req: POST request containing "multipart/form-data" upload
    :returns: content and type for each uploaded file, sorted by type
    """
    files: List[Tuple] = []
    reader = await req.multipart()
    while True:
        part = await reader.next()
        # Following is probably error in aiohttp type hints, fixing so
        # mypy doesn't complain about it. No runtime consequences.
        part = cast(BodyPartReader, part)
        if not part:
            break
        xml_type = part.name.lower()
        if xml_type not in object_types:
            raise web.HTTPBadRequest(reason="Not ok type")
        data = []
        while True:
            chunk = await part.read_chunk()
            if not chunk:
                break
            data.append(chunk)
        xml_content = ''.join(x.decode('UTF-8') for x in data)
        files.append((xml_content, xml_type))
    return sorted(files, key=lambda x: object_types[x[1]])
