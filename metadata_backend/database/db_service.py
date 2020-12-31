"""Services that handle database connections. Implemented with MongoDB."""
from functools import wraps
from typing import Any, Callable, Dict, Union, List

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCursor
from pymongo.errors import AutoReconnect, ConnectionFailure
from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError

from ..conf.conf import serverTimeout
from ..helpers.logger import LOG
from ..helpers.parser import jsonpatch_mongo


def auto_reconnect(db_func: Callable) -> Callable:
    """Auto reconnection decorator."""

    @wraps(db_func)
    async def retry(*args: Any, **kwargs: Any) -> Any:
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
            except AutoReconnect:
                if attempt == max_attempts:
                    message = f"Connection to database failed after {attempt} tries"
                    raise ConnectionFailure(message=message)
                LOG.error(
                    "Connection not successful, trying to reconnect."
                    f"Reconnection attempt number {attempt}, waiting for {default_timeout} seconds."
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

    @auto_reconnect
    async def create(self, collection: str, document: Dict) -> bool:
        """Insert document or a folder to collection in database.

        :param collection: Collection where document should be inserted
        :param document: Document to be inserted
        :returns: True if operation was successful
        """
        result = await self.database[collection].insert_one(document)
        LOG.debug("DB doc inserted.")
        return result.acknowledged

    @auto_reconnect
    async def exists(self, collection: str, accession_id: str) -> bool:
        """Check object, folder or user exists by its generated ID.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/folder/user to be searched
        :returns: True if exists and False if it does not
        """
        id_key = f"{collection}Id" if (collection in ["folder", "user"]) else "accessionId"
        projection = {"_id": False, "eppn": False} if collection == "user" else {"_id": False}
        find_by_id = {id_key: accession_id}
        exists = await self.database[collection].find_one(find_by_id, projection)
        LOG.debug(f"DB check exists for {accession_id} in collection {collection}.")
        return True if exists else False

    @auto_reconnect
    async def exists_eppn_user(self, eppn: str, name: str) -> Union[None, str]:
        """Check user exists by its eppn.

        :param eppn: eduPersonPrincipalName to be searched
        :returns: True if exists and False if it does not
        """
        find_by_id = {"eppn": eppn, "name": name}
        user = await self.database["user"].find_one(find_by_id, {"_id": False, "eppn": False})
        LOG.debug(f"DB check user exists for {eppn} returned {user}.")
        return user["userId"] if user else None

    @auto_reconnect
    async def read(self, collection: str, accession_id: str) -> Dict:
        """Find object, folder or user by its generated ID.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/folder/user to be searched
        :returns: First document matching the accession_id
        """
        id_key = f"{collection}Id" if (collection in ["folder", "user"]) else "accessionId"
        projection = {"_id": False, "eppn": False} if collection == "user" else {"_id": False}
        find_by_id = {id_key: accession_id}
        LOG.debug(f"DB doc read for {accession_id}.")
        return await self.database[collection].find_one(find_by_id, projection)

    @auto_reconnect
    async def patch(self, collection: str, accession_id: str, patch_data: List[Dict]) -> bool:
        """Patch some elements of object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/folder/user to be updated
        :param patch_data: JSON representing the data that should be
        updated to object it will update fields.
        :returns: True if operation was successful
        """
        find_by_id = {f"{collection}Id": accession_id}
        requests = jsonpatch_mongo(find_by_id, patch_data)
        try:
            result = await self.database[collection].bulk_write(requests, ordered=False)
            LOG.debug(f"DB doc patched for {accession_id} with data {patch_data}.")
            return result.acknowledged
        except BulkWriteError as bwe:
            LOG.error(bwe.details)
            return False

    @auto_reconnect
    async def update(self, collection: str, accession_id: str, data_to_be_updated: Dict) -> bool:
        """Update some elements of object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/folder/user to be updated
        :param data_to_be_updated: JSON representing the data that should be
        updated to object, can replace previous fields and add new ones.
        :returns: True if operation was successful
        """
        id_key = f"{collection}Id" if (collection in ["folder", "user"]) else "accessionId"
        find_by_id = {id_key: accession_id}
        update_op = {"$set": data_to_be_updated}
        result = await self.database[collection].update_one(find_by_id, update_op)
        LOG.debug(f"DB doc updated for {accession_id} with data {data_to_be_updated}.")
        return result.acknowledged

    @auto_reconnect
    async def remove(self, collection: str, accession_id: str, data_to_be_removed: Any) -> bool:
        """Remove element of object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/folder/user to be updated
        :param data_to_be_removed: str or JSON representing the data that should be
        updated to removed.
        :returns: True if operation was successful
        """
        id_key = f"{collection}Id" if (collection in ["folder", "user"]) else "accessionId"
        find_by_id = {id_key: accession_id}
        remove_op = {"$pull": data_to_be_removed}
        result = await self.database[collection].find_one_and_update(
            find_by_id, remove_op, projection={"_id": False}, return_document=ReturnDocument.AFTER
        )
        LOG.debug(f"DB doc data {data_to_be_removed} removed from {accession_id}.")
        return result

    @auto_reconnect
    async def append(self, collection: str, accession_id: str, data_to_be_addded: Any) -> bool:
        """Append data by to object with accessionId in collection.

        :param collection: Collection where document should be searched from
        :param accession_id: ID of the object/folder/user to be appended to
        :param data_to_be_addded: str or JSON representing the data that should be
        updated to removed.
        :returns: True if operation was successful
        """
        id_key = f"{collection}Id" if (collection in ["folder", "user"]) else "accessionId"
        find_by_id = {id_key: accession_id}
        append_op = {"$addToSet": data_to_be_addded}
        result = await self.database[collection].find_one_and_update(
            find_by_id, append_op, projection={"_id": False}, return_document=ReturnDocument.AFTER
        )
        LOG.debug(f"DB doc data {data_to_be_addded} appeneded for {accession_id}.")
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
        LOG.debug(f"DB doc replaced with {new_data} for {accession_id}.")
        return result.acknowledged

    @auto_reconnect
    async def delete(self, collection: str, accession_id: str) -> bool:
        """Delete object, folder or user by its generated ID.

        :param collection: Collection where document should be searched from
        :param accession_id: ID for object/folder/user to be deleted
        :returns: True if operation was successful
        """
        id_key = f"{collection}Id" if (collection in ["folder", "user"]) else "accessionId"
        find_by_id = {id_key: accession_id}
        result = await self.database[collection].delete_one(find_by_id)
        LOG.debug(f"DB doc deleted for {accession_id}.")
        return result.acknowledged

    def query(self, collection: str, query: Dict) -> AsyncIOMotorCursor:
        """Query database with given query.

        Find() does no I/O and does not require an await expression, hence
        function is not async.

        :param collection: Collection where document should be searched from
        :param query: query to be used
        :returns: Async cursor instance which should be awaited when iterating
        """
        LOG.debug("DB doc query performed.")
        projection = {"_id": False, "eppn": False} if collection == "user" else {"_id": False}
        return self.database[collection].find(query, projection)

    @auto_reconnect
    async def get_count(self, collection: str, query: Dict) -> int:
        """Get (estimated) count of documents matching given query.

        :param collection: Collection where document should be searched from
        :param query: query to be used
        :returns: Estimate of the number of documents
        """
        LOG.debug("DB doc count performed.")
        return await self.database[collection].count_documents(query)

    @auto_reconnect
    async def aggregate(self, collection: str, query: List) -> List:
        """Peform aggregate query.

        :param collection: Collection where document should be searched from
        :param query: query to be used
        :returns: aggregated query result list
        """
        LOG.debug("DB aggregate performed.")
        aggregate = self.database[collection].aggregate(query)
        return [doc async for doc in aggregate]
