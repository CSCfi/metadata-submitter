"""Operators for handling database-related operations."""
import re
import secrets
import string
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Tuple, Union

from aiohttp import web
from bson import json_util
from dateutil.relativedelta import relativedelta
from multidict import MultiDictProxy
from pymongo.cursor import Cursor
from pymongo.errors import ConnectionFailure, OperationFailure

from ..conf.conf import query_map
from ..database.db_service import DBService
from ..helpers.logger import LOG
from ..helpers.parser import XMLToJSONParser


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
        :raises: 400 if reading was not succesful, 404 if no data found
        """
        try:
            data_raw = self.db_service.read(type, accession_id)
            if not data_raw:
                raise web.HTTPNotFound
            data = self._format_read_data(type, data_raw)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            raise web.HTTPBadRequest(reason=reason)
        return data, self.content_type

    def create_metadata_object(self, type: str,
                               data: Union[Dict, str]) -> str:
        """Create new object and add it to database.

        :param type: Type of the object to be added.
        :param data: Data to be saved to database.
        :returns: Accession id for the object added.
        """
        accession_id = self._generate_accession_id()
        self._handle_data_and_add_to_db(type, data, accession_id)
        LOG.info(f"Inserting file to database succeeded: {type}, "
                 f"{self.content_type}")
        return accession_id

    def delete_metadata_object(self, type: str, accession_id: str) -> None:
        """Delete object from database.

        Tries to remove both JSON and original XML from database, passes
        silently if XML doesn't exist.

        :param type: Type of the object to be added.
        :param data: Data to be saved to database.
        :param accession_id: Accession Id of the object to read.
        :raises: 400 if deleting was not succesful
        """
        try:
            Operator().db_service.delete(type, accession_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            raise web.HTTPBadRequest(reason=reason)
        LOG.info(f"{accession_id} successfully deleted from JSON colletion")
        try:
            XMLOperator().db_service.delete(type, accession_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            raise web.HTTPBadRequest(reason=reason)
        LOG.info(f"{accession_id} successfully deleted from XML colletion")

    def _generate_accession_id(self) -> str:
        """Generate random accession id.

        Will be replaced later with external id generator.
        """
        sequence = ''.join(secrets.choice(string.digits) for i in range(16))
        return f"EDAG{sequence}"

    @abstractmethod
    def _format_read_data(self, type: str, data_raw: Any) -> Any:
        """Format data read from db to specific format.

        Must be implemented by subclass.
        """

    @abstractmethod
    def _handle_data_and_add_to_db(self, type: str, data: Any,
                                   accession_id: str) -> None:
        """Handle needed conversions and parsing, then add data to database.

        Must be implemented by subclass.
        """


class Operator(BaseOperator):
    """Default operator class for handling database operations.

    Operations are implemented with json format.
    """

    def __init__(self) -> None:
        """Initialize database and content-type."""
        super().__init__("objects", "application/json")

    def query_metadata_database(self, type: str, que: MultiDictProxy) -> Dict:
        """Create database query based on url query parameters.

        Url queries are mapped to mongodb queries based on query_map in
        apps config.

        :param type: Type of the object to read.
        :param que: Dict containing query information
        :raises: HTTPBadRequest if error happened when connection to database
        and HTTPNotFound error if file with given accession id is not found.
        """
        # Generate mongodb query from query parameters
        mongo_query: Dict = {}
        for query, value in que.items():
            if query in query_map:
                regx = re.compile(f".*{value}.*", re.IGNORECASE)
                if isinstance(query_map[query], dict):
                    # Make or-query for keys in dictionary
                    base = query_map[query]["base"]  # type: ignore
                    if "$or" not in mongo_query:
                        mongo_query["$or"] = []
                    ors = [{f"{base}.{key}": regx} for key
                           in query_map[query]["keys"]]  # type: ignore
                    mongo_query["$or"].extend(ors)
                else:
                    # Query with regex from just one field
                    mongo_query = {query_map[query]: regx}
        try:
            data_raw = self.db_service.query(type, mongo_query)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            raise web.HTTPBadRequest(reason=reason)
        data = self._format_read_data(type, data_raw)
        if data == "[]":
            raise web.HTTPNotFound
        return data

    def _format_read_data(self, type: str,
                          data_raw: Union[Dict, Cursor]) -> Dict:
        """Get json content from given mongodb data.

        Data can be either one result or cursor containing multiple
        results.

        :param type: Type of the object to format
        :param data_raw: Data from mongodb query, can contain multiple results
        :returns: Mongodb query result dumped as json
        """
        formatted: Union[Dict, List]
        if isinstance(data_raw, dict):
            formatted = self._format_single_dict(type, data_raw)
        else:
            formatted = []
            for doc in data_raw:
                formatted.append(self._format_single_dict(type, doc))
        return json_util.dumps(formatted)

    def _format_single_dict(self, type: str, doc: Dict) -> Dict:
        """Format single result dictionary.

        Delete mongodb internal id from returned result.
        For studies, publish date is formatted to ISO 8601.

        :param doc: single document from mongodb
        :returns: formatted version of document
        """
        def format_date(key: str, doc: Dict) -> Dict:
            doc[key] = doc[key].isoformat()
            return doc

        del doc["_id"]
        doc = format_date("dateCreated", doc)
        doc = format_date("dateModified", doc)
        if type == "study":
            doc = format_date("publishDate", doc)
        return doc

    def _handle_data_and_add_to_db(self, type: str, data: Dict,
                                   accession_id: str) -> None:
        """Format added json metadata object and add it to db.

        Adds necessary additional information to object before adding to db.

        If type is study, publishDate and status is added.
        By default date is two months from submission date (based on ENA
        submission model).

        :param type: Type of the object to format
        :param data: Metadata object
        :param accession_id: objects accession id
        """
        data["accessionId"] = accession_id
        data["dateCreated"] = datetime.utcnow()
        data["dateModified"] = datetime.utcnow()
        if type == "study":
            data["publishDate"] = datetime.utcnow() + relativedelta(months=2)
        try:
            self.db_service.create(type, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            raise web.HTTPBadRequest(reason=reason)


class XMLOperator(BaseOperator):
    """Alternative operator class for handling database operations.

    Operations are implemented with XML format.
    """

    def __init__(self) -> None:
        """Initialize database and content-type."""
        super().__init__("backups", "text/xml")

    def _format_read_data(self, type: str, data_raw: Dict) -> str:
        """Get xml content from given mongodb data.

        :param type: Type of the object to format
        :param data_raw: Data from mongodb query with single result.
        :returns: XML content
        """
        return data_raw["content"]

    def _handle_data_and_add_to_db(self, type: str, data: str,
                                   accession_id: str) -> None:
        """Format added xml metadata object and add it to db.

        XML is validated, then parsed to json and json is added to database.
        After success, xml itself is backed up to database.

        :param type: Type of the object to format
        :param data: Original xml content
        :param accession_id: objects accession id
        """
        data_as_json = XMLToJSONParser().parse(type, data)
        Operator()._handle_data_and_add_to_db(type, data_as_json, accession_id)

        try:
            self.db_service.create(type, {"accessionId": accession_id,
                                          "content": data})
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            raise web.HTTPBadRequest(reason=reason)
