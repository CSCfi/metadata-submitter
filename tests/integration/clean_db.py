"""Drop MongoDB default database.

To be utilised mostly for integration tests
"""

import argparse
import asyncio
import logging
import os

from mongo import Mongo

# === Global vars ===
DATABASE = os.getenv("MONGO_DATABASE", "default")
AUTHDB = os.getenv("MONGO_AUTHDB", "admin")
HOST = os.getenv("MONGO_HOST", "localhost")
FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear or recreate mongo db.")
    parser.add_argument("--tls", action="store_true", help="add tls configuration")
    parser.add_argument("--purge", action="store_true", help="destroy database")
    parser.add_argument("--recreate", action="store_true", help="Recreate database")
    args = parser.parse_args()

    url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}?authSource=admin"
    if args.tls:
        _params = "?tls=true&tlsCAFile=./config/cacert&tlsCertificateKeyFile=./config/combined"
        url = f"mongodb://{AUTHDB}:{AUTHDB}@{HOST}/{DATABASE}{_params}&authSource=admin"
    LOG.debug(f"=== Database url {url} ===")

    mongo = Mongo(url)
    if args.purge:
        asyncio.run(mongo.drop_db())
    elif args.recreate:
        asyncio.run(mongo.recreate_db())
    else:
        asyncio.run(mongo.clean_db())
