"""Handle health check endpoint."""
from typing import Dict

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

        services["database"] = {"status": "Ok"} if self.try_connection(db_client) else {"status": "Down"}
        body = {"status": "Ok", "services": services}
        LOG.info("Health status collected.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def try_connection(self, db_client: AsyncIOMotorClient) -> bool:
        """Check the connection to database.

        :param db_client: Motor client used for database connections
        :returns: True if check was successful
        """
        try:
            db_client.server_info()
            LOG.info("Connection to db succeeded.")
            return True
        except ConnectionFailure:
            LOG.info("Connection to db failed.")
            return False
