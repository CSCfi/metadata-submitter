"""MongoDB client and basic operations on default collections and indexes."""

import argparse
import asyncio
import logging
import os

import pymongo
from motor.motor_asyncio import AsyncIOMotorClient

# === Global vars ===
DATABASE = os.getenv("MONGO_DATABASE", "default")
AUTHDB = os.getenv("MONGO_AUTHDB", "admin")
HOST = os.getenv("MONGO_HOST", "localhost:27017")

# === Logging ===
FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

# === MongoDB setup ===
COLLECTIONS = {"submission", "user"}
INDEXES = {
    "submission": [
        {
            "index": ("submissionId", 1),
            "unique": True,
        },
        {
            "index": ("dateCreated", -1),
            "unique": False,
        },
        {
            "index": ("datePublished", -1),
            "unique": False,
        },
        {
            "index": ("lastModified", -1),
            "unique": False,
        },
        {
            "index": ("text_name", pymongo.TEXT),
            "unique": False,
        },
    ],
    "user": [
        {
            "index": ("userId", 1),
            "unique": True,
        }
    ],
}


class Mongo:
    """Helper class to automate mongo tasks."""

    _db = None

    def __init__(self, url: str, database=DATABASE):
        """Take a mongo connection URI and create a client."""
        self.client = self.create_db_client(url, 15000, 15000)
        self._database_name = database

    @property
    def db(self):
        """Create a new db instance if one is not available, on demand."""
        if self._db is not None:
            return self._db

        LOG.debug(f"=== Database connection didn't exist, creating a new one === {self._database_name}")
        self._db = self.client[self._database_name]
        return self._db

    @staticmethod
    def create_db_client(url: str, connectTimeout: int, serverTimeout: int) -> AsyncIOMotorClient:
        """Initialize database client for AioHTTP App.

        :returns: Coroutine-based Motor client for Mongo operations
        """
        return AsyncIOMotorClient(url, connectTimeoutMS=connectTimeout, serverSelectionTimeoutMS=serverTimeout)

    async def create_collections(self) -> None:
        """Create collections."""
        LOG.debug(f"Current database: {self.db}")
        LOG.debug("=== Create collections ===")
        for col in COLLECTIONS:
            try:
                await self.db.create_collection(col)
            except pymongo.errors.CollectionInvalid as e:
                LOG.debug(f"=== Collection {col} not created due to {str(e)} ===")
                pass
        LOG.debug("=== DONE ===")

    async def drop_collections(self) -> None:
        """Drop collections."""
        LOG.debug(f"Current database: {self.db}")
        LOG.debug("=== Drop collections ===")
        collections = await self.db.list_collection_names()
        LOG.debug(f"=== Collections to be cleared: {collections} ===")
        for col in collections:
            try:
                await self.db.drop_collection(col)
            except pymongo.errors.CollectionInvalid as e:
                LOG.debug(f"=== Collection {col} not dropped {str(e)} ===")
                pass
        LOG.debug("=== DONE ===")

    async def clean_db(self) -> None:
        """Clean Collections."""
        LOG.debug(f"Database to clear: {self._database_name}")
        LOG.debug("=== Delete all documents in all collections ===")
        collections = await self.db.list_collection_names()
        LOG.debug(f"=== Collections to be cleared: {collections} ===")
        for col in collections:
            x = await self.db[col].delete_many({})
            LOG.debug(f"{x.deleted_count}{' documents deleted'}\t{'from '}{col}")
        LOG.debug("=== DONE ===")

    async def create_indexes(self) -> None:
        """Create indexes for collections."""
        LOG.debug(f"Current database: {self.db}")
        LOG.debug("=== Create indexes ===")

        for collection, indexes in INDEXES.items():
            for index in indexes:
                try:
                    await self.db[collection].create_index([index["index"]], unique=index["unique"])
                except Exception:
                    LOG.exception(f"=== Collection '{collection}' index '{index}' not created ===")
                    pass
            ind = await self.db[collection].index_information()
            LOG.debug(f"==== Collection '{collection}' indexes created ==== {ind}")

        LOG.debug("=== DONE ===")

    async def drop_indexes(self) -> None:
        """Drop indexes for collections."""
        LOG.debug(f"Current database: {self.db}")
        LOG.debug("=== Drop indexes ===")

        for collection in COLLECTIONS:
            self.db[collection].drop_indexes()
        LOG.debug("=== DONE ===")
        LOG.debug("==== Indexes created ====")

    async def drop_db(self) -> None:
        """Drop DB."""
        LOG.debug("=== Dropping DB ===")
        await self.drop_collections()
        await self.client.drop_database(self._database_name)
        LOG.debug("=== Done ===")

    async def recreate_db(self):
        """Drop db, then create collections and indexes."""
        LOG.debug("=== Re-creating DB ===")
        await self.drop_db()
        await self.create_collections()
        await self.create_indexes()
        await self.clean_db()
        LOG.debug("=== Re-creating DB DONE ===")

    async def get_count(self):
        """Report number of documents per collection."""
        LOG.info("=== Number of documents per collection ===")
        for collection in COLLECTIONS:
            count = await self.db[collection].count_documents({})
            LOG.info(f"Collection '{collection}' has {count} documents")
        LOG.info("=== Done ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--tls", action="store_true", help="add tls configuration")
    parser.add_argument("--count", action="store_true", help="Print number of documents in each collection")
    args = parser.parse_args()
    url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}?authSource=admin"
    if args.tls:
        _params = "?tls=true&tlsCAFile=./config/cacert&tlsCertificateKeyFile=./config/combined"
        url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}{_params}&authSource=admin"
    LOG.debug(f"=== Database url {url} ===")
    if args.count:
        asyncio.run(Mongo(url).get_count())
    else:
        asyncio.run(Mongo(url).recreate_db())
