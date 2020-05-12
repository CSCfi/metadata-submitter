"""Handle HTTP methods for server."""
from typing import Dict

from aiohttp import web

from .parser import SubmissionXMLToJSONParser
from .translator import ActionToCRUDTranslator


class SiteHandler:
    """Backend HTTP method handler."""

    @staticmethod
    async def extract_submissions_from_request(request) -> Dict[str, str]:
        """Extract xml-files and their types from multi-part request.

        :param request: Multi-part POST request
        :return: List of dictionaries containing type and content for each
        XML file in request
        """
        submissions = {}
        reader = await request.multipart()
        while True:
            part = await reader.next()
            if not part:
                break
            xml_type = part.name.lower()
            data = []
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                data.append(chunk)
            xml_content = ''.join(x.decode('UTF-8') for x in data)
            submissions[xml_type] = xml_content
        return submissions

    async def submit(self, request):
        """Handle submission to server.

        First submission info is parsed and then for every action in submission
        (such as "add", or "modify") corresponding operation is performed.
        Finally submission info itself is added.

        :param request: POST request
        :raises: HTTP Exceptions with status code 201 or 400
        :returns: XML-based receipt from submission
        """
        submissions = await self.extract_submissions_from_request(request)

        if "submission" not in submissions:
            reason = "There must be a submission.xml file in submission"
            raise web.HTTPBadRequest(reason=reason)

        parser = SubmissionXMLToJSONParser()
        translator = ActionToCRUDTranslator(submissions)
        submission_json = parser.parse("submission", submissions["submission"])

        for action_info in submission_json["action_infos"]:
            try:
                action = action_info["action"]
                getattr(translator, action)(action_info)
            except AttributeError as error:
                reason = (f"Unfortunately this feature has not yet been "
                          f"implemented. More info: {error}")
                raise web.HTTPBadRequest(reason=reason)

        translator.add({"schema": "submission"})

        raise web.HTTPCreated(body=translator.generate_receipt(),
                              content_type="text/xml")
