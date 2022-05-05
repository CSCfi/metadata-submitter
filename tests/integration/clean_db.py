"""Drop MongoDB default database.

To be utilised mostly for integration tests
"""

import argparse
import asyncio
import logging
import os

from motor.motor_asyncio import AsyncIOMotorClient

serverTimeout = 15000
connectTimeout = 15000

# === Global vars ===
DATABASE = os.getenv("MONGO_DATABASE", "default")
AUTHDB = os.getenv("MONGO_AUTHDB", "admin")
HOST = os.getenv("MONGO_HOST", "localhost")
FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


def create_db_client(url: str) -> AsyncIOMotorClient:
    """Initialize database client for AioHTTP App.

    :returns: Coroutine-based Motor client for Mongo operations
    """
    return AsyncIOMotorClient(url, connectTimeoutMS=connectTimeout, serverSelectionTimeoutMS=serverTimeout)


async def purge_mongodb(url: str) -> None:
    """Erase database."""
    client = create_db_client(url)
    LOG.debug(f"current databases: {*await client.list_database_names(),}")
    LOG.debug("=== Drop curent database ===")
    await client.drop_database(DATABASE)
    LOG.debug("=== DONE ===")


async def clean_mongodb(url: str) -> None:
    """Clean Collection and recreate it."""
    client = create_db_client(url)
    db = client[DATABASE]
    LOG.debug(f"Database to clear: {DATABASE}")
    collections = await db.list_collection_names()
    LOG.debug(f"=== Collections to be cleared: {collections} ===")
    LOG.debug("=== Delete all documents in all collections ===")
    for col in collections:
        x = await db[col].delete_many({})
        LOG.debug(f"{x.deleted_count}{' documents deleted'}\t{'from '}{col}")
    LOG.debug("=== DONE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--tls", action="store_true", help="add tls configuration")
    parser.add_argument("--purge", action="store_true", help="destroy database")
    args = parser.parse_args()
    url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}?authSource=admin"
    if args.tls:
        _params = "?tls=true&tlsCAFile=./config/cacert&ssl_keyfile=./config/key&ssl_certfile=./config/cert"
        url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}{_params}&authSource=admin"
    LOG.debug(f"=== Database url {url} ===")
    if args.purge:
        asyncio.run(purge_mongodb(url))
    else:
        asyncio.run(clean_mongodb(url))
