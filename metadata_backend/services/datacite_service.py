"""Datacite Service."""

import json
from typing import Any, override

from aiohttp import BasicAuth, ClientTimeout
from aiohttp.client_exceptions import ClientConnectorError
from yarl import URL

from ..api.services.datacite import DataciteService
from ..conf.datacite import datacite_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class DataciteServiceHandler(DataciteService, ServiceHandler):
    """Datacite Service."""

    service_name = "Datacite"

    def __init__(self) -> None:
        """Datacite Service."""

        super().__init__(
            auth=BasicAuth(login=datacite_config.DATACITE_USER, password=datacite_config.DATACITE_KEY),
            base_url=URL(datacite_config.DATACITE_API),
            http_client_timeout=ClientTimeout(total=2 * 60),  # 2 minutes timeout
            http_client_headers={"Content-Type": "application/vnd.api+json"},
        )

    @override
    async def create_draft_doi(self) -> str:
        """Create draft DOI.

        :returns: The draft DOI.
        """

        data = {"data": {"type": "dois", "attributes": {"prefix": datacite_config.DATACITE_DOI_PREFIX}}}

        response = await self._request(method="POST", path="/dois", json_data=data)

        try:
            doi: str = response["data"]["attributes"]["doi"]
        except KeyError:
            raise SystemError(f"Invalid DataCite response: {json.dumps(response)}")

        LOG.debug("Created Datacite DOI: %r", doi)
        return doi

    @override
    async def _publish(self, doi: str, data: dict[str, Any]) -> None:
        """Publish DOI with associated metadata.

        :param doi: The draft DOI
        :param data: The request data
        """

        await self._request(method="PUT", path=f"/dois/{doi}", json_data=data)
        LOG.info("Published DataCite DOI: %r", doi)

    async def get(self, doi: str) -> dict[str, Any]:
        """Retrieve DataCite metadata."""

        data = await self._request(
            method="GET", path=f"/dois/{doi}", params={"publisher": "true", "affiliation": "true"}
        )

        if not isinstance(data, dict):
            raise SystemError(f"Invalid DOI response: {data}")

        return data

    async def delete(self, doi: str) -> None:
        """Delete draft DOI.

        :param doi: The draft DOI
        """

        await self._request(method="DELETE", path=f"/dois/{doi}")
        LOG.info("Deleted DataCite DOI: %r", doi)

    async def healthcheck(self) -> dict[str, Any]:
        """Check service health.

        :returns: the with health status.
        """

        try:
            async with self._client.request(
                method="GET",
                url=f"{self.base_url}/heartbeat",
                timeout=ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    return {"status": "Ok"}

                content = await response.text()
                LOG.error("Datacite API is down with error: %r.", content)
                return {"status": "Down"}

        except ClientConnectorError as e:
            LOG.exception("Datacite API is down with error: %r.", e)
            return {"status": "Down"}
        except Exception as e:
            LOG.exception("Datacite API status retrieval failed with: %r.", e)
            return {"status": "Error"}
