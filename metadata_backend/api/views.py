"""Handle HTTP methods for server."""
from typing import Dict, Set, List, Tuple

from aiohttp import web
from aiohttp.web import Request

from .parser import SubmissionXMLToJSONParser
from .translator import ActionToCRUDTranslator
from datetime import datetime

from ..helpers.logger import get_attributes, LOG


class SiteHandler:
    """Backend HTTP method handler."""

    @staticmethod
    async def extract_submissions(req: Request) -> Dict[str, List]:
        """Extract submitted xml-files from multi-part request.

        :param request: Multi-part POST request
        :returns: Filename and content for each submitted xml, grouped by
        schemas
        """
        submissions: Dict[str, List] = {}
        reader = await req.multipart()
        while True:
            part = await reader.next()
            if not part:
                break
            xml_type = part.name.lower()
            filename = part.filename
            data = []
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                data.append(chunk)
            xml_content = ''.join(x.decode('UTF-8') for x in data)
            if xml_type not in submissions:
                submissions[xml_type] = []
            submissions[xml_type].append((filename, xml_content))
        return submissions

    def generate_receipt(self, successful_submissions: Set) -> str:
        """Generate receipt XML after all submissions have ran through.

        Not currently valid receipt (against schema), will be changed later.

        :param: Set of succesful submissions
        :returns: XML-based receipt
        """
        date = datetime.now()
        infos = "<SUBMISSION accession=\"ERA521986\" alias=\"submission_1\" />"
        receipt = (f"<RECEIPT receiptDate = \"{date}\" success = \"true\" >"
                   f"{infos}"
                   f"</RECEIPT>")
        return receipt

    async def submit(self, request):
        """Handle submission to server.

        First submission info is parsed and then for every action in submission
        (such as "add", or "modify") corresponding operation is performed.
        Finally submission info itself is added.

        :param request: POST request
        :raises: HTTP Exceptions with status code 201 or 400
        :returns: XML-based receipt from submission
        """
        submissions = await self.extract_submissions(request)

        if "submission" not in submissions:
            reason = "There must be a submission.xml file in submission."
            raise web.HTTPBadRequest(reason=reason)

        if len(submissions["submission"]) > 1:
            reason = "You should submit only one submission.xml file."
            raise web.HTTPBadRequest(reason=reason)

        # parser = SubmissionXMLToJSONParser()
        # translator = ActionToCRUDTranslator(submissions)
        # submission_json = parser.parse("submission", submissions["submission"])

        successful_submissions = set()

        # for action_info in submission_json["action_infos"]:
        #     try:
        #         action = action_info["action"]
        #         if getattr(translator, action)(action_info):
        #             successful_submissions.add(action_info["schema"])

        #     except AttributeError as error:
        #         reason = (f"Unfortunately this feature has not yet been "
        #                   f"implemented. More info: {error}")
        #         raise web.HTTPBadRequest(reason=reason)

        # translator.add({"schema": "submission"})
        receipt = self.generate_receipt(successful_submissions)

        raise web.HTTPCreated(body=receipt, content_type="text/xml")
