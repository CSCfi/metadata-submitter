"""Datacite Service."""

import json
from typing import Any, override

from aiohttp import BasicAuth, ClientTimeout
from yarl import URL

from ..api.services.datacite import DataciteService
from ..api.services.metax import MetaxService
from ..conf.datacite import datacite_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class DataciteServiceHandler(DataciteService, ServiceHandler):
    """Datacite Service."""

    service_name = "Datacite"

    def __init__(self, metax_service: MetaxService | None) -> None:
        """Datacite Service."""

        self._config = datacite_config()

        DataciteService.__init__(self, metax_service)
        ServiceHandler.__init__(
            self,
            service_name="datacite",
            base_url=URL(self._config.DATACITE_API),
            auth=BasicAuth(login=self._config.DATACITE_USER, password=self._config.DATACITE_KEY),
            http_client_timeout=ClientTimeout(total=2 * 60),  # 2 minutes timeout
            http_client_headers={"Content-Type": "application/vnd.api+json"},
            healthcheck_url=URL(self._config.DATACITE_API) / "heartbeat",
        )

    @override
    async def create_draft_doi(self) -> str:
        """Create draft DOI.

        :returns: The draft DOI.
        """

        data = {"data": {"type": "dois", "attributes": {"prefix": self._config.DATACITE_DOI_PREFIX}}}

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
