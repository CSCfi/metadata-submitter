"""Handle translating API endpoint functionalities to CRUD operations."""
from typing import Dict

from aiohttp import web
from bson import json_util
from pymongo import errors

from ..database.db_service import DBService
from ..helpers.logger import LOG


class ActionToCRUDTranslator:
    """Wrapper that turns submission actions to CRUD operations."""

    def __init__(self) -> None:
        """Create needed services for connecting to database."""
        self.submission_db_service = DBService("submissions")
        self.backup_db_service = DBService("backups")

    def add(self, content_json: Dict, type: str, content_xml: str = None) -> \
            Dict:
        """Submit new metadata object.

        :param target: Attributes for add action, e.g. information about which
        file to save to database
        :param submissions: Submission xml data grouped by schemas and
        filenames
        :raises: HTTP error when inserting file to database fails
        :returns Json containing accession id for object that has been
        inserted to database
        """
        try:
            self.submission_db_service.create(type, content_json)
        except errors.PyMongoError as error:
            LOG.info(f"error, reason: {error}")
            reason = "Error happened when saving file to database."
            raise web.HTTPBadRequest(reason=reason)

        if content_xml:
            backup_json = {"accessionId": content_json["accessionId"],
                           "content": content_xml}
            try:
                self.backup_db_service.create(type, backup_json)
            except errors.PyMongoError as error:
                LOG.info(f"error, reason: {error}")
                reason = "Error happened when backing up to database."
                raise web.HTTPBadRequest(reason=reason)
            LOG.info("Inserting file to database succeeded")
        return content_json["accessionId"]

    def get_object_with_accession_id(self, schema: str, accession_id: str,
                                     return_xml: bool) -> Dict:
        """Get object from database according to given accession id.

        param: accessionId: Accession id for object to be searched
        raises: HTTPBadRequest if error happened when connection to database
        and HTTPNotFound error if file with given accession id is not found.
        returns: JSON containing all objects.
        """
        try:
            if return_xml:
                data_raw = self.backup_db_service.read(schema, accession_id)
                data = list(data_raw)[0]["content"]
            else:
                data_raw = self.submission_db_service.read(schema,
                                                           accession_id)
                data = json_util.dumps(data_raw)
            if data_raw.retrieved == 0:
                raise web.HTTPNotFound
            return data

        except errors.PyMongoError as error:
            LOG.info(f"error, reason: {error}")
            reason = "Error happened while getting file from database."
            raise web.HTTPBadRequest(reason=reason)
