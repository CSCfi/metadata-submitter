"""Object operator class."""

import re
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from dateutil.relativedelta import relativedelta
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCursor
from multidict import MultiMapping
from pymongo.errors import ConnectionFailure, OperationFailure

from ...conf.conf import BP_SCHEMA_TYPES, DATACITE_SCHEMAS, query_map
from ...database.db_service import auto_reconnect
from ...helpers.logger import LOG
from .object_base import BaseObjectOperator


class ObjectOperator(BaseObjectOperator):
    """Default operator class for handling metadata object related database operations.

    Operations are implemented with JSON format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:  # type: ignore
        """Initialize database and content-type.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        super().__init__("application/json", db_client)

    async def query_metadata_database(
        self, schema_type: str, que: MultiMapping[str], page_num: int, page_size: int, filter_objects: list[Any]
    ) -> tuple[list[dict[str, Any]], int, int, int]:
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
        mongo_query: dict[Any, Any] = {}
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

    async def update_identifiers(self, schema_type: str, accession_id: str, data: dict[str, Any]) -> bool:
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

    async def _format_data_to_create_and_add_to_db(self, schema_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """Format JSON metadata object and add it to db.

        Adds necessary additional information to object before adding to db.

        If schema type is study, publishDate and status are added.
        By default, date is two months from submission date (based on ENA
        submission model).

        :param schema_type: Schema type of the object to create.
        :param data: Metadata object
        :returns: Metadata object with some additional keys/values
        """

        if schema_type in BP_SCHEMA_TYPES:
            data["accessionId"] = self._generate_bp_accession_id(schema_type)
        else:
            data["accessionId"] = self._generate_accession_id()

        data["dateCreated"] = datetime.now(UTC)
        data["dateModified"] = datetime.now(UTC)
        if schema_type == "study":
            data["publishDate"] = datetime.now(UTC) + relativedelta(months=2)
        LOG.debug("ObjectOperator formatted data for collection: %r to add to DB.", schema_type)
        await self._insert_formatted_object_to_db(schema_type, data)
        return data

    async def _format_data_to_replace_and_add_to_db(
        self, schema_type: str, accession_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Format JSON metadata object and replace it in db.

        Replace information in object before adding to db.doc

        We will not replace ``accessionId``, ``publishDate`` or ``dateCreated``,
        as these are generated when created.
        Will not replace ``metaxIdentifier`` and ``doi`` for ``study`` and ``dataset``
        as it is generated when created.
        We will keep also ``publishDate`` and ``dateCreated`` from old object.

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
        data["dateModified"] = datetime.now(UTC)
        LOG.debug("ObjectOperator formatted data for collection: %r to add to DB.", schema_type)
        await self._replace_object_from_db(schema_type, accession_id, data)
        return data

    async def _format_data_to_update_and_add_to_db(
        self, schema_type: str, accession_id: str, data: dict[str, Any]
    ) -> str:
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
        data["dateModified"] = datetime.now(UTC)

        LOG.debug("ObjectOperator formatted data for collection: %r to add to DB.", schema_type)
        return await self._update_object_from_db(schema_type, accession_id, data)

    @auto_reconnect
    async def _format_read_data(
        self, schema_type: str, data_raw: dict[str, Any] | AsyncIOMotorCursor  # type: ignore
    ) -> dict[str, Any] | list[dict[str, Any]]:
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

        return [self._format_single_dict(schema_type, doc) for doc in data_raw]  # type: ignore

    def _format_single_dict(self, schema_type: str, doc: dict[str, Any]) -> dict[str, Any]:
        """Format single result dictionary.

        Delete mongodb internal id from returned result.
        For studies, publish date is formatted to ISO 8601.

        :param schema_type: Schema type of the object to read.
        :param doc: single document from mongodb
        :returns: formatted version of document
        """

        def format_date(key: str, doc: dict[str, Any]) -> dict[str, Any]:
            doc[key] = doc[key].isoformat()
            return doc

        doc = format_date("dateCreated", doc)
        doc = format_date("dateModified", doc)
        if schema_type == "study":
            doc = format_date("publishDate", doc)
        return doc
