"""CSC PID service."""

from typing import Any, override

from aiohttp.client_exceptions import ClientConnectorError
from yarl import URL

from ..api.services.datacite import DataciteService
from ..conf.pid import pid_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class PIDServiceHandler(DataciteService, ServiceHandler):
    """CSC PID service."""

    service_name = "PID"

    def __init__(self) -> None:
        """CSC PID service."""

        super().__init__(
            base_url=URL(pid_config.CSC_PID_URL),
        )
        self._headers = {"Content-Type": "application/json", "apikey": pid_config.CSC_PID_KEY}

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

    async def healthcheck(self) -> dict[str, Any]:
        """Check service health.

        :returns: the health status.
        """

        try:
            async with self._client.request(
                method="GET",
                url=f"{URL(self.base_url)}/q/health/live",
            ) as response:
                content = await response.json()
                if content["status"] == "UP":
                    return {"status": "Ok"}

                LOG.error("PID API is down with error: %r.", content)
                return {"status": "Down"}

        except ClientConnectorError as e:
            LOG.exception("PID API is down with error: %r.", e)
            return {"status": "Down"}
        except Exception as e:
            LOG.exception("PID API status retrieval failed with: %r.", e)
            return {"status": "Error"}
