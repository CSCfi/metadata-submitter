"""Handle health check endpoint."""
import ujson
import time
from typing import Dict, Union

from aiohttp import web
from aiohttp.web import Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure

from ..helpers.logger import LOG
from ..conf.conf import url


class HealthHandler:
    """Handler for health check."""

    async def get_health_status(self, req: Request) -> Response:
        """Check health status of the application and return a JSON object portraying the status.

        :param req: GET request
        :returns: JSON response containing health statuses
        """
        db_client = await self.create_test_db_client()
        services: Dict[str, Dict] = {}
        full_status: Dict[str, Union[Dict, str]] = {}
        conn = await self.try_db_connection(db_client)
        # Determine database load status
        if conn:
            services["database"] = {"status": "Ok"} if conn < 1000 else {"status": "Degraded"}
        else:
            services["database"] = {"status": "Down"}
        # General service status
        full_status["status"] = "Ok" if services["database"]["status"] == "Ok" else "Partially down"
        full_status["services"] = services
        LOG.info("Health status collected.")

        return web.Response(
            body=ujson.dumps(full_status, escape_forward_slashes=False), status=200, content_type="application/json"
        )

    async def create_test_db_client(self) -> AsyncIOMotorClient:
        """Initialize a new database client to test Mongo connection.

        :returns: Coroutine-based Motor client for Mongo operations
        """
        new_client = AsyncIOMotorClient(url, connectTimeoutMS=4000, serverSelectionTimeoutMS=4000)
        LOG.info("Initialised a new DB client as a test")
        return new_client

    async def try_db_connection(self, db_client: AsyncIOMotorClient) -> Union[float, None]:
        """Check the connection to database.

        :param db_client: Motor client used for database connections
        :returns: Connection time or None if connection fails
        """
        try:
            start = time.time()
            await db_client.server_info()
            LOG.info("Connection to db succeeded.")
            perf_time = time.time() - start
            return perf_time
        except ConnectionFailure:
            LOG.info("Connection to db failed.")
            return None
