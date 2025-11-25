"""Handle health check endpoint."""

import ujson
from aiohttp import web
from aiohttp.web import Request, Response

from metadata_backend.api.auth import AAIServiceHandler

from ..helpers.logger import LOG
from ..services.admin_service_handler import AdminServiceHandler
from ..services.datacite_service_handler import DataciteServiceHandler
from ..services.metax_service_handler import MetaxServiceHandler
from ..services.pid_ms_handler import PIDServiceHandler
from ..services.pouta_service_handler import KeystoneService
from ..services.rems_service_handler import RemsServiceHandler


class HealthHandler:
    """Handler for health check."""

    def __init__(
        self,
        metax_handler: MetaxServiceHandler,
        datacite_handler: DataciteServiceHandler,
        pid_handler: PIDServiceHandler,
        rems_handler: RemsServiceHandler,
        aai_handler: AAIServiceHandler,
        admin_handler: AdminServiceHandler,
        keystone_handler: KeystoneService,
    ) -> None:
        """Endpoints should have access to metax, datacite, rems, aai, PID, and admin services."""
        self.metax_handler = metax_handler
        self.datacite_handler = datacite_handler
        self.pid_handler = pid_handler
        self.rems_handler = rems_handler
        self.aai_handler = aai_handler
        self.admin_handler = admin_handler
        self.keystone_handler = keystone_handler

    async def get_health_status(self, _: Request) -> Response:
        """Check health status of the application and return a JSON object portraying the status.

        :returns: JSON response containing health statuses
        """
        services: dict[str, dict[str, str]] = {}
        full_status: dict[str, dict[str, dict[str, str]] | str] = {}

        # Determine the status of loaded services

        services["datacite"] = await self.datacite_handler._healthcheck()
        services["pid"] = await self.pid_handler._healthcheck()
        services["rems"] = await self.rems_handler._healthcheck()
        services["metax"] = await self.metax_handler._healthcheck()
        services["aai"] = await self.aai_handler._healthcheck()
        services["admin"] = await self.admin_handler._healthcheck()
        services["pouta"] = await self.keystone_handler._healthcheck()

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
