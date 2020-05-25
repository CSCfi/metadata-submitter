"""Handle translating API endpoint functionalities to CRUD operations."""

from typing import Dict

from aiohttp import web
from bson import json_util
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
        """Submit new metadata object (ADD action in submission.xml).

        :param target: Attributes for add action, e.g. information about which
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

    def get_all(self) -> Dict:
        """Get all objects from the database.

        Objects are grabbed from all collections with empty query,
        which in MongoDB returns everything from that collection.

        This will load all the objects into program memory and should
        since be refactored at some point.

        returns: JSON containing all objects.
        """
        schemas = ["study", "sample", "experiment", "run",
                   "analysis", "dac", "policy", "dataset", "project"]

        objects = []
        for schema in schemas:
            objects.extend(list(CRUDService.read(self.submission_db_service,
                                                 schema, {})))
        return json_util.dumps(objects)
