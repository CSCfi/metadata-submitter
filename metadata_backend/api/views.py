import xmltodict
from aiohttp import web

from ..database.db_services import CRUDService, MongoDBService
from ..helpers.schema_load import SchemaLoader
from ..helpers.validator import XMLValidator
from ..helpers.logger import LOG


class SubmissionActionsToCRUD:
    """
    Results submission actions to CRUD requests.
    """
    # TODO: decide whether to raise error and exit if one fails or just raise errors?
    
    def __init__(self, submissions):
        """
        Create needed services for connecting to database.
        :@param submissions: all submissions submitted via xml
        """
        self.submissions = submissions
        self.submission_db_service = MongoDBService("submissions")
        self.backup_db_service = MongoDBService("backups")
        
    def generate_accession_number_and_alias(self):
        """
        random stuff
        @return: 
        """
        return (1,2)
        

    def add(self, data):
        s = data["schema"]
        d = self.submissions[s]
        
        check_if_submission_is_valid(s, d)
        numbers = self.generate_accession_number_and_alias()
        submission_json = xmltodict.parse(d)
        backup_json = {"accession": numbers[0],
                       "alias": numbers[1],
                       "content": d}
        result = CRUDService.create(self.submission_db_service, s, submission_json)
        result = CRUDService.create(self.backup_db_service, s, backup_json)


    def modify(self, data):
        LOG.info("modifying stuff!")

        numbers = self.generate_accession_number_and_alias()
class SiteHandler:
    """ Backend feature handling, speaks to db via db_service objects"""

    @staticmethod
    async def extract_submission_from_request(request):
        """
        Extracts xml-files and their types from multi-part form submission. 
        @param request: POST request sent
        @return: List of dictionaries containing type and content for each xml file sent through POST
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

    def get_actions_from_submission_xml(self, submission_content):
        """
        Parses actions from submission.xml
        @param submission_content: XML string containing submission.xml with actions
        @return: dictionary containing actions as keys and list with info of data to perform
        action against as values
        """
        check_if_submission_is_valid("submission", submission_content)
        submission_as_json = xmltodict.parse(submission_content)
        action_list = submission_as_json["SUBMISSION_SET"]["SUBMISSION"]["ACTIONS"]["ACTION"]
        actions = {}
        for action_dict in action_list:
            for action, data in action_dict.items():
                if data:
                    action_info = {}
                    for attribute, value in data.items():
                        action_info[attribute[1:]] = value
                    action = action.lower()
                    if action not in actions:
                        actions[action] = []
                    actions[action].append(action_info)
        return actions

    async def submit(self, request):
        """
        Handles submission to server
        :param request: POST request sent
        :raises: HTTP Exceptions with status code 201 or 400
        :returns: JSON response with submitted xml_content or validation error
        reason
        """
        submissions = await self.extract_submission_from_request(request)

        # TODO: allow submissions without xml file when using correct parameters (this helps submitting from frontend)
        if "submission" not in submissions:
            reason = "There must be a submission.xml file in submission"
            raise web.HTTPBadRequest(reason=reason)

        actions = self.get_actions_from_submission_xml(submissions["submission"])
        
        submitter = SubmissionActionsToCRUD(submissions)

        for action, li in actions.items():
            for l in li:
                getattr(submitter, action)(l)

        receipt = """<RECEIPT receiptDate = "2014-12-02T16:06:20.871Z" success = "true" >
                         <RUN accession = "ERR049536" alias = "run_1" status = "PRIVATE" />
                         <SUBMISSION accession = "ERA390457" alias = "submission_1" />
                         <ACTIONS>ADD</ACTIONS>
                     </RECEIPT>"""
        raise web.HTTPCreated(body=receipt, content_type="text/xml")


def check_if_submission_is_valid(xml_type, xml_content):
    try:
        valid_xml = XMLValidator.validate(xml_content, xml_type, SchemaLoader())
    except ValueError as error:
        reason = f"{error} {xml_type}"
        raise web.HTTPBadRequest(reason=reason)
    if not valid_xml:
        reason = f"Submitted XML file was not valid against schema {xml_type}"
        raise web.HTTPBadRequest(reason=reason)
