"""Drop MongoDB default database.

To be utilised mostly for integration tests
"""

from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import logging
import argparse

serverTimeout = 15000
connectTimeout = 15000

# === Global vars ===
FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


def create_db_client(url: str) -> AsyncIOMotorClient:
    """Initialize database client for AioHTTP App.

    :returns: Coroutine-based Motor client for Mongo operations
    """
    return AsyncIOMotorClient(url, connectTimeoutMS=connectTimeout, serverSelectionTimeoutMS=serverTimeout)


async def clean_mongodb(url: str) -> None:
    """Clean Collection and recreate it."""
    client = create_db_client(url)
    LOG.debug(f"current databases: {*await client.list_database_names(),}")
    LOG.debug("=== Drop any existing database ===")
    await client.drop_database("default")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("--tls", action="store_true", help="add tls configuration")
    args = parser.parse_args()
    url = url = "mongodb://admin:admin@localhost:27017/default?authSource=admin"
    if args.tls:
        _params = "?tls=true&tlsCAFile=config/ca.crt&ssl_keyfile=config/client.key&ssl_certfile=config/client.crt"
        url = f"mongodb://admin:admin@localhost:27017/default{_params}&authSource=admin"
    asyncio.run(clean_mongodb(url))
