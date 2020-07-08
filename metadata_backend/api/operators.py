"""Operators for handling database-related operations."""
import re
import secrets
import string
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Tuple, Union

from aiohttp import web
from dateutil.relativedelta import relativedelta
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCursor
from multidict import MultiDictProxy
from pymongo.errors import ConnectionFailure, OperationFailure

from ..conf.conf import query_map
from ..database.db_service import DBService, auto_reconnect
from ..helpers.logger import LOG
from ..helpers.parser import XMLToJSONParser


class BaseOperator(ABC):
    """Base class for operators, implements shared functionality.

    :param ABC: The abstract base class
    """

    def __init__(self, db_name: str, content_type: str,
                 db_client: AsyncIOMotorClient) -> None:
        """Init needed variables, must be given by subclass.

        :param db_name: Name for database to save files to
        :param content_type: Content type this operator handles (XML or JSON)
        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(db_name, db_client)
        self.content_type = content_type

    async def create_metadata_object(self, schema_type: str,
                                     data: Union[Dict, str]) -> str:
        """Create new metadata object to database.

        Data formatting and addition step for JSON or XML must be implemented
        by corresponding subclass.

        :param schema_type: Schema type of the object to read.
        :param data: Data to be saved to database.
        :returns: Accession id for the object inserted to database
        """
        accession_id = (await self.
                        _format_data_to_create_and_add_to_db(schema_type,
                                                             data))
        LOG.info(f"Inserting file with schema {schema_type} to database "
                 f"succeeded with accession id: {accession_id}")
        return accession_id

    async def read_metadata_object(self, schema_type: str, accession_id:
                                   str) -> Tuple[Union[Dict, str], str]:
        """Read metadata object from database.

        Data formatting to JSON or XML must be implemented by corresponding
        subclass.

        :param schema_type: Schema type of the object to read.
        :param accession_id: Accession Id of the object to read.
        :raises: 400 if reading was not succesful, 404 if no data found
        :returns: Metadata object formatted to JSON or XML, content type
        """
        try:
            data_raw = await self.db_service.read(schema_type, accession_id)
            if not data_raw:
                raise web.HTTPNotFound
            data = await self._format_read_data(schema_type, data_raw)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return data, self.content_type

    async def delete_metadata_object(self, schema_type: str,
                                     accession_id: str) -> None:
        """Delete metadata object from database.

        Tries to remove both JSON and original XML from database, passes
        silently if files don't exist in database.

        :param schema_type: Schema type of the object to read.
        :param accession_id: Accession Id of the object to read.
        :raises: 400 if deleting was not succesful
        """
        db_client = self.db_service.db_client
        await self._remove_object_from_db(Operator(db_client),
                                          schema_type,
                                          accession_id)
        await self._remove_object_from_db(XMLOperator(db_client),
                                          schema_type,
                                          accession_id)
        LOG.info(f"removing object with schema {schema_type} from database "
                 f"and accession id: {accession_id}")

    async def _insert_formatted_object_to_db(self, schema_type: str,
                                             data: Dict) -> str:
        """Insert formatted metadata object to database.

        :param schema_type: Schema type of the object to read.
        :param data: Single document formatted as JSON
        :returns: Accession Id for object inserted to database
        """
        try:
            insert_success = (await self.db_service.create(schema_type, data))
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if insert_success:
            return data["accessionId"]
        else:
            reason = "Inserting file to database failed for some (un)known reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def _remove_object_from_db(self,
                                     operator: Any,
                                     schema_type: str,
                                     accession_id: str) -> None:
        try:
            delete_success = (await operator.db_service.delete(schema_type,
                                                               accession_id))
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while deleting file: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if delete_success:
            LOG.info(f"{accession_id} successfully deleted from collection")
        else:
            reason = "Deleting for {accession_id} from database failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    @abstractmethod
    async def _format_data_to_create_and_add_to_db(self, schema_type: str,
                                                   data: Any) -> str:
        """Format and add data to database.

        Must be implemented by subclass.
        """

    @abstractmethod
    async def _format_read_data(self, schema_type: str, data_raw: Any) -> Any:
        """Format data for API response.

        Must be implemented by subclass.
        """


class Operator(BaseOperator):
    """Default operator class for handling database operations.

    Operations are implemented with JSON format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Initialize database and content-type.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        super().__init__("objects", "application/json", db_client)

    async def query_metadata_database(self, schema_type: str,
                                      que: MultiDictProxy,
                                      page_num: int, page_size: int
                                      ) -> Tuple[Dict, int, int, int]:
        """Query database based on url query parameters.

        Url queries are mapped to mongodb queries based on query_map in
        apps config.

        :param schema_type: Schema type of the object to read.
        :param que: Dict containing query information
        :param page_size: Results per page
        :param page_num: Page number
        :raises: HTTPBadRequest if error happened when connection to database
        and HTTPNotFound error if file with given accession id is not found.
        :returns: Query result with pagination numbers
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
            cursor = self.db_service.query(schema_type, mongo_query)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        skips = page_size * (page_num - 1)
        cursor.skip(skips).limit(page_size)
        data = await self._format_read_data(schema_type, cursor)
        if not data:
            LOG.error("could not find any data.")
            raise web.HTTPNotFound
        page_size = len(data) if len(data) != page_size else page_size
        total_objects = await self.db_service.get_count(schema_type,
                                                        mongo_query)
        LOG.debug(f"DB query: {que}")
        LOG.info(f"DB query successful for query on {schema_type}"
                 f"resulted in {total_objects}."
                 f"Requested was page {page_num} and page size {page_size}.")
        return data, page_num, page_size, total_objects

    async def _format_data_to_create_and_add_to_db(self, schema_type: str,
                                                   data: Dict) -> str:
        """Format JSON metadata object and add it to db.

        Adds necessary additional information to object before adding to db.

        If schema type is study, publishDate and status is added.
        By default date is two months from submission date (based on ENA
        submission model).

        :param schema_type: Schema type of the object to read.
        :param data: Metadata object
        :returns: Accession Id for object inserted to database
        """
        accession_id = self._generate_accession_id()
        data["accessionId"] = accession_id
        data["dateCreated"] = datetime.utcnow()
        data["dateModified"] = datetime.utcnow()
        if schema_type == "study":
            data["publishDate"] = datetime.utcnow() + relativedelta(months=2)
        LOG.debug(f"Operator format data for {schema_type} to add to DB")
        return await self._insert_formatted_object_to_db(schema_type, data)

    def _generate_accession_id(self) -> str:
        """Generate random accession id.

        Will be replaced later with external id generator.
        """
        sequence = ''.join(secrets.choice(string.digits) for i in range(16))
        LOG.debug("Generated accession ID.")
        return f"EDAG{sequence}"

    @auto_reconnect
    async def _format_read_data(self, schema_type: str, data_raw: Union[Dict,
                                AsyncIOMotorCursor]) -> Union[Dict,
                                                              List[Dict]]:
        """Get JSON content from given mongodb data.

        Data can be either one result or cursor containing multiple
        results.

        If data is cursor, the query it contains is executed here and possible
        database connection failures are try-catched with reconnect decorator.

        :param schema_type: Schema type of the object to read.
        :param data_raw: Data from mongodb query, can contain multiple results
        :returns: Mongodb query result, formatted to readable dicts
        """
        if isinstance(data_raw, dict):
            return self._format_single_dict(schema_type, data_raw)
        else:
            return ([self._format_single_dict(schema_type, doc) async for
                     doc in data_raw])

    def _format_single_dict(self, schema_type: str, doc: Dict) -> Dict:
        """Format single result dictionary.

        Delete mongodb internal id from returned result.
        For studies, publish date is formatted to ISO 8601.

        :param schema_type: Schema type of the object to read.
        :param doc: single document from mongodb
        :returns: formatted version of document
        """
        def format_date(key: str, doc: Dict) -> Dict:
            doc[key] = doc[key].isoformat()
            return doc

        del doc["_id"]
        doc = format_date("dateCreated", doc)
        doc = format_date("dateModified", doc)
        if schema_type == "study":
            doc = format_date("publishDate", doc)
        return doc


class XMLOperator(BaseOperator):
    """Alternative operator class for handling database operations.

    Operations are implemented with XML format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Initialize database and content-type.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        super().__init__("backups", "text/xml", db_client)

    async def _format_data_to_create_and_add_to_db(self, schema_type: str,
                                                   data: str) -> str:
        """Format XML metadata object and add it to db.

        XML is validated, then parsed to json and json is added to database.
        After successful json insertion, xml itself is backed up to database.

        :param schema_type: Schema type of the object to read.
        :param data: Original xml content
        :returns: Accession Id for object inserted to database
        """
        db_client = self.db_service.db_client
        data_as_json = XMLToJSONParser().parse(schema_type, data)
        accession_id = (await Operator(db_client).
                        _format_data_to_create_and_add_to_db(schema_type,
                                                             data_as_json))
        LOG.debug(f"XMLOperator format data for {schema_type} to add to DB")
        return (await self.
                _insert_formatted_object_to_db(schema_type,
                                               {"accessionId": accession_id,
                                                "content": data}))

    async def _format_read_data(self, schema_type: str, data_raw: Dict) -> str:
        """Get XML content from given mongodb data.

        :param schema_type: Schema type of the object to read.
        :param data_raw: Data from mongodb query with single result.
        :returns: XML content
        """
        return data_raw["content"]
