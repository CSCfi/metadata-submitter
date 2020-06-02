"""Services that handle database connections. Implemented with MongoDB.

MongoDB client should be shared across the whole application, so it's created
here as module level variable.

Admin access is needed in order to create new databases during runtime.
Default values are the same that are used in docker-compose file
found from deploy/mongodb.
"""

import os
from typing import Dict

from pymongo import MongoClient, errors
from pymongo.cursor import Cursor

# Set up database client
mongo_user = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "admin")
mongo_password = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "admin")
mongo_host = os.getenv("MONGODB_HOST", "localhost:27017")
url = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}"
db_client = MongoClient(url)


class DBService:
    """Create service used for database communication.

    With this class, it is possible to create separate databases for different
    purposes (e.g. submissions and backups).

    All services should use the same client, since pymongo handles pooling
    automatically.
    """

    def __init__(self, database_name: str) -> None:
        """Create service for given database.

        Service will have read-write access to given database. Database will be
        created during first read-write operation if not already present.
        :param database_name: Name of database to be used
        """
        self.database = db_client[database_name]


class CRUDService:
    """Static methods to handle CRUD operations."""

    @staticmethod
    def create(db_service: DBService, collection: str, document: Dict) -> None:
        """Insert document to collection in database.

        :param db_service: Service that connects to database
        :param collection: Collection where document should be inserted
        :param document: Document to be inserted
        :raises: Error when write fails for any Mongodb related reason
        """
        try:
            db_service.database[collection].insert_one(document)
        except errors.PyMongoError:
            raise

    @staticmethod
    def read(db_service: DBService, collection: str,
             query: Dict) -> Cursor:
        """Query from collection in database.

        :param db_service: Service that connects to MongoDB database
        :param collection: Collection where document should be searched from
        :param query: Query for document(s) that should be found
        :returns: Pymongo's Cursor object (iterator)
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            return db_service.database[collection].find(query)
        except errors.ConnectionFailure:
            raise

    @staticmethod
    def update(db_service: DBService, collection: str,
               accession_id: str, data_to_be_updated: Dict) -> None:
        """Update some elements of object by its accessionId.

        :param db_service: Service that connects to MongoDB database
        :param collection: Collection where document should be searched from
        :param accession_id: Accession id for object to be updated
        :param data_to_be_updated: JSON representing the data that should be
        updated to object, can replace previous fields and add new ones.
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            find_by_id_query = {"accessionId": accession_id}
            update_operation = {"$set": data_to_be_updated}
            db_service.database[collection].update_one(find_by_id_query,
                                                       update_operation)
        except errors.ConnectionFailure:
            raise

    @staticmethod
    def replace(db_service: DBService, collection: str,
                accession_id: str, data_to_be_updated: Dict) -> None:
        """Replace whole object by its accessionId.

        :param db_service: Service that connects to MongoDB database
        :param collection: Collection where document should be searched from
        :param accession_id: Accession id for object to be updated
        :param data_to_be_updated: JSON representing the data that replaces
        old data
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            find_by_id_query = {"accessionId": accession_id}
            db_service.database[collection].replace_one(find_by_id_query,
                                                        data_to_be_updated)
        except errors.ConnectionFailure:
            raise

    @staticmethod
    def delete(db_service: DBService, collection: str,
               accession_id: str) -> None:
        """Delete object by its accessionId.

        :param db_service: Service that connects to MongoDB database
        :param collection: Collection where document should be searched from
        :param accession_id: Accession id for object to be updated
        :raises: Error when read fails for any Mongodb related reason
        """
        try:
            find_by_id_query = {"accessionId": accession_id}
            db_service.database[collection].delete_one(find_by_id_query)
        except errors.ConnectionFailure:
            raise
