"""Services that handle database connections. Implemented with MongoDB."""

from typing import Dict

from motor.motor_asyncio import AsyncIOMotorCursor
from pymongo.errors import ConnectionFailure, OperationFailure
from ..helpers.logger import LOG


class DBService:
    """Create service used for database communication.

    With this class, it is possible to create separate databases for different
    purposes (e.g. submissions and backups). Normal CRUD and some basic query
    operations are implemented.

    All services should use the same client, since Motor handles pooling
    automatically.
    """

    def __init__(self, database_name: str, db_client) -> None:
        """Create service for given database.

        Service will have read-write access to given database. Database will be
        created during first read-write operation if not already present.
        :param database_name: Name of database to be used
        """
        self.db_client = db_client
        self.database = db_client[database_name]

    async def create(self, collection: str, document: Dict) -> bool:
        """Insert document to collection in database.

        :param collection: Collection where document should be inserted
        :param document: Document to be inserted
        :raises: Error when write fails for any Mongodb related reason
        :returns: True if operation was successful
        """
        try:
            result = await self.database[collection].insert_one(document)
            return result.acknowledged
        except (ConnectionFailure, OperationFailure):
            raise

    async def read(self, collection: str, accession_id: str) -> Dict:
        """Find object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: Accession id of the document to be searched
        :returns: First document matching the query
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            find_by_id_query = {"accessionId": accession_id}
            return await self.database[collection].find_one(find_by_id_query)
        except (ConnectionFailure, OperationFailure):
            raise

    async def update(self, collection: str, accession_id: str,
                     data_to_be_updated: Dict) -> None:
        """Update some elements of object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: Accession id for object to be updated
        :param data_to_be_updated: JSON representing the data that should be
        updated to object, can replace previous fields and add new ones.
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            find_by_id_query = {"accessionId": accession_id}
            update_operation = {"$set": data_to_be_updated}
            await self.database[collection].update_one(find_by_id_query,
                                                       update_operation)
        except (ConnectionFailure, OperationFailure):
            raise

    async def replace(self, collection: str, accession_id: str,
                      data_to_be_updated: Dict) -> None:
        """Replace whole object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: Accession id for object to be updated
        :param data_to_be_updated: JSON representing the data that replaces
        old data
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            find_by_id_query = {"accessionId": accession_id}
            await self.database[collection].replace_one(find_by_id_query,
                                                        data_to_be_updated)
        except (ConnectionFailure, OperationFailure):
            raise

    async def delete(self, collection: str, accession_id: str) -> None:
        """Delete object by its accessionId.

        :param collection: Collection where document should be searched from
        :param accession_id: Accession id for object to be updated
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            find_by_id_query = {"accessionId": accession_id}
            await self.database[collection].delete_one(find_by_id_query)
        except (ConnectionFailure, OperationFailure):
            raise

    def query(self, collection: str, query: Dict) -> AsyncIOMotorCursor:
        """Query database with given query.

        Find() does no I/O and does not require an await expression, hence
        function is not async.

        :param collection: Collection where document should be searched from
        :param query: query to be used
        :returns: Async cursor instance which should be awaited when iterating
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            return self.database[collection].find(query)
        except (ConnectionFailure, OperationFailure):
            raise
