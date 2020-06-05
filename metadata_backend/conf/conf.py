"""Python-based app configurations.

1) Database configurations
You need to specify the necessary environmental variables for connecting to
MongoDB.
Currently in use:
- MONGO_INITDB_ROOT_USERNAME - Admin username for mongodb
- MONGO_INITDB_ROOT_PASSWORD - Admin password for mongodb
- MONGODB_HOST - Mongodb server hostname, with port spesified if needed

MongoDB client should be shared across the whole application and always
imported from this module.
Admin access is needed in order to create new databases during runtime.
Default values are the same that are used in docker-compose file
found from deploy/mongodb.

2) Metadata object types
Object types (such as "submission", "study", "sample") are needed in
different parts of the application.


"""

import os

from pymongo import MongoClient

# 1) Set up database client
mongo_user = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
mongo_password = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "admin")
mongo_host = os.getenv("MONGODB_HOST", "localhost:27017")
url = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}"
db_client = MongoClient(url)

# 2) Define object types and their priorities
object_types = {"submission": 1,
                "study": 2,
                "project": 3,
                "sample": 4,
                "experiment": 5,
                "run": 6,
                "analysis": 7,
                "dac": 8,
                "policy": 9,
                "dataset": 10}
