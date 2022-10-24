"""Services that handle database connections. Implemented with MongoDB."""
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCursor
from pymongo import ReturnDocument
from pymongo.errors import AutoReconnect, BulkWriteError, ConnectionFailure

from ..conf.conf import serverTimeout
from ..helpers.logger import LOG
from ..helpers.parser import jsonpatch_mongo


def auto_reconnect(db_func: Callable) -> Callable:
    """Auto reconnection decorator."""

    @wraps(db_func)
    async def retry(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Retry given function for many times with increasing interval.

        By default increases interval by clients default timeout for five
        times and then stops.

        :returns Async mongodb function passed to decorator
        :raises ConnectionFailure after preset amount of attempts
        """
        default_timeout = int(serverTimeout // 1000)
        max_attempts = 6
        for attempt in range(1, max_attempts + 1):
            try:
                return await db_func(*args, **kwargs)
            except AutoReconnect as exc:
                if attempt == max_attempts:
                    message = f"Connection to database failed after {attempt} tries"
                    raise ConnectionFailure(message=message) from exc
                LOG.exception(
                    "Connection not successful, trying to reconnect. Reconnection attempt: %d, waiting for %d seconds.",
                    attempt,
                    default_timeout,
                )
                continue

    return retry


class DBService:
    """Create service used for database communication.

    With this class, it is possible to create separate databases for different
    purposes (e.g. submissions and backups). Normal CRUD and some basic query
    operations are implemented.

    All services should use the same client, since Motor handles pooling
    automatically.
    """

    def __init__(self, database_name: str, db_client: AsyncIOMotorClient) -> None:
        """Create service for given database.

        Service will have read-write access to given database. Database will be
        created during first read-write operation if not already present.
        :param database_name: Name of database to be used
        """
        self.db_client = db_client
        self.database = db_client[database_name]

    def _get_id_key(self, collection: str) -> str:
        """Get id key based on the collection."""
        return f"{collection}Id" if (collection in ["submission", "user", "project"]) else "accessionId"

    @auto_reconnect
    async def create(self, collection: str, document: Dict) -> bool:
        """Insert document or a submission to collection in database.

        :param collection: Collection where document should be inserted
        :param document: Document to be inserted
        :returns: True if operation was successful
        """
        result = await self.database[collection].insert_one(document)
        LOG.debug("DB document inserted in collection: %r.", collection)
        return result.acknowledged

    @auto_reconnect
    async def exists(self, collection: str, accession_id: str) -> bool:
        """Check object, submission or user exists by its generated ID.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/submission/user to be searched
        :returns: True if exists and False if it does not
        """
        id_key = self._get_id_key(collection)
        projection = {"_id": False, "externalId": False} if collection == "user" else {"_id": False}
        find_by_id = {id_key: accession_id}
        exists = await self.database[collection].find_one(find_by_id, projection)
        LOG.debug("DB check exists for accession ID: %r in collection: %r.", accession_id, collection)
        return bool(exists)

    @auto_reconnect
    async def exists_project_by_external_id(self, external_id: str) -> Union[None, str]:
        """Check project exists by its external id.

        :param external_id: project external id
        :returns: Id if exists and None if it does not
        """
        find_by_id = {"externalId": external_id}
        project = await self.database["project"].find_one(find_by_id, {"_id": False, "externalId": False})
        LOG.debug("DB check project exists for: %r returned: '%r'.", external_id, project)
        return project["projectId"] if project else None

    @auto_reconnect
    async def exists_user_by_external_id(self, external_id: str, name: str) -> Union[None, str]:
        """Check user exists by its eppn.

        :param external_id: external user ID
        :param name: eduPersonPrincipalName to be searched
        :returns: User ID if exists and None if it does not
        """
        find_by_id = {"externalId": external_id, "name": name}
        user = await self.database["user"].find_one(find_by_id, {"_id": False, "externalId": False})
        LOG.debug("DB check user exists for: %r returned: %r.", external_id, user)
        return user["userId"] if user else None

    @auto_reconnect
    async def published_submission(self, submission_id: str) -> bool:
        """Check submission is published.

        :param submission_id: submission ID to be searched
        :returns: True if exists and False if it does not
        """
        find_published = {"published": True, "submissionId": submission_id}
        exists = await self.database["submission"].find_one(find_published, {"_id": False})
        check = bool(exists)
        LOG.debug("DB check submission: %r if published, result: %s.", submission_id, check)
        return check

    @auto_reconnect
    async def read(self, collection: str, accession_id: str) -> Dict:
        """Find object, submission or user by its generated ID.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/submission/user to be searched
        :returns: First document matching the accession_id
        """
        id_key = self._get_id_key(collection)
        projection = {"_id": False, "eppn": False} if collection == "user" else {"_id": False}
        find_by_id = {id_key: accession_id}
        LOG.debug("DB doc in collection: %r read for accession ID: %r.", collection, accession_id)
        return await self.database[collection].find_one(find_by_id, projection)

    @auto_reconnect
    async def read_by_key_value(
        self, collection: str, key: str, value: str, projection: Optional[dict] = None
    ) -> Union[None, dict]:
        """Check document exists by an arbitrary key and value.

        :param collection: Collection to search in
        :param key: document property
        :param value: property value
        :param projection: mongodb projection of the result. defaults to hiding the internal mongodb _id field
        :returns: document if exists and None if it does not
        """
        if projection is None:
            projection = {"_id": False}

        find_by_key_value = {key: value}
        document = await self.database[collection].find_one(find_by_key_value, projection)
        LOG.debug("DB collection %r for document matching: %r returned: '%r'.", collection, find_by_key_value, document)
        return document

    @auto_reconnect
    async def patch(self, collection: str, accession_id: str, patch_data: List[Dict]) -> bool:
        """Patch some elements of object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/submission/user to be updated
        :param patch_data: JSON representing the data that should be
        updated to object it will update fields.
        :returns: True if operation was successful
        """
        find_by_id = {f"{collection}Id": accession_id}
        requests = jsonpatch_mongo(find_by_id, patch_data)
        try:
            result = await self.database[collection].bulk_write(requests, ordered=False)
            LOG.debug(
                "DB doc in collection: %r patched for accession ID: %r with data: %r.",
                collection,
                accession_id,
                patch_data,
            )
            return result.acknowledged
        except BulkWriteError as bwe:
            LOG.exception(bwe.details)
            return False

    @auto_reconnect
    async def update_study(self, collection: str, accession_id: str, patch_data: List[Dict]) -> bool:
        """Update and avoid duplicates for study object.

        Currently we don't allow duplicate studies in the same submission,
        thus we need to check before inserting. Regular Bulkwrite cannot prevent race condition.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/submission/user to be updated
        :param patch_data: JSON representing the data that should be
        updated to object it will update fields.
        :returns: True if operation was successful
        """
        find_by_id = {f"{collection}Id": accession_id, "metadataObjects.schema": {"$ne": "study"}}
        requests = jsonpatch_mongo(find_by_id, patch_data)
        for req in requests:
            result = await self.database[collection].find_one_and_update(
                find_by_id, req._doc, projection={"_id": False}, return_document=ReturnDocument.AFTER
            )
            LOG.debug(
                "DB doc in collection: %r with data: %r modified for accession ID: %r.",
                collection,
                patch_data,
                accession_id,
            )
            if not result:
                return False
        return True

    @auto_reconnect
    async def update(self, collection: str, accession_id: str, data_to_be_updated: Dict) -> bool:
        """Update some elements of object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/submission/user to be updated
        :param data_to_be_updated: JSON representing the data that should be
        updated to object, can replace previous fields and add new ones.
        :returns: True if operation was successful
        """
        id_key = self._get_id_key(collection)
        find_by_id = {id_key: accession_id}
        update_op = {"$set": data_to_be_updated}
        result = await self.database[collection].update_one(find_by_id, update_op)
        LOG.debug(
            "DB doc in collection: %r updated for accession ID: %r with data: %r.",
            collection,
            accession_id,
            data_to_be_updated,
        )
        return result.acknowledged

    @auto_reconnect
    async def update_by_key_value(self, collection: str, key: str, value: str, data_to_be_updated: Dict) -> bool:
        """Update some elements of object by its accessionId.

        :param collection: Collection to search in
        :param key: document property
        :param value: property value
        :param data_to_be_updated: JSON representing the data that should be
        updated to object, can replace previous fields and add new ones.
        :returns: True if operation was successful
        """
        find_by_key_value = {key: value}
        update_op = {"$set": data_to_be_updated}
        result = await self.database[collection].update_one(find_by_key_value, update_op)
        LOG.debug(
            "DB collection: %r updated for document matching: %r with data: %r.",
            collection,
            find_by_key_value,
            data_to_be_updated,
        )
        return result.acknowledged

    @auto_reconnect
    async def remove(self, collection: str, accession_id: str, data_to_be_removed: Union[str, Dict]) -> bool:
        """Remove element of object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/submission/user to be updated
        :param data_to_be_removed: str or JSON representing the data that should be
        updated to removed.
        :returns: True if operation was successful
        """
        id_key = self._get_id_key(collection)
        find_by_id = {id_key: accession_id}
        remove_op = {"$pull": data_to_be_removed}
        result = await self.database[collection].find_one_and_update(
            find_by_id, remove_op, projection={"_id": False}, return_document=ReturnDocument.AFTER
        )
        LOG.debug(
            "DB doc in collection: %r with data: %r removed the accesion ID: %r.",
            collection,
            data_to_be_removed,
            accession_id,
        )
        return result

    @auto_reconnect
    async def append(
        self, collection: str, accession_id: str, data_to_be_addded: Union[str, Dict], upsert: bool = False
    ) -> bool:
        """Append data by to object with accessionId in collection.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/submission/user to be appended to
        :param data_to_be_addded: str or JSON representing the data that should be
        updated to removed.
        :param upsert: If the document does not exist add it
        :returns: True if operation was successful
        """
        id_key = self._get_id_key(collection)
        find_by_id = {id_key: accession_id}
        # push vs addtoSet
        # push allows us to specify the postion but it does not check the items are unique
        # addToSet cannot easily specify position
        append_op = {"$push": data_to_be_addded}
        result = await self.database[collection].find_one_and_update(
            find_by_id, append_op, projection={"_id": False}, upsert=upsert, return_document=ReturnDocument.AFTER
        )
        LOG.debug(
            "DB doc in collection: %r with data: %r appeneded for accession ID: %r.",
            collection,
            data_to_be_addded,
            accession_id,
        )
        return result

    @auto_reconnect
    async def replace(self, collection: str, accession_id: str, new_data: Dict) -> bool:
        """Replace whole object by its accessionId.

        We keep the dateCreated and publishDate dates as these
        are connected with accession ID.

        XML data we replace as a whole and no need for dateCreated.

        :param collection: Collection where document should be searched from
        :param accession_id: Accession accession_id for object to be updated
        :param new_data: JSON representing the data that replaces
        old data
        :returns: True if operation was successful
        """
        find_by_id = {"accessionId": accession_id}
        old_data = await self.database[collection].find_one(find_by_id)
        if not (len(new_data) == 2 and new_data["content"].startswith("<")):
            new_data["dateCreated"] = old_data["dateCreated"]
            if "publishDate" in old_data:
                new_data["publishDate"] = old_data["publishDate"]
        result = await self.database[collection].replace_one(find_by_id, new_data)
        LOG.debug(
            "DB doc in collection: %r replaced with data: %r for accession ID: %r.",
            collection,
            new_data,
            accession_id,
        )
        return result.acknowledged

    @auto_reconnect
    async def delete(self, collection: str, accession_id: str) -> bool:
        """Delete object, submission or user by its generated ID.

        :param collection: Collection where document should be searched from
        :param accession_id: ID for object/submission/user to be deleted
        :returns: True if operation was successful
        """
        id_key = self._get_id_key(collection)
        find_by_id = {id_key: accession_id}
        result = await self.database[collection].delete_one(find_by_id)
        LOG.debug("DB doc in collection: %r deleted data for accession ID: %r.", collection, accession_id)
        return result.acknowledged

    def query(
        self, collection: str, query: Dict, custom_projection: Optional[Dict] = None, limit: int = 0
    ) -> AsyncIOMotorCursor:
        """Query database with given query.

        Find() does no I/O and does not require an await expression, hence
        function is not async.

        :param collection: Collection where document should be searched from
        :param query: query to be used
        :param custom_projection: overwrites default projection
        :param limit: maximum number of results
        :returns: Async cursor instance which should be awaited when iterating
        """
        LOG.debug("DB doc query performed in: %r.", collection)
        projection = {"_id": False, "eppn": False} if collection == "user" else {"_id": False}
        if custom_projection:
            projection = custom_projection
        return self.database[collection].find(query, projection, limit=limit)

    @auto_reconnect
    async def do_aggregate(self, collection: str, query: List) -> List:
        """Peform aggregate query.

        :param collection: Collection where document should be searched from
        :param query: query to be used
        :returns: aggregated query result list
        """
        LOG.debug("DB aggregate performed in collection: %r.", collection)
        aggregate = self.database[collection].aggregate(query)
        return [doc async for doc in aggregate]
