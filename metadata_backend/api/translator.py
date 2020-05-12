"""Handle translating API endpoint functionalities to CRUD operations."""

from typing import Dict

from ..database.db_services import CRUDService, DBService
from ..helpers.logger import LOG
from .parser import SubmissionXMLToJSONParser


class ActionToCRUDTranslator:
    """Wrapper that turns submission actions to CRUD operations."""

    def __init__(self, submissions: Dict) -> None:
        """Create needed services for connecting to database.

        :param submissions: Original XML types and contents for each submitted
        file
        """
        self.submission_db_service = DBService("submissions")
        self.backup_db_service = DBService("backups")
        self.parser = SubmissionXMLToJSONParser()
        self.submissions = submissions

    def add(self, target) -> None:
        """Submit new metadata object with ADD action.

        :param target: Attributes for action, e.g. information about what to
        process in action
        """
        xml_type = target["schema"]
        content_xml = self.submissions[xml_type]
        content_json = self.parser.parse(xml_type, content_xml)
        backup_json = {"accession": content_json["accession"],
                       "alias": content_json["alias"],
                       "content": content_xml}
        CRUDService.create(self.submission_db_service, xml_type, content_json)
        LOG.info(f"{xml_type} added to submission database")
        CRUDService.create(self.backup_db_service, xml_type, backup_json)
        LOG.info(f"{xml_type} added to backup database")

    def generate_receipt(self) -> str:
        """Generate receipt XML all submissions are ran through.

        Returned receipt is currently just a placeholder.
        :returns: XML-based receipt
        """
        receipt = """<RECEIPT receiptDate = "2014-12-02T16:06:20.871Z" \
                    success = "true" >
                        <RUN accession = "ERR049536" alias = "run_1" \
                        status = "PRIVATE" />
                        <SUBMISSION accession = "ERA390457" alias = \
                        "submission_1" />
                        <ACTIONS>ADD</ACTIONS>
                    </RECEIPT>"""
        return receipt
