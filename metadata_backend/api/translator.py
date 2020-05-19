"""Handle translating API endpoint functionalities to CRUD operations."""

from typing import Dict

from aiohttp import web
from pymongo import errors

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

    def add(self, target: Dict) -> None:
        """Submit new metadata object with ADD action.

        :param target: Attributes for add action, e.g. information on which
        file to save to database
        :raises: HTTP error when inserting file to database fails
        """
        xml_type = target["schema"]
        source = target["source"]
        content_xml = self.submissions[xml_type][source]
        content_json = self.parser.parse(xml_type, content_xml)
        backup_json = {"accession": content_json["accession"],
                       "alias": content_json["alias"],
                       "content": content_xml}
        try:
            CRUDService.create(self.submission_db_service, xml_type,
                               content_json)
        except errors.PyMongoError as error:
            LOG.info(f"error, reason: {error}")
            reason = f"Error happened when saving file {source} to database."
            raise web.HTTPBadRequest(reason=reason)

        try:
            CRUDService.create(self.backup_db_service, xml_type, backup_json)
        except errors.PyMongoError as error:
            LOG.info(f"error, reason: {error}")
            reason = f"Error happened when backing up {source} to database."
            raise web.HTTPBadRequest(reason=reason)
        LOG.info(f"Inserting file {source} to database succeeded")
