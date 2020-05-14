"""Handle translating API endpoint functionalities to CRUD operations."""

from typing import Dict

from ..database.db_services import CRUDService, DBService
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

    def add(self, target) -> bool:
        """Submit new metadata object with ADD action.

        :param target: Attributes for action, e.g. information about what to
        process in action
        :returns: True
        """
        xml_type = target["schema"]
        content_xml = self.submissions[xml_type]
        content_json = self.parser.parse(xml_type, content_xml)
        backup_json = {"accession": content_json["accession"],
                       "alias": content_json["alias"],
                       "content": content_xml}
        CRUDService.create(self.submission_db_service, xml_type, content_json)
        CRUDService.create(self.backup_db_service, xml_type, backup_json)
        return True
