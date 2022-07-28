# pylint: disable=too-many-lines
"""Operators for handling database-related operations."""
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

import aiohttp_session
from aiohttp import web
from dateutil.relativedelta import relativedelta
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCursor
from multidict import MultiDictProxy
from pymongo.errors import ConnectionFailure, OperationFailure

from ..conf.conf import mongo_database, query_map
from ..database.db_service import DBService, auto_reconnect
from ..helpers.logger import LOG
from ..helpers.parser import XMLToJSONParser
from ..helpers.validator import JSONValidator


class BaseOperator(ABC):
    """Base class for operators, implements shared functionality.

    This BaseOperator is mainly addressed for working with objects owned by
    a user and that are clustered by submission.
    :param ABC: The abstract base class
    """

    def __init__(self, db_name: str, content_type: str, db_client: AsyncIOMotorClient) -> None:
        """Init needed variables, must be given by subclass.

        :param db_name: Name for database to save objects to.
        :param content_type: Content type this operator handles (XML or JSON)
        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(db_name, db_client)
        self.content_type = content_type

    async def create_metadata_object(self, schema_type: str, data: Union[Dict, str]) -> Union[Dict, List[dict]]:
        """Create new metadata object to database.

        Data formatting and addition step for JSON or XML must be implemented
        by corresponding subclass.

        :param schema_type: Schema type of the object to create.
        :param data: Data to be saved to database.
        :returns: Dict (or list of dicts) with accession id of the object inserted to database and its title
        """
        formatted_data = await self._format_data_to_create_and_add_to_db(schema_type, data)
        data_list: List = formatted_data if isinstance(formatted_data, list) else [formatted_data]
        for obj in data_list:
            _id = obj["accessionId"]
            LOG.info(f"Inserting object with schema {schema_type} to database succeeded with accession id: {_id}")
        return formatted_data

    async def replace_metadata_object(self, schema_type: str, accession_id: str, data: Union[Dict, str]) -> Dict:
        """Replace metadata object from database.

        Data formatting and addition step for JSON or XML must be implemented
        by corresponding subclass.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Data to be saved to database.
        :returns: Tuple of Accession id for the object replaced to database and its title
        """
        data = await self._format_data_to_replace_and_add_to_db(schema_type, accession_id, data)
        LOG.info(f"Replacing object with schema {schema_type} to database succeeded with accession id: {accession_id}")
        return data

    async def update_metadata_object(self, schema_type: str, accession_id: str, data: Union[Dict, str]) -> str:
        """Update metadata object from database.

        Data formatting and addition step for JSON or XML must be implemented
        by corresponding subclass.

        :param schema_type: Schema type of the object to update.
        :param accession_id: Identifier of object to update.
        :param data: Data to be saved to database.
        :returns: Accession id for the object updated to database
        """
        await self._format_data_to_update_and_add_to_db(schema_type, accession_id, data)
        LOG.info(f"Updated object with schema {schema_type} to database succeeded with accession id: {accession_id}")
        return accession_id

    async def read_metadata_object(self, schema_type: str, accession_id: str) -> Tuple[Union[Dict, str], str]:
        """Read metadata object from database.

        Data formatting to JSON or XML must be implemented by corresponding
        subclass.

        :param schema_type: Schema type of the object to read.
        :param accession_id: Accession Id of the object to read.
        :raises: HTTPBadRequest if reading was not successful, HTTPNotFound if no data found
        :returns: Tuple of Metadata object formatted to JSON or XML, content type
        """
        try:
            data_raw = await self.db_service.read(schema_type, accession_id)
            if not data_raw:
                LOG.error(f"Object with {accession_id} not found in schema: {schema_type}.")
                raise web.HTTPNotFound()
            data = await self._format_read_data(schema_type, data_raw)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while reading object: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return data, self.content_type

    async def delete_metadata_object(self, schema_type: str, accession_id: str) -> str:
        """Delete metadata object from database.

        Tries to remove both JSON and original XML from database, passes
        silently if objects don't exist in database.

        :param schema_type: Schema type of the object to delete.
        :param accession_id: Accession Id of the object to delete.
        :raises: HTTPBadRequest if deleting was not successful
        :returns: Accession id for the object deleted from the database
        """
        db_client = self.db_service.db_client
        JSON_deletion_success = await self._remove_object_from_db(Operator(db_client), schema_type, accession_id)
        XML_deletion_success = await self._remove_object_from_db(XMLOperator(db_client), schema_type, accession_id)
        if JSON_deletion_success and XML_deletion_success:
            LOG.info(f"{accession_id} successfully deleted from collection")
            return accession_id

        reason = f"Deleting {accession_id} from database failed."
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)

    async def _insert_formatted_object_to_db(self, schema_type: str, data: Dict) -> bool:
        """Insert formatted metadata object to database.

        :param schema_type: Schema type of the object to insert.
        :param data: Single document formatted as JSON
        :returns: Accession Id for object inserted to database
        :raises: HTTPBadRequest if reading was not successful
        :returns: Tuple of Accession id for the object deleted from the database and its title
        """
        try:
            insert_success = await self.db_service.create(schema_type, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting object: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not insert_success:
            reason = "Inserting object to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return True

    async def _replace_object_from_db(self, schema_type: str, accession_id: str, data: Dict) -> bool:
        """Replace formatted metadata object in database.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Single document formatted as JSON
        :raises: HTTPBadRequest if reading was not successful, HTTPNotFound if no data found
        :returns: Tuple of Accession Id for object inserted to database and its title
        """
        try:
            check_exists = await self.db_service.exists(schema_type, accession_id)
            if not check_exists:
                reason = f"Object with accession id {accession_id} was not found."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)
            replace_success = await self.db_service.replace(schema_type, accession_id, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting object: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not replace_success:
            reason = "Replacing object to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return True

    async def _update_object_from_db(self, schema_type: str, accession_id: str, data: Dict) -> str:
        """Update formatted metadata object in database.

        After the data has been update we need to do a sanity check
        to see if the patched data still adheres to the corresponding
        JSON schema.

        :param schema_type: Schema type of the object to update.
        :param accession_id: Identifier of object to update.
        :param data: Single document formatted as JSON
        :raises: HTTPBadRequest if reading was not successful, HTTPNotFound if no data found
        :returns: Accession Id for object updated to database
        """
        try:
            check_exists = await self.db_service.exists(schema_type, accession_id)
            if not check_exists:
                reason = f"Object with accession id {accession_id} was not found."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)
            update_success = await self.db_service.update(schema_type, accession_id, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting object: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if update_success:
            return accession_id

        reason = "Replacing object to database failed for some reason."
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)

    async def _remove_object_from_db(self, operator: Any, schema_type: str, accession_id: str) -> bool:
        """Delete object from database.

        We can omit raising error for XMLOperator if id is not
        in backup collection.

        :param schema_type: Schema type of the object to delete.
        :param accession_id: Identifier of object to delete.
        :param data: Single document formatted as JSON
        :raises: HTTPBadRequest if reading was not successful, HTTPNotFound if no data found
        :returns: True or False if object deleted from the database
        """
        try:
            check_exists = await operator.db_service.exists(schema_type, accession_id)
            if not check_exists and not isinstance(operator, XMLOperator):
                reason = f"Object with accession id {accession_id} was not found."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)

            LOG.debug("XML is not in backup collection")
            delete_success = await operator.db_service.delete(schema_type, accession_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while deleting object: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return delete_success

    async def check_exists(self, schema_type: str, accession_id: str) -> None:
        """Check the existance of a object by its id in the database.

        :param schema_type: Schema type of the object to find.
        :param accession_id: Identifier of object to find.
        :raises: HTTPNotFound if object does not exist
        """
        exists = await self.db_service.exists(schema_type, accession_id)
        LOG.info(f"check_exists: {exists}")
        if not exists:
            reason = f"Object with id {accession_id} from schema {schema_type} was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

    @abstractmethod
    async def _format_data_to_create_and_add_to_db(self, schema_type: str, data: Any) -> Union[Dict, List[dict]]:
        """Format and add data to database.

        Must be implemented by subclass.
        """

    @abstractmethod
    async def _format_data_to_replace_and_add_to_db(self, schema_type: str, accession_id: str, data: Any) -> Dict:
        """Format and replace data in database.

        Must be implemented by subclass.
        """

    @abstractmethod
    async def _format_data_to_update_and_add_to_db(self, schema_type: str, accession_id: str, data: Any) -> str:
        """Format and update data in database.

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
        super().__init__(mongo_database, "application/json", db_client)

    async def query_templates_by_project(self, project_id: str) -> List[Dict[str, Union[Dict[str, str], str]]]:
        """Get templates list from given project ID.

        :param project_id: project internal ID that owns templates
        :returns: list of templates in project
        """
        try:
            templates_cursor = self.db_service.query(
                "project", {"projectId": project_id}, custom_projection={"_id": 0, "templates": 1}
            )
            templates = [template async for template in templates_cursor]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting templates from project {project_id}: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if len(templates) == 1:
            return templates[0]["templates"]

        return []

    async def get_object_project(self, collection: str, accession_id: str) -> str:
        """Get the project ID the object is associated to.

        :param collection: database table to look into
        :param accession_id: internal accession ID of object
        :returns: project ID object is associated to
        """
        try:
            object_cursor = self.db_service.query(collection, {"accessionId": accession_id})
            objects = [object async for object in object_cursor]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting object from {collection}: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if len(objects) == 1:
            try:
                return objects[0]["projectId"]
            except KeyError as error:
                # This should not be possible and should never happen, if the object was created properly
                reason = f"{collection} {accession_id} does not have an associated project, err={error}"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
        else:
            reason = f"{collection} {accession_id} not found"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def query_metadata_database(
        self, schema_type: str, que: MultiDictProxy, page_num: int, page_size: int, filter_objects: List
    ) -> Tuple[List, int, int, int]:
        """Query database based on url query parameters.

        Url queries are mapped to mongodb queries based on query_map in
        apps config.

        :param schema_type: Schema type of the object to read.
        :param que: Dict containing query information
        :param page_size: Results per page
        :param page_num: Page number
        :param filter_objects: List of objects belonging to a user
        :raises: HTTPBadRequest if error happened when connection to database
        and HTTPNotFound error if object with given accession id is not found.
        :returns: Tuple of query result with pagination numbers
        """
        # Redact the query by checking the accessionId belongs to user
        redacted_content = {
            "$redact": {
                "$cond": {
                    "if": {"$in": ["$accessionId", filter_objects]} if len(filter_objects) > 1 else {},
                    "then": "$$DESCEND",
                    "else": "$$PRUNE",
                }
            }
        }
        # Generate mongodb query from query parameters
        mongo_query: Dict[Any, Any] = {}
        for query, value in que.items():
            if query in query_map:
                regx = re.compile(f".*{value}.*", re.IGNORECASE)
                if isinstance(query_map[query], dict):
                    # Make or-query for keys in dictionary
                    base = query_map[query]["base"]  # type: ignore
                    if "$or" not in mongo_query:
                        mongo_query["$or"] = []
                    for key in query_map[query]["keys"]:  # type: ignore
                        if value.isdigit():
                            regi = {
                                "$expr": {
                                    "$regexMatch": {
                                        "input": {"$toString": f"${base}.{key}"},
                                        "regex": f".*{int(value)}.*",
                                    }
                                }
                            }
                            mongo_query["$or"].append(regi)
                        else:
                            mongo_query["$or"].append({f"{base}.{key}": regx})
                else:
                    # Query with regex from just one field
                    mongo_query = {query_map[query]: regx}
        LOG.debug(f"Query construct: {mongo_query}")
        LOG.debug(f"redacted filter: {redacted_content}")
        skips = page_size * (page_num - 1)
        aggregate_query = [
            {"$match": mongo_query},
            redacted_content,
            {"$skip": skips},
            {"$limit": page_size},
            {"$project": {"_id": 0}},
        ]
        try:
            result_aggregate = await self.db_service.do_aggregate(schema_type, aggregate_query)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting object: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        data = await self._format_read_data(schema_type, result_aggregate)

        if not data:
            reason = f"could not find any data in {schema_type}."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        page_size = len(data) if len(data) != page_size else page_size
        count_query = [{"$match": mongo_query}, redacted_content, {"$count": "total"}]
        total_objects = await self.db_service.do_aggregate(schema_type, count_query)

        LOG.debug(f"DB query: {que}")
        LOG.info(
            f"DB query successful for query on {schema_type} "
            f"resulted in {total_objects[0]['total']}. "
            f"Requested was page {page_num} and page size {page_size}."
        )
        return data, page_num, page_size, total_objects[0]["total"]

    async def update_identifiers(self, schema_type: str, accession_id: str, data: Dict) -> bool:
        """Update study or dataset object with metax info.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Metadata object
        :returns: True on successful database update
        """
        if schema_type not in {"study", "dataset"}:
            LOG.error("Object schema type must be either study or dataset")
            return False
        try:
            create_success = await self.db_service.update(schema_type, accession_id, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while updating object: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not create_success:
            reason = "Updating object to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Object {schema_type} with id {accession_id} metax info updated.")
        return True

    async def _format_data_to_create_and_add_to_db(self, schema_type: str, data: Dict) -> Dict:
        """Format JSON metadata object and add it to db.

        Adds necessary additional information to object before adding to db.

        If schema type is study, publishDate and status are added.
        By default, date is two months from submission date (based on ENA
        submission model).

        :param schema_type: Schema type of the object to create.
        :param data: Metadata object
        :returns: Metadata object with some additional keys/values
        """
        accession_id = self._generate_accession_id()
        data["accessionId"] = accession_id
        data["dateCreated"] = datetime.utcnow()
        data["dateModified"] = datetime.utcnow()
        if schema_type == "study":
            data["publishDate"] = datetime.utcnow() + relativedelta(months=2)
        LOG.debug(f"Operator formatted data for {schema_type} to add to DB.")
        await self._insert_formatted_object_to_db(schema_type, data)
        return data

    async def _format_data_to_replace_and_add_to_db(self, schema_type: str, accession_id: str, data: Dict) -> Dict:
        """Format JSON metadata object and replace it in db.

        Replace information in object before adding to db.

        We will not replace ``accessionId``, ``publishDate`` or ``dateCreated``,
        as these are generated when created.
        Will not replace ``metaxIdentifier`` and ``doi`` for ``study`` and ``dataset``
        as it is generated when created.
        We will keep also ``publisDate`` and ``dateCreated`` from old object.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Metadata object
        :returns: Metadata object with some additional keys/values
        """
        forbidden_keys = {"accessionId", "publishDate", "dateCreated", "metaxIdentifier", "doi"}
        if any(i in data for i in forbidden_keys):
            reason = f"Some items (e.g: {', '.join(forbidden_keys)}) cannot be changed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        data["accessionId"] = accession_id
        data["dateModified"] = datetime.utcnow()
        LOG.debug(f"Operator formatted data for {schema_type} to add to DB")
        await self._replace_object_from_db(schema_type, accession_id, data)
        return data

    async def _format_data_to_update_and_add_to_db(self, schema_type: str, accession_id: str, data: Any) -> str:
        """Format and update data in database.

        Will not allow to update ``metaxIdentifier`` and ``doi`` for ``study`` and ``dataset``
        as it is generated when created.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Metadata object
        :returns: Accession Id for object updated in database
        """
        forbidden_keys = {"accessionId", "publishDate", "dateCreated", "metaxIdentifier", "doi"}
        if any(i in data for i in forbidden_keys):
            reason = f"Some items (e.g: {', '.join(forbidden_keys)}) cannot be changed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        data["accessionId"] = accession_id
        data["dateModified"] = datetime.utcnow()

        LOG.debug(f"Operator formatted data for {schema_type} to add to DB")
        return await self._update_object_from_db(schema_type, accession_id, data)

    def _generate_accession_id(self) -> str:
        """Generate random accession id.

        Will be replaced later with external id generator.
        """
        sequence = uuid4().hex
        LOG.debug("Generated accession ID.")
        return sequence

    @auto_reconnect
    async def _format_read_data(
        self, schema_type: str, data_raw: Union[Dict, AsyncIOMotorCursor]
    ) -> Union[Dict, List[Dict]]:
        """Get JSON content from given mongodb data.

        Data can be either one result or cursor containing multiple
        results.

        If data is cursor, the query it contains is executed here and possible
        database connection failures are try-catched with reconnect decorator.

        :param schema_type: Schema type of the object to read.
        :param data_raw: Data from mongodb query, can contain multiple results
        :returns: MongoDB query result, formatted to readable dicts
        """
        if isinstance(data_raw, dict):
            return self._format_single_dict(schema_type, data_raw)

        return [self._format_single_dict(schema_type, doc) for doc in data_raw]

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

        doc = format_date("dateCreated", doc)
        doc = format_date("dateModified", doc)
        if schema_type == "study":
            doc = format_date("publishDate", doc)
        return doc


class XMLOperator(BaseOperator):
    """Alternative operator class for handling database operations.

    We store the XML data in a database ``XML-{schema}``.
    Operations are implemented with XML format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Initialize database and content-type.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        super().__init__(mongo_database, "text/xml", db_client)

    async def _format_data_to_create_and_add_to_db(self, schema_type: str, data: str) -> List[dict]:
        """Format XML metadata object and add it to db.

        XML is validated, then parsed to JSON, which is added to database.
        After successful JSON insertion, XML itself is backed up to database.

        :param schema_type: Schema type of the object to read.
        :param data: Original XML content
        :returns: List of metadata objects extracted from the XML content
        """
        db_client = self.db_service.db_client
        # remove `draft-` from schema type
        schema = schema_type[6:] if schema_type.startswith("draft") else schema_type
        parsed_data = XMLToJSONParser().parse(schema, data)

        # Parser may return a list of objects and each object should be added separately
        data_objects = parsed_data if isinstance(parsed_data, list) else [parsed_data]
        added_data: List = []
        for obj in data_objects:
            data_with_id = await Operator(db_client)._format_data_to_create_and_add_to_db(schema_type, obj)
            added_data.append(data_with_id)
            LOG.debug(f"XMLOperator formatted data for xml-{schema_type} to add to DB")
            await self._insert_formatted_object_to_db(
                f"xml-{schema_type}", {"accessionId": data_with_id["accessionId"], "content": data}
            )

        return added_data

    async def _format_data_to_replace_and_add_to_db(self, schema_type: str, accession_id: str, data: str) -> Dict:
        """Format XML metadata object and add it to db.

        XML is validated, then parsed to JSON, which is added to database.
        After successful JSON insertion, XML itself is backed up to database.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Original XML content
        :returns: Metadata object extracted from the XML content
        """
        db_client = self.db_service.db_client
        # remove `draft-` from schema type
        schema = schema_type[6:] if schema_type.startswith("draft") else schema_type
        data_as_json = XMLToJSONParser().parse(schema, data)
        data_with_id = await Operator(db_client)._format_data_to_replace_and_add_to_db(
            schema_type, accession_id, data_as_json
        )
        LOG.debug(f"XMLOperator formatted data for xml-{schema_type} to add to DB")
        await self._replace_object_from_db(
            f"xml-{schema_type}", accession_id, {"accessionId": accession_id, "content": data}
        )
        return data_with_id

    async def _format_data_to_update_and_add_to_db(self, schema_type: str, accession_id: str, data: str) -> str:
        """Raise not implemented.

        Patch update for XML not supported

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Original XML content
        :raises: HTTPUnsupportedMediaType
        """
        reason = "XML patching is not possible."
        raise web.HTTPUnsupportedMediaType(reason=reason)

    async def _format_read_data(self, schema_type: str, data_raw: Dict) -> str:
        """Get XML content from given mongodb data.

        :param schema_type: Schema type of the object to read.
        :param data_raw: Data from mongodb query with single result.
        :returns: XML content
        """
        return data_raw["content"]


class SubmissionOperator:
    """Operator class for handling database operations of submissions.

    Operations are implemented with JSON format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Init db_service.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(mongo_database, db_client)

    async def get_submission_project(self, submission_id: str) -> str:
        """Get the project ID the submission is associated to.

        :param submission_id: internal accession ID of submission
        :returns: project ID submission is associated to
        """
        try:
            submission_cursor = self.db_service.query("submission", {"submissionId": submission_id})
            submissions = [submission async for submission in submission_cursor]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if len(submissions) == 1:
            try:
                return submissions[0]["projectId"]
            except KeyError as error:
                # This should not be possible and should never happen, if the submission was created properly
                reason = f"submission {submission_id} does not have an associated project, err={error}"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
        else:
            reason = f"submission {submission_id} not found"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def check_object_in_submission(self, collection: str, accession_id: str) -> Tuple[bool, str, bool]:
        """Check a object/draft is in a submission.

        :param collection: collection it belongs to, it would be used as path
        :param accession_id: document by accession_id
        :raises: HTTPUnprocessableEntity if error occurs during the process and object in more than 1 submission
        :returns: Tuple with True for the check, submission id and if published or not
        """
        try:
            submission_path = "drafts" if collection.startswith("draft") else "metadataObjects"

            submission_cursor = self.db_service.query(
                "submission", {submission_path: {"$elemMatch": {"accessionId": accession_id, "schema": collection}}}
            )
            submission_check = [submission async for submission in submission_cursor]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while checking object in submission: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if len(submission_check) == 0:
            LOG.info(f"doc {accession_id} belongs to no submission something is off")
            return False, "", False

        if len(submission_check) > 1:
            reason = f"The {accession_id} is in more than 1 submission."
            LOG.error(reason)
            raise web.HTTPUnprocessableEntity(reason=reason)

        submission_id = submission_check[0]["submissionId"]
        LOG.info(f"found doc {accession_id} in {submission_id}")
        return True, submission_id, submission_check[0]["published"]

    async def get_collection_objects(self, submission_id: str, collection: str) -> List:
        """List objects ids per collection.

        :param submission_id: id of the submission
        :param collection: collection it belongs to, it would be used as path
        :returns: List of objects
        """
        try:
            submission_path = "drafts" if collection.startswith("draft") else "metadataObjects"

            submission_cursor = self.db_service.query(
                "submission",
                {"$and": [{submission_path: {"$elemMatch": {"schema": collection}}}, {"submissionId": submission_id}]},
            )
            submissions = [submission async for submission in submission_cursor]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting collection objects: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if len(submissions) >= 1:
            return [i["accessionId"] for i in submissions[0][submission_path]]

        return []

    async def create_submission(self, data: Dict) -> str:
        """Create new object submission to database.

        :param data: Data to be saved to database
        :raises: HTTPBadRequest if error occurs during the process of insert
        :returns: Submission id for the submission inserted to database
        """
        submission_id = self._generate_submission_id()
        _now = int(datetime.now().timestamp())
        data["submissionId"] = submission_id
        data["text_name"] = " ".join(re.split("[\\W_]", data["name"]))
        data["published"] = False
        data["dateCreated"] = _now
        # when we create a submission the last modified should correspond to dateCreated
        data["lastModified"] = _now
        data["metadataObjects"] = data["metadataObjects"] if "metadataObjects" in data else []
        data["drafts"] = data["drafts"] if "drafts" in data else []
        try:
            insert_success = await self.db_service.create("submission", data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting submission: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not insert_success:
            reason = "Inserting submission to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Inserting submission with id {submission_id} to database succeeded.")
        return submission_id

    async def query_submissions(
        self, query: Dict, page_num: int, page_size: int, sort_param: Optional[dict] = None
    ) -> Tuple[List, int]:
        """Query database based on url query parameters.

        :param query: Dict containing query information
        :param page_num: Page number
        :param page_size: Results per page
        :param sort_param: Sorting options.
        :returns: Tuple with Paginated query result
        """
        skips = page_size * (page_num - 1)

        if not sort_param:
            sort = {"dateCreated": -1}
        elif sort_param["score"] and not sort_param["date"] and not sort_param["modified"]:
            sort = {"score": {"$meta": "textScore"}, "dateCreated": -1}  # type: ignore
        elif sort_param["score"] and sort_param["date"]:
            sort = {"dateCreated": -1, "score": {"$meta": "textScore"}}  # type: ignore
        elif sort_param["score"] and sort_param["modified"]:
            sort = {"lastModified": -1, "score": {"$meta": "textScore"}}  # type: ignore
        else:
            sort = {"dateCreated": -1}

        _query = [
            {"$match": query},
            {"$sort": sort},
            {"$skip": skips},
            {"$limit": page_size},
            {"$project": {"_id": 0, "text_name": 0}},
        ]
        data_raw = await self.db_service.do_aggregate("submission", _query)

        if not data_raw:
            data = []
        else:
            data = list(data_raw)

        count_query = [{"$match": query}, {"$count": "total"}]
        total_submissions = await self.db_service.do_aggregate("submission", count_query)

        if not total_submissions:
            total_submissions = [{"total": 0}]

        return data, total_submissions[0]["total"]

    async def read_submission(self, submission_id: str) -> Dict:
        """Read object submission from database.

        :param submission_id: Submission ID of the object to read
        :raises: HTTPBadRequest if reading was not successful
        :returns: Object submission formatted to JSON
        """
        try:
            submission = await self.db_service.read("submission", submission_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return submission

    async def update_submission(self, submission_id: str, patch: List, schema: str = "") -> str:
        """Update object submission from database.

        Utilizes JSON Patch operations specified at: http://jsonpatch.com/

        :param submission_id: ID of submission to update
        :param patch: JSON Patch operations determined in the request
        :param schema: database schema for the object
        :raises: HTTPBadRequest if updating was not successful
        :returns: ID of the submission updated to database
        """
        try:
            if schema == "study":
                update_success = await self.db_service.update_study("submission", submission_id, patch)
            else:
                update_success = await self.db_service.patch("submission", submission_id, patch)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while updating submission: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not update_success:
            if schema == "study":
                reason = "Either there was a request to add another study to a submissions or annother error occurred."
            else:
                reason = "Updating submission to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Updating submission with id {submission_id} to database succeeded.")
        return submission_id

    async def remove_object(self, submission_id: str, collection: str, accession_id: str) -> None:
        """Remove object from submissions in the database.

        :param submission_id: ID of submission to update
        :param accession_id: ID of object to remove
        :param collection: collection where to remove the id from
        :raises: HTTPBadRequest if db connection fails
        """
        try:
            submission_path = "drafts" if collection.startswith("draft") else "metadataObjects"
            upd_content = {submission_path: {"accessionId": accession_id}}
            await self.db_service.remove("submission", submission_id, upd_content)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while removing object from submission: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Removing object {accession_id} from {submission_id} succeeded.")

    async def delete_submission(self, submission_id: str) -> Union[str, None]:
        """Delete object submission from database.

        :param submission_id: ID of the submission to delete.
        :raises: HTTPBadRequest if deleting was not successful
        :returns: ID of the submission deleted from database
        """
        try:
            published = await self.db_service.published_submission(submission_id)
            if not published:
                delete_success = await self.db_service.delete("submission", submission_id)
            else:
                return None
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while deleting submission: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not delete_success:
            reason = f"Deleting for {submission_id} from database failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Deleting submission with id {submission_id} to database succeeded.")
        return submission_id

    async def check_submission_exists(self, submission_id: str) -> None:
        """Check the existance of a submission by its id in the database.

        :raises: HTTPNotFound if submission does not exist
        """
        exists = await self.db_service.exists("submission", submission_id)
        if not exists:
            reason = f"Submission with id {submission_id} was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

    async def check_submission_published(self, submission_id: str) -> None:
        """Check the existance of a submission by its id in the database.

        :raises: HTTPNotFound if submission does not exist
        """
        published = await self.db_service.published_submission(submission_id)
        if published:
            reason = f"Submission with id {submission_id} is published and cannot be deleted."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

    def _generate_submission_id(self) -> str:
        """Generate random submission id.

        :returns: str with submission id
        """
        sequence = uuid4().hex
        LOG.debug("Generated submission ID.")
        return sequence


class UserOperator:
    """Operator class for handling database operations of users.

    Operations are implemented with JSON format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Init db_service.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(mongo_database, db_client)

    async def check_user_has_doc(
        self, req: web.Request, collection: str, user_id: str, accession_id: str
    ) -> Tuple[bool, str]:
        """Check a submission/template belongs to same project the user is in.

        :param req: HTTP request
        :param collection: collection it belongs to, it would be used as path
        :param user_id: user_id from session
        :param accession_id: document by accession_id
        :raises: HTTPUnprocessableEntity if more users seem to have same submission
        :returns: True and project_id if accession_id belongs to user, False otherwise
        """
        session = await aiohttp_session.get_session(req)
        LOG.debug(f"check that user {user_id} belongs to same project as {collection} {accession_id}")

        db_client = req.app["db_client"]
        user_operator = UserOperator(db_client)

        project_id = ""
        if collection.startswith("template"):
            object_operator = Operator(db_client)
            project_id = await object_operator.get_object_project(collection, accession_id)
        elif collection == "submissions":
            submission_operator = SubmissionOperator(db_client)
            project_id = await submission_operator.get_submission_project(accession_id)
        else:
            reason = f"collection must be submissions or template, received {collection}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        current_user = session["user_info"]
        user = await user_operator.read_user(current_user)
        user_has_project = await user_operator.check_user_has_project(project_id, user["userId"])
        return user_has_project, project_id

    async def check_user_has_project(self, project_id: str, user_id: str) -> bool:
        """Check that user has project affiliation.

        :param project_id: internal project ID
        :param user_id: internal user ID
        :raises HTTPBadRequest: on database error
        :returns: True if user has project, False if user does not have project
        """
        try:
            user_query = {"projects": {"$elemMatch": {"projectId": project_id}}, "userId": user_id}
            user_cursor = self.db_service.query("user", user_query)
            user_check = [user async for user in user_cursor]
            if user_check:
                LOG.debug(f"user {user_id} has project {project_id} affiliation")
                return True

            reason = f"user {user_id} does not have project {project_id} affiliation"
            LOG.debug(reason)
            return False
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while reading user project affiliation: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def create_user(self, data: Dict[str, Union[list, str]]) -> str:
        """Create new user object to database.

        :param data: User Data to identify user
        :raises: HTTPBadRequest if error occurs during the process of creating user
        :returns: User id for the user object inserted to database
        """
        user_data: Dict[str, Union[list, str]] = {}

        try:
            existing_user_id = await self.db_service.exists_user_by_external_id(data["user_id"], data["real_name"])
            if existing_user_id:
                LOG.info(f"User with identifier: {data['user_id']} exists, no need to create.")
                return existing_user_id

            user_data["projects"] = data["projects"]
            user_data["userId"] = user_id = self._generate_user_id()
            user_data["name"] = data["real_name"]
            user_data["externalId"] = data["user_id"]
            JSONValidator(user_data, "users")
            insert_success = await self.db_service.create("user", user_data)
            if not insert_success:
                reason = "Inserting user to database failed for some reason."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

            LOG.info(f"Inserting user with id {user_id} to database succeeded.")
            return user_id
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting user: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def read_user(self, user_id: str) -> Dict:
        """Read user object from database.

        :param user_id: User ID of the object to read
        :raises: HTTPBadRequest if reading user was not successful
        :returns: User object formatted to JSON
        """
        try:
            await self._check_user_exists(user_id)
            user = await self.db_service.read("user", user_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting user: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return user

    async def filter_user(self, query: Dict, item_type: str, page_num: int, page_size: int) -> Tuple[List, int]:
        """Query database based on url query parameters.

        :param query: Dict containing query information
        :param item_type: schema type of the item
        :param page_num: Page number
        :param page_size: Results per page
        :returns: Tuple with Paginated query result
        """
        skips = page_size * (page_num - 1)
        _query = [
            {"$match": query},
            {
                "$project": {
                    "_id": 0,
                    item_type: {"$slice": [f"${item_type}", skips, page_size]},
                }
            },
        ]
        data = await self.db_service.do_aggregate("user", _query)

        if not data:
            data = [{item_type: []}]

        count_query = [
            {"$match": query},
            {
                "$project": {
                    "_id": 0,
                    "item": 1,
                    "total": {
                        "$cond": {"if": {"$isArray": f"${item_type}"}, "then": {"$size": f"${item_type}"}, "else": 0}
                    },
                }
            },
        ]
        total_users = await self.db_service.do_aggregate("user", count_query)

        return data[0][item_type], total_users[0]["total"]

    async def update_user(self, user_id: str, patch: List) -> str:
        """Update user object from database.

        :param user_id: ID of user to update
        :param patch: Patch operations determined in the request
        :returns: User Id updated to database
        """
        try:
            await self._check_user_exists(user_id)
            update_success = await self.db_service.patch("user", user_id, patch)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while updating user: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not update_success:
            reason = "Updating user to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Updating user with id {user_id} to database succeeded.")
        return user_id

    async def assign_objects(self, user_id: str, collection: str, object_ids: List) -> None:
        """Assing object to user.

        An object can be submission(s) or templates(s).

        :param user_id: ID of user to update
        :param collection: collection where to remove the id from
        :param object_ids: ID or list of IDs of submission(s) to assign
        :raises: HTTPBadRequest if assigning templates/submissions to user was not successful
        returns: None
        """
        try:
            await self._check_user_exists(user_id)
            assign_success = await self.db_service.append(
                "user", user_id, {collection: {"$each": object_ids, "$position": 0}}
            )
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while assigning objects to user: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not assign_success:
            reason = "Assigning objects to user failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Assigning {object_ids} from {user_id} succeeded.")

    async def remove_objects(self, user_id: str, collection: str, object_ids: List) -> None:
        """Remove object from user.

        An object can be submission(s) or template(s).

        :param user_id: ID of user to update
        :param collection: collection where to remove the id from
        :param object_ids: ID or list of IDs of submission(s) to remove
        :raises: HTTPBadRequest if db connection fails
        returns: None
        """
        remove_content: Dict
        try:
            await self._check_user_exists(user_id)
            for obj in object_ids:
                if collection == "templates":
                    remove_content = {"templates": {"accessionId": obj}}
                else:
                    remove_content = {"submissions": obj}
                await self.db_service.remove("user", user_id, remove_content)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while removing objects from user: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Removing {object_ids} from {user_id} succeeded.")

    async def delete_user(self, user_id: str) -> str:
        """Delete user object from database.

        :param user_id: ID of the user to delete.
        :raises: HTTPBadRequest if deleting user was not successful
        :returns: User Id deleted from database
        """
        try:
            await self._check_user_exists(user_id)
            delete_success = await self.db_service.delete("user", user_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while deleting user: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not delete_success:
            reason = "Deleting for {user_id} from database failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"User {user_id} successfully deleted.")
        return user_id

    async def _check_user_exists(self, user_id: str) -> None:
        """Check the existance of a user by its id in the database.

        :param user_id: Identifier of user to find.
        :raises: HTTPNotFound if user does not exist
        :returns: None
        """
        exists = await self.db_service.exists("user", user_id)
        if not exists:
            reason = f"User with id {user_id} was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

    def _generate_user_id(self) -> str:
        """Generate random user id.

        :returns: str with user id
        """
        sequence = uuid4().hex
        LOG.debug("Generated user ID.")
        return sequence


class ProjectOperator:
    """Operator class for handling database operations of project groups.

    Operations are implemented with JSON format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Init db_service.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(mongo_database, db_client)

    async def create_project(self, project_number: str) -> str:
        """Create new object project to database.

        :param project_number: project external ID received from AAI
        :raises: HTTPBadRequest if error occurs during the process of insert
        :returns: Project id for the project inserted to database
        """
        project_data: Dict[str, Union[str, List[str]]] = {}

        try:
            existing_project_id = await self.db_service.exists_project_by_external_id(project_number)
            if existing_project_id:
                LOG.info(f"Project with external ID: {project_number} exists, no need to create.")
                return existing_project_id

            project_id = self._generate_project_id()
            project_data["templates"] = []
            project_data["projectId"] = project_id
            project_data["externalId"] = project_number
            insert_success = await self.db_service.create("project", project_data)
            if not insert_success:
                reason = "Inserting project to database failed for some reason."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

            LOG.info(f"Inserting project with id {project_id} to database succeeded.")
            return project_id
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting project: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def check_project_exists(self, project_id: str) -> None:
        """Check the existence of a project by its id in the database.

        :param project_id: Identifier of project to find.
        :raises: HTTPNotFound if project does not exist
        """
        exists = await self.db_service.exists("project", project_id)
        if not exists:
            reason = f"Project with id {project_id} was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

    async def assign_templates(self, project_id: str, object_ids: List) -> None:
        """Assing templates to project.

        :param project_id: ID of project to update
        :param object_ids: ID or list of IDs of template(s) to assign
        :raises: HTTPBadRequest if assigning templates to project was not successful
        returns: None
        """
        try:
            await self.check_project_exists(project_id)
            assign_success = await self.db_service.append(
                "project", project_id, {"templates": {"$each": object_ids, "$position": 0}}
            )
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting project: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not assign_success:
            reason = "Assigning templates to project failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Assigning templates={object_ids} to project={project_id} succeeded.")

    async def remove_templates(self, project_id: str, object_ids: List) -> None:
        """Remove templates from project.

        :param project_id: ID of project to update
        :param object_ids: ID or list of IDs of template(s) to remove
        :raises: HTTPBadRequest if db connection fails
        returns: None
        """
        remove_content: Dict
        try:
            await self.check_project_exists(project_id)
            for obj in object_ids:
                remove_content = {"templates": {"accessionId": obj}}
                await self.db_service.remove("project", project_id, remove_content)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while removing templates from project: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Removing templates={object_ids} from project={project_id} succeeded.")

    async def update_project(self, project_id: str, patch: List) -> str:
        """Update project object in database.

        :param project_id: ID of project to update
        :param patch: Patch operations determined in the request
        :returns: ID of the project updated to database
        """
        try:
            await self.check_project_exists(project_id)
            update_success = await self.db_service.patch("project", project_id, patch)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting project: {error}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not update_success:
            reason = "Updating project in database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(f"Updating project={project_id} to database succeeded.")
        return project_id

    def _generate_project_id(self) -> str:
        """Generate random project id.

        :returns: str with project id
        """
        sequence = uuid4().hex
        LOG.debug("Generated project ID.")
        return sequence
