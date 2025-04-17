"""Class for integrating with Admin API service."""

import time
from typing import Any, cast

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
        LOG.info("File in submission %s with path %r is being ingested", data["submissionId"], data["filepath"])

    async def get_user_files(self, req: web.Request, username: str) -> list[dict[str, Any]]:
        """Return information on all the user's files in inbox.

        :param req: HTTP request
        :param username: Username of the user whose files are retrieved
        :raises: HTTPInternalServerError if the file ingestion fails
        """
        admin_auth_headers = self.get_admin_auth_headers(req)
        user_files = await self._request(method="GET", path=f"/users/{username}/files", headers=admin_auth_headers)
        LOG.info("Fetched files from inbox for user %s", username)
        return cast(list[dict[str, Any]], user_files)

    async def post_accession_id(self, req: web.Request, data: dict[str, str]) -> None:
        """Assign accession ID to a file.

        :param req: HTTP request
        :param data: Dict with request data including 'user', 'filepath' and 'accessionId'
        :raises: HTTPInternalServerError if the file ingestion fails
        :raises: HTTPBadRequest if file does not belong to user
        """
        admin_auth_headers = self.get_admin_auth_headers(req)
        accession_data = {"user": data["user"], "filepath": data["filepath"], "accession_id": data["accessionId"]}
        await self._request(method="POST", path="/file/accession", json_data=accession_data, headers=admin_auth_headers)
        LOG.info("Accession ID %s assigned to file %s", accession_data["accession_id"], accession_data["filepath"])

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
