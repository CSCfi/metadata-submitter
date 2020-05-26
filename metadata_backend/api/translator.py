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

    def __init__(self) -> None:
        """Create needed services for connecting to database."""
        self.submission_db_service = DBService("submissions")
        self.backup_db_service = DBService("backups")
        self.parser = SubmissionXMLToJSONParser()

    def add(self, target: Dict, submissions: Dict) -> Dict:
        """Submit new metadata object (ADD action in submission.xml).

        :param target: Attributes for add action, e.g. information about which
        file to save to database
        :param submissions: Submission xml data grouped by schemas and
        filenames
        :raises: HTTP error when inserting file to database fails
        :returns Json containing accession id for object that has been
        inserted to database
        """
        xml_type = target["schema"]
        source = target["source"]
        content_xml = submissions[xml_type][source]
        content_json = self.parser.parse(xml_type, content_xml)
        backup_json = {"accessionId": content_json["accessionId"],
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
        return content_json["accessionId"]

    def get_object_with_accessionId(self, schema: str, accessionId: str,
                                    return_xml: bool) -> Dict:
        """Get object from database according to given accession id.

        param: accessionId: Accession id for object to be searched
        raises: HTTPBadRequest if error happened when connection to database
        and HTTPNotFound error if file with given accession id is not found.
        returns: JSON containing all objects.
        """
        try:
            if return_xml:
                data_raw = CRUDService.read(self.backup_db_service, schema,
                                            {"accessionId": accessionId})
                data = list(data_raw)[0]["content"]
            else:
                data_raw = CRUDService.read(self.submission_db_service, schema,
                                            {"accessionId": accessionId})
                data = json_util.dumps(data_raw)

            if data is not None:
                return data

        except errors.PyMongoError as error:
            LOG.info(f"error, reason: {error}")
            reason = "Error happened while getting file from database."
            raise web.HTTPBadRequest(reason=reason)

        raise web.HTTPNotFound
