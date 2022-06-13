"""Tool for registering DOI at DataCite.

The DOI handler from SDA orchestration was used as reference:
https://github.com/neicnordic/sda-orchestration/blob/master/sda_orchestrator/utils/id_ops.py
"""
from typing import Dict, Union
from uuid import uuid4

from aiohttp import BasicAuth, ClientTimeout
from yarl import URL

from .service_handler import ServiceHandler
from ..helpers.logger import LOG
from ..conf.conf import doi_config


class DataciteServiceHandler(ServiceHandler):
    """DOI registration methods."""

    service_name = "Datacite"

    def __init__(self) -> None:
        """Get DOI credentials from config."""
        super().__init__(
            auth=BasicAuth(login=doi_config["user"], password=doi_config["key"]),
            base_url=URL(doi_config["api"]),
            http_client_timeout=ClientTimeout(total=2 * 60),  # 2 minutes timeout
            http_client_headers={"Content-Type": "application/vnd.api+json"},
        )
        self.doi_prefix = doi_config["prefix"]

    # @property
    # def enabled(self) -> bool:
    #     """True when service is enabled."""
    #     # return doi_config["enabled"]
    #     return True

    async def create_draft(self, prefix: Union[str, None] = None) -> Dict:
        """Generate random suffix and POST request a draft DOI to DataCite DOI API.

        :param prefix: Custom prefix to add to the DOI e.g. study/dataset
        :raises: HTTPInternalServerError if we the Datacite DOI draft registration fails
        :returns: Dictionary with DOI and URL
        """
        suffix = uuid4().hex[:10]
        doi_suffix = f"{prefix}.{suffix[:4]}-{suffix[4:]}" if prefix else f"{suffix[:4]}-{suffix[4:]}"
        # this payload is sufficient to get a draft DOI
        doi_payload = {"data": {"type": "dois", "attributes": {"doi": f"{self.doi_prefix}/{doi_suffix}"}}}

        draft_resp = await self._request(method="POST", json_data=doi_payload)
        full_doi = draft_resp["data"]["attributes"]["doi"]
        returned_suffix = draft_resp["data"]["attributes"]["suffix"]
        LOG.info(f"DOI draft created with doi: {full_doi}.")
        doi_data = {
            "fullDOI": full_doi,
            "dataset": str(self.base_url / returned_suffix.lower()),
        }

        return doi_data

    async def set_state(self, doi_payload: Dict) -> None:
        """Set DOI and associated metadata.

        We will only support publish event type, and we expect the data to be
        prepared for the update.
        Partial updates are possible.

        :param doi_payload: Dictionary with payload to send to Datacite
        :raises: HTTPInternalServerError if the Datacite DOI update fails
        :returns: None
        """
        await self._request(method="PUT", path=doi_payload["id"], json_data=doi_payload)
        LOG.info(f"Datacite doi {doi_payload['id']} updated ")

    async def delete(self, doi: str) -> None:
        """Delete DOI and associated metadata.

        Datacite only support deleting draft DOIs.

        :param doi: identifier to be utilized for deleting draft DOI
        :raises: HTTPInternalServerError if we the Datacite draft DOI delete fails
        :returns: None
        """
        await self._request(method="DELETE", path=doi)
        LOG.info(f"Datacite doi {doi} deleted.")
