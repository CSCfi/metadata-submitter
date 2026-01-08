"""CSC PID service."""

from typing import Any, override

from aiohttp import ClientResponse
from yarl import URL

from ..api.services.datacite import DataciteService
from ..conf.pid import csc_pid_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class PIDServiceHandler(DataciteService, ServiceHandler):
    """CSC PID service."""

    def __init__(self) -> None:
        """CSC PID service."""

        self._config = csc_pid_config()

        super().__init__(
            service_name="pid",
            base_url=URL(self._config.CSC_PID_URL),
            healthcheck_url=URL(self._config.CSC_PID_URL) / "q" / "health" / "live",
            healthcheck_callback=self.healthcheck_callback,
        )
        self._headers = {"Content-Type": "application/json", "apikey": self._config.CSC_PID_KEY}

    @override
    async def create_draft_doi(self) -> str:
        """Create draft DOI.

        :returns: The draft DOI.
        """

        data = {"data": {"type": "dois", "attributes": {"doi": ""}}}
        doi = await self._request(method="POST", headers=self._headers, path="v1/pid/doi", json_data=data)

        if not isinstance(doi, str):
            raise SystemError(f"Invalid DOI response: {doi}")

        LOG.debug("Created PID DOI: %r", doi)
        return doi

    @override
    async def _publish(self, doi: str, data: dict[str, Any]) -> None:
        """Publish DOI with associated metadata.

        :param doi: The draft DOI
        :param data: The request data
        """

        await self._request(method="PUT", headers=self._headers, path=f"v1/pid/doi/{doi}", json_data=data)

        LOG.info("PID: DOI %r updated.", doi)

    async def get(self, doi: str) -> str:
        """Retrieve discovery URL.

        :param doi: The DOI
        :return: The discovery URL
        """

        response = await self._request(method="GET", headers=self._headers, path=f"/get/v1/pid/{doi}")

        if not isinstance(response, str):
            raise SystemError(f"Invalid DOI response: {response}")

        return response

    # No delete endpoint

    @staticmethod
    async def healthcheck_callback(response: ClientResponse) -> bool:
        content = await response.json()
        return "status" in content and content["status"] == "UP"
