"""Operators for handling database-related operations."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple, Union

from aiohttp import web
from bson import json_util
from pymongo import errors
from pymongo.cursor import Cursor

from ..database.db_service import DBService
from ..helpers.logger import LOG


class BaseOperator(ABC):
    """Base class for operators, implements shared functionality.

    :param ABC: The abstract base class
    """

    def __init__(self, db_type: str, content_type: str) -> None:
        """Init needed variables, must be given by subclass."""
        self.db_service = DBService(db_type)
        self.content_type = content_type

    def read_metadata_object(self, type: str, accession_id:
                             str) -> Tuple[Union[Dict, str], str]:
        """Read metadata object from database.

        :param type: Type of the object to read.
        :param accession_id: Accession Id of the object to read.
        """
        try:
            data_raw = self.db_service.read(type, accession_id)
            if not data_raw:
                raise web.HTTPNotFound
            data = self._format_read_data(data_raw)
        except errors.PyMongoError as error:
            LOG.info(f"error, reason: {error}")
            reason = f"Error happened while getting file: {error}"
            raise web.HTTPBadRequest(reason=reason)
        return data, self.content_type

    def create_metadata_object(self, type: str, data: Dict) -> None:
        """Create new object to database.

        Formats data to specific format and adds accession_id.

        :param type: Type of the object to read.
        :param data: Data to be saved to database.
        :returns: Accession id for the object created.
        """
        try:
            self.db_service.create(type, data)
        except errors.PyMongoError as error:
            LOG.info(f"error, reason: {error}")
            reason = f"Error happened while getting file: {error}"
            raise web.HTTPBadRequest(reason=reason)
        LOG.info(f"Inserting file to database succeeded: {type}, "
                 f"{self.content_type}")

    @abstractmethod
    def _format_read_data(self, data_raw: Any) -> Any:
        """Format data to specific format, must be implemented by subclass."""


class Operator(BaseOperator):
    """Default operator class for handling database operations.

    Operations are implemented with json format.
    """

    def __init__(self) -> None:
        """Initialize database and content-type."""
        super().__init__("objects", "application/json")

    def _format_read_data(self, data_raw: Union[Dict, Cursor]) -> Dict:
        """Get json content from given mongodb data.

        :param data_raw: Data from mongodb query, can contain multiple results
        :returns: Mongodb query result dumped as json
        """
        return json_util.dumps(data_raw)


class XMLOperator(BaseOperator):
    """Alternative operator class for handling database operations.

    Operations are implemented with XML format.
    """

    def __init__(self) -> None:
        """Initialize database and content-type."""
        super().__init__("backups", "text/xml")

    def _format_read_data(self, data_raw: Dict) -> str:
        """Get xml content from given mongodb data.

        :param data_raw: Data from mongodb query with single result.
        :returns: XML content
        """
        return data_raw["content"]
