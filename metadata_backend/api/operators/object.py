"""Object operator class."""
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple, Union
from uuid import uuid4

from aiohttp import web
from dateutil.relativedelta import relativedelta
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCursor
from multidict import MultiDictProxy
from pymongo.errors import ConnectionFailure, OperationFailure

from ...conf.conf import DATACITE_SCHEMAS, mongo_database, query_map
from ...database.db_service import auto_reconnect
from ...helpers.logger import LOG
from .base import BaseOperator


class Operator(BaseOperator):
    """Default operator class for handling metadata object related database operations.

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
            reason = f"Error happened while getting templates from project {project_id}, err: {error}"
            LOG.exception(reason)
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
            reason = f"Error happened while getting object from {collection}, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if len(objects) == 1:
            try:
                return objects[0]["projectId"]
            except KeyError as error:
                # This should not be possible and should never happen, if the object was created properly
                reason = (
                    f"In {collection}, accession ID {accession_id} does not have an associated project, err:{error}"
                )
                LOG.exception(reason)
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
        LOG.debug("Query construct: %r ", mongo_query)
        LOG.debug("Redacted filter: %r", redacted_content)
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
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        data = await self._format_read_data(schema_type, result_aggregate)

        if not data:
            reason = f"could not find any data in {schema_type}."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        page_size = len(data) if len(data) != page_size else page_size
        count_query = [{"$match": mongo_query}, redacted_content, {"$count": "total"}]
        total_objects = await self.db_service.do_aggregate(schema_type, count_query)

        LOG.debug("DB query: %r", que)
        LOG.info(
            "DB query successful in collection: %r resulted in: %d objects. Requested was page: %d & page size: %d.",
            schema_type,
            total_objects[0]["total"],
            page_num,
            page_size,
        )
        return data, page_num, page_size, total_objects[0]["total"]

    async def update_identifiers(self, schema_type: str, accession_id: str, data: Dict) -> bool:
        """Update study, dataset or bpdataset object with doi and/or metax info.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Metadata object
        :returns: True on successful database update
        """
        if schema_type not in DATACITE_SCHEMAS:
            LOG.error("Object schema type not supported")
            return False
        try:
            create_success = await self.db_service.update(schema_type, accession_id, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while updating object, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not create_success:
            reason = "Updating object to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Object in collection: %r with accession ID: %r metax info updated.", schema_type, accession_id)
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
        LOG.debug("Operator formatted data for collection: %r to add to DB.", schema_type)
        await self._insert_formatted_object_to_db(schema_type, data)
        return data

    async def _format_data_to_replace_and_add_to_db(self, schema_type: str, accession_id: str, data: Dict) -> Dict:
        """Format JSON metadata object and replace it in db.

        Replace information in object before adding to db.doc

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
        LOG.debug("Operator formatted data for collection: %r to add to DB.", schema_type)
        await self._replace_object_from_db(schema_type, accession_id, data)
        return data

    async def _format_data_to_update_and_add_to_db(self, schema_type: str, accession_id: str, data: Dict) -> str:
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

        LOG.debug("Operator formatted data for collection: %r to add to DB.", schema_type)
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
