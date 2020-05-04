"""
Service that handles database connections. Currently implemented with MongoDB.
"""

from pymongo import MongoClient
from metadata_backend.config import init_loadenv
import os


class MongoClientService():
    """Database connection initialiser."""

    def __init__(self):
        """ Creates mongoDB client with admin access. Admin access is needed in
        order to create new databases during runtime """
        init_loadenv()
        mongo_user = os.getenv("MONGO_INITDB_ROOT_USERNAME")
        mongo_password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
        mongo_host = os.getenv("MONGODB_HOST")
        url = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}"
        self.client = MongoClient(url)


class MongoDBService(MongoClientService):
    """ Creates mongoDB database object which inherits client from
    client service. Makes it possible to create separate databases for
    different purposes (e.g. submissions and backups).

    :param mongoClientService: mongoClientService object which can connect to
    mongoDB instance
    """

    def __init__(self, database_name):
        """ Initialise db_service with read-write access to given database.
        Database will be created during first read-write operation if not
        already present.
        :param database_name: name of database to be used
        """
        MongoClientService.__init__(self)
        self.database = self.client[database_name]


class CRUDService():
    """ Static methods to handle CRUD operations for given database """

    @staticmethod
    def create(dbservice, collection, data):
        """ Insert data to database wrapped around dbservice """
        result = dbservice.database[collection].insert_one(data)
        return result

    @staticmethod
    def read(dbservice, collection, query):
        pass

    @staticmethod
    def update(dbservice, collection, _id):
        pass

    @staticmethod
    def delete(dbservice, collection, query):
        pass
