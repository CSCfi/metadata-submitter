"""Services that handle database connections. Implemented with MongoDB."""
from functools import wraps
from typing import Any, Callable, Dict

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCursor
from pymongo.errors import AutoReconnect, ConnectionFailure

from ..conf.conf import serverTimeout
from ..helpers.logger import LOG


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
                    message = f"Connection to database failed after {attempt}" "tries"
                    raise ConnectionFailure(message=message)
                LOG.error(
                    "Connection not successful, trying to reconnect."
                    f"Reconnection attempt number {attempt}, waiting "
                    f" for {default_timeout} seconds."
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
    async def exists(self, collection: str, id: str) -> bool:
        """Check object, folder or user exists by its generated ID.

        :param collection: Collection where document should be searched from
        :param id: ID of the object/folder/user to be searched
        :returns: True if exists and False if it does not
        """
        id_key = collection + "Id" if (collection == "folder" or collection == "user") else "accessionId"
        find_by_id = {id_key: id}
        LOG.debug(f"DB doc read for {id}.")
        exists = await self.database[collection].find_one(find_by_id, {"_id": False})
        return True if exists else False

    @auto_reconnect
    async def read(self, collection: str, id: str) -> Dict:
        """Find object, folder or user by its generated ID.

        :param collection: Collection where document should be searched from
        :param id: ID of the object/folder/user to be searched
        :returns: First document matching the accession_id
        """
        id_key = collection + "Id" if (collection == "folder" or collection == "user") else "accessionId"
        find_by_id = {id_key: id}
        LOG.debug(f"DB doc read for {id}.")
        return await self.database[collection].find_one(find_by_id, {"_id": False})

    @auto_reconnect
    async def update(self, collection: str, id: str, data_to_be_updated: Dict) -> bool:
        """Update some elements of object by its accessionId.

        :param collection: Collection where document should be searched from
        :param id: ID of the object/folder/user to be updated
        :param data_to_be_updated: JSON representing the data that should be
        updated to object, can replace previous fields and add new ones.
        :returns: True if operation was successful
        """
        id_key = collection + "Id" if (collection == "folder" or collection == "user") else "accessionId"
        find_by_id = {id_key: id}
        update_op = {"$set": data_to_be_updated}
        result = await self.database[collection].update_one(find_by_id, update_op)
        LOG.debug(f"DB doc updated for {id}.")
        return result.acknowledged

    @auto_reconnect
    async def replace(self, collection: str, accession_id: str, new_data: Dict) -> bool:
        """Replace whole object by its accessionId.

        We keep the dateCreated and publishDate dates as these
        are connected with accession ID.

        XML data we replace as a whole and no need for dateCreated.

        :param collection: Collection where document should be searched from
        :param accession_id: Accession id for object to be updated
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
        LOG.debug(f"DB doc replaced for {accession_id}.")
        return result.acknowledged

    @auto_reconnect
    async def delete(self, collection: str, id: str) -> bool:
        """Delete object, folder or user by its generated ID.

        :param collection: Collection where document should be searched from
        :param id: ID for object/folder/user to be deleted
        :returns: True if operation was successful
        """
        id_key = collection + "Id" if (collection == "folder" or collection == "user") else "accessionId"
        find_by_id = {id_key: id}
        result = await self.database[collection].delete_one(find_by_id)
        LOG.debug(f"DB doc deleted for {id}.")
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
        return self.database[collection].find(query, {"_id": False})

    @auto_reconnect
    async def get_count(self, collection: str, query: Dict) -> int:
        """Get (estimated) count of documents matching given query.

        :param collection: Collection where document should be searched from
        :param query: query to be used
        :returns: Estimate of the number of documents
        """
        LOG.debug("DB doc count performed.")
        return await self.database[collection].count_documents(query)
