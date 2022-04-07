"""Create MongoDB default collections and indexes."""

import argparse
import asyncio
import logging
import os

import pymongo
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import TEXT

serverTimeout = 15000
connectTimeout = 15000

# === Global vars ===
DATABASE = os.getenv("MONGO_DATABASE", "default")
AUTHDB = os.getenv("MONGO_AUTHDB", "admin")
HOST = os.getenv("MONGO_HOST", "admin")
FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


def create_db_client(url: str) -> AsyncIOMotorClient:
    """Initialize database client for AioHTTP App.

    :returns: Coroutine-based Motor client for Mongo operations
    """
    return AsyncIOMotorClient(url, connectTimeoutMS=connectTimeout, serverSelectionTimeoutMS=serverTimeout)


async def create_indexes(url: str) -> None:
    """Clean Collection and recreate it."""
    client = create_db_client(url)
    db = client[DATABASE]
    LOG.debug(f"Current database: {db}")
    LOG.debug("=== Create collections ===")
    for col in {"folder", "user"}:
        try:
            await db.create_collection(col)
        except pymongo.errors.CollectionInvalid as e:
            LOG.debug(f"=== Collection {col} not created due to {str(e)} ===")
            pass
    LOG.debug("=== Create indexes ===")

    indexes = [
        db.folder.create_index([("dateCreated", -1)]),
        db.folder.create_index([("folderId", 1)], unique=True),
        db.folder.create_index([("text_name", TEXT)]),
        db.user.create_index([("userId", 1)], unique=True),
    ]

    for index in indexes:
        try:
            await index
        except Exception as e:
            LOG.debug(f"=== Indexes not created due to {str(e)} ===")
            pass
    LOG.debug("=== DONE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--tls", action="store_true", help="add tls configuration")
    args = parser.parse_args()
    url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}?authSource=admin"
    if args.tls:
        _params = "?tls=true&tlsCAFile=./config/cacert&ssl_keyfile=./config/key&ssl_certfile=./config/cert"
        url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}{_params}&authSource=admin"
    LOG.debug(f"=== Database url {url} ===")
    asyncio.run(create_indexes(url))
