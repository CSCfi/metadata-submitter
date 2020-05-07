import xmltodict
from aiohttp import web

from ..database.db_services import CRUDService, MongoDBService
from ..helpers.logger import LOG, get_attributes
from ..helpers.schema_load import SchemaLoader
from ..helpers.validator import XMLValidator


class SiteHandler:
    """ Backend feature handling, speaks to db via db_service objects"""

    def __init__(self):
        """ Create needed services for connecting to database. """
        self.schema_db_service = MongoDBService("schemas")
        self.submission_db_service = MongoDBService("submissions")
        self.backup_db_service = MongoDBService("backups")

    @staticmethod
    async def extract_submission_from_request(request):
        """
        Extracts xml-files and their types from multi-part form submission. 
        @param request: POST request sent
        @return: List of dictionaries containing type and content for each xml file sent through POST
        """
        submissions = []
        reader = await request.multipart()
        while True:
            part = await reader.next()
            if not part:
                break
            # TODO: test what happens if no name is given
            xml_type = part.name.lower()
            data = []
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                data.append(chunk)
            xml_content = ''.join(x.decode('UTF-8') for x in data)
            submissions.append({xml_type: xml_content})
        return submissions

    def get_actions_from_submission(self, submission):
        pass

    @staticmethod
    def check_if_submission_is_valid(xml_type, xml_content):
        try:
            valid_xml = XMLValidator.validate(xml_content, xml_type, SchemaLoader())
        except ValueError as error:
            reason = f"{error} {xml_type}"
            raise web.HTTPBadRequest(reason=reason)
        if not valid_xml:
            reason = f"Submitted XML file was not valid against schema {xml_type}"
            raise web.HTTPBadRequest(reason=reason)

    async def submit(self, request):
        """
        Handles submission to server
        :param request: POST request sent
        :raises: HTTP Exceptions with status code 201 or 400
        :returns: JSON response with submitted xml_content or validation error
        reason
        """
        submissions = await self.extract_submission_from_request(request)

        if not any("submission" in xml_types for xml_types in submissions):
            reason = "There must be a submission.xml file in submission"
            raise web.HTTPBadRequest(reason=reason)

        # for submission in submissions:
        #    submission_json = xmltodict.parse(xml_content)
        #    backup_json = {"content": xml_content}
        # result = CRUDService.create(self.submission_db_service, schema, submission_json)
        # result = CRUDService.create(self.backup_db_service, schema, backup_json)

        receipt = """<RECEIPT receiptDate = "2014-12-02T16:06:20.871Z" success = "true" >
                         <RUN accession = "ERR049536" alias = "run_1" status = "PRIVATE" />
                         <SUBMISSION accession = "ERA390457" alias = "submission_1" />
                         <ACTIONS>ADD</ACTIONS>
                     </RECEIPT>"""
        raise web.HTTPCreated(body=receipt, content_type="text/xml")
