"""Register DOI through CSC PID microservice."""

import time
from typing import Any

from aiohttp.client_exceptions import ClientConnectorError
from aiohttp.web import HTTPError
from yarl import URL

from ..conf.conf import pid_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class PIDServiceHandler(ServiceHandler):
    """DOI registration methods."""

    service_name = "PID"

    def __init__(self) -> None:
        """Set up from config."""
        super().__init__(
            base_url=URL(pid_config["api_url"]),
        )

    async def create_draft_doi_pid(self) -> str:
        """POST request to create a draft DOI to CSC PID microservice.

        Draft does not include publish event in data. Requires another request to publish.

        :raises: HTTPBadRequest if DOI payload is invalid
        :raises: HTTPInternalServerError if DOI draft registration fails
        :returns: DOI
        """

        # Minimal payload for draft, no URL needed
        doi_payload = {"data": {"type": "dois", "attributes": {"doi": ""}}}
        headers = {"Content-Type": "application/json", "apikey": pid_config["api_key"]}

        doi: str = await self._request(method="POST", headers=headers, path="v1/pid/doi", json_data=doi_payload)
        # Example of the returned test DOI (plain text) is 10.80869/sd-2108ec42-6a9e-39c0-9941-2e8f02ff5b7f
        # In production prefix will be 10.24340
        LOG.info("PID: DOI draft created with identifier: %r.", doi)
        return doi

    async def publish(self, datacite_payload: dict[str, Any]) -> None:
        """Set DOI and associated metadata.

        Endpoint: PUT /v1/pid/doi/{prefix}/{suffix}

        :param datacite_payload: Dictionary with payload to send to PID ms
        :raises: HTTPBadRequest if DOI payload is invalid
        :raises: HTTPBadRequest if DOI is missing in doi_payload
        :raises: HTTPInternalServerError if DOI update fails
        """
        try:
            doi = datacite_payload["id"]
        except KeyError as exc:
            raise self.make_exception(reason="Missing 'id' field in object data", status=400) from exc
        path = f"v1/pid/doi/{doi}"
        headers = {"Content-Type": "application/json", "apikey": pid_config["api_key"]}
        await self._request(method="PUT", headers=headers, path=path, json_data=datacite_payload)

        LOG.info("PID: DOI %r updated.", doi)

    async def _healthcheck(self) -> dict[str, Any]:
        """Check the status of PID ms.

        :returns: Dict with status of PID ms
        """
        try:
            start = time.time()
            # returns dict {status: "", checks : []}
            async with self._client.request(
                method="GET",
                url=f"{URL(self.base_url)}/q/health/live",
            ) as response:
                LOG.debug("PID API status is: %s.", response.status)
                content = await response.json()
                if content["status"] == "UP":
                    status = "Ok" if (time.time() - start) < 1000 else "Degraded"
                else:
                    status = "Down"
                return {"status": status}
        except ClientConnectorError:
            LOG.exception("Connection cannot be established with PID API.")
            return {"status": "Down"}
        except HTTPError as e:
            LOG.exception("PID API status retrieval failed with: %r.", e)
            return {"status": "Error"}

    # no delete endpoint on PID ms
