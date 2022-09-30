"""Handle health check endpoint."""
import time
from typing import Dict, Union

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure

from metadata_backend.api.auth import AAIServiceHandler

from ..conf.conf import url
from ..helpers.logger import LOG
from ..services.datacite_service_handler import DataciteServiceHandler
from ..services.metax_service_handler import MetaxServiceHandler
from ..services.rems_service_handler import RemsServiceHandler


class HealthHandler:
    """Handler for health check."""

    def __init__(
        self,
        metax_handler: MetaxServiceHandler,
        datacite_handler: DataciteServiceHandler,
        rems_handler: RemsServiceHandler,
        aai_handler: AAIServiceHandler,
    ) -> None:
        """Endpoints should have access to metax and datacite services."""
        self.metax_handler = metax_handler
        self.datacite_handler = datacite_handler
        self.rems_handler = rems_handler
        self.aai_handler = aai_handler

    async def get_health_status(self, _: Request) -> Response:
        """Check health status of the application and return a JSON object portraying the status.

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

        # Determine the status of loaded services

        services["datacite"] = await self.datacite_handler._healtcheck()
        services["rems"] = await self.rems_handler._healtcheck()
        services["metax"] = await self.metax_handler._healtcheck()
        services["aai"] = await self.aai_handler._healtcheck()

        full_status["status"] = "Ok"

        # General service status

        for service in services.values():
            if service["status"] in ["Down", "Error"]:
                full_status["status"] = "Partially down"
                break
            if service["status"] == "Degraded":
                full_status["status"] = "Degraded"

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
        LOG.debug("Initialised a new DB client as a test")
        return new_client

    async def try_db_connection(self, db_client: AsyncIOMotorClient) -> Union[None, float]:
        """Check the connection to database.

        :param db_client: Motor client used for database connections
        :returns: Connection time or None if connection fails
        """
        try:
            start = time.time()
            await db_client.server_info()
            LOG.debug("Connection to db succeeded.")
            perf_time = time.time() - start
            return perf_time
        except ConnectionFailure:
            LOG.exception("Connection to db failed.")
            return None
