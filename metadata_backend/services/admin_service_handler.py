"""Class for integrating with Admin API service."""

import time
from typing import Any

from aiohttp import ClientTimeout, web
from aiohttp.client_exceptions import ClientConnectorError, InvalidURL
from yarl import URL

from ..conf.conf import admin_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class AdminServiceHandler(ServiceHandler):
    """API Handler for Admin API service."""

    service_name = "Admin"

    def __init__(self) -> None:
        """Get Admin API credentials from config."""
        super().__init__(base_url=URL(admin_config["url"]))

    @staticmethod
    def get_admin_auth_headers(req: web.Request) -> dict[str, str]:
        """Get authentication headers for Admin API service.

        :param req: HTTP request
        """
        try:
            admin_auth_header = {"Authorization": req.headers["Authorization"]}
            return admin_auth_header
        except KeyError as e:
            LOG.exception("Missing Authorization header")
            raise web.HTTPUnauthorized(reason="User is not authorized") from e

    async def ingest_file(self, req: web.Request, data: dict[str, str]) -> None:
        """Start the ingestion of a file.

        :param req: HTTP request
        :param data: Dict with request data including 'user' and 'filepath'
        :raises: HTTPInternalServerError if the file ingestion fails
        """
        admin_auth_headers = self.get_admin_auth_headers(req)
        ingestion_data = {"user": data["user"], "filepath": data["filepath"]}
        await self._request(method="POST", path="/file/ingest", json_data=ingestion_data, headers=admin_auth_headers)
        LOG.info("The ingestion for file with path %r is started", ingestion_data["filepath"])

    async def _healthcheck(self) -> dict[str, Any]:
        """Check Admin service readiness.

        This can return 200 or 503.

        :returns: Dict with status of the Admin API
        """
        try:
            start = time.time()
            async with self._client.request(
                method="GET",
                url=f"{self.base_url}/ready",
                timeout=ClientTimeout(total=10),
            ) as response:
                content = await response.text()
                LOG.info("ADMIN API response content is: %s.", content)
                if response.status == 200:
                    status = "Ok" if (time.time() - start) < 1000 else "Degraded"
                else:
                    status = "Down"

                return {"status": status}
        except ClientConnectorError as e:
            LOG.exception("Admin API is down with error: %r.", e)
            return {"status": "Down"}
        except InvalidURL as e:
            LOG.exception("Admin API status retrieval failed with: %r.", e)
            return {"status": "Error"}
        except web.HTTPError as e:
            LOG.exception("Admin API status retrieval failed with: %r.", e)
            return {"status": "Error"}
