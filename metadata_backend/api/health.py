"""Handle health check endpoint."""
import json
from typing import Dict, Union

from aiohttp import web
from aiohttp.web import Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure

from ..helpers.logger import LOG


class HealthHandler:
    """Handler for health check."""

    async def get_health_status(self, req: Request) -> Response:
        """Check health status of the application and return a JSON object portraying the status.

        :param req: GET request
        :returns: JSON response containing health statuses
        """
        db_client = req.app["db_client"]
        services: Dict[str, Dict] = {}
        full_status: Dict[str, Union[Dict, str]] = {}
        services["database"] = {"status": "Ok"} if await self.try_db_connection(db_client) else {"status": "Down"}
        full_status["status"] = "Ok" if services["database"]["status"] == "Ok" else "Partially down"
        full_status["services"] = services
        LOG.info("Health status collected.")
        return web.Response(body=json.dumps(full_status), status=200, content_type="application/json")

    async def try_db_connection(self, db_client: AsyncIOMotorClient) -> bool:
        """Check the connection to database.

        :param db_client: Motor client used for database connections
        :returns: True if check was successful
        """
        try:
            await db_client.server_info()
            LOG.info("Connection to db succeeded.")
            return True
        except ConnectionFailure:
            LOG.info("Connection to db failed.")
            return False
