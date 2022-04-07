"""Tool for registering DOI at DataCite.

The DOI handler from SDA orchestration was used as reference:
https://github.com/neicnordic/sda-orchestration/blob/master/sda_orchestrator/utils/id_ops.py
"""
from typing import Dict, Union
from uuid import uuid4

from aiohttp import web, ClientSession, BasicAuth, ClientTimeout

from ..helpers.logger import LOG
from ..conf.conf import doi_config


class DOIHandler:
    """DOI registration methods."""

    def __init__(self) -> None:
        """Get DOI credentials from config."""
        self.doi_api = doi_config["api"]
        self.doi_prefix = doi_config["prefix"]
        self.doi_user = doi_config["user"]
        self.doi_key = doi_config["key"]
        self.doi_url = f"{doi_config['url'].rstrip('/')}/{self.doi_prefix}"
        self.timeout = ClientTimeout(total=2 * 60)  # 2 minutes timeout
        self.headers = {"Content-Type": "application/vnd.api+json"}

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

        auth = BasicAuth(login=self.doi_user, password=self.doi_key)
        async with ClientSession(headers=self.headers, auth=auth) as session:
            async with session.post(self.doi_api, json=doi_payload) as response:
                if response.status == 201:
                    draft_resp = await response.json()
                    full_doi = draft_resp["data"]["attributes"]["doi"]
                    returned_suffix = draft_resp["data"]["attributes"]["suffix"]
                    LOG.info(f"DOI draft created with doi: {full_doi}.")
                    doi_data = {
                        "fullDOI": full_doi,
                        "dataset": f"{self.doi_url}/{returned_suffix.lower()}",
                    }
                else:
                    reason = f"DOI API draft creation request failed with code: {response.status}"
                    LOG.error(reason)
                    raise web.HTTPInternalServerError(reason=reason)

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
        auth = BasicAuth(login=self.doi_user, password=self.doi_key)
        async with ClientSession(headers=self.headers, auth=auth) as session:
            async with session.put(f"{self.doi_api}/{doi_payload['id']}", json=doi_payload) as response:
                if response.status == 200:
                    _resp = await response.json()
                    LOG.info(f"Datacite doi {doi_payload['id']} updated ")
                    LOG.debug(f"Datacite doi {doi_payload['id']} updated, response: {_resp}")
                else:
                    reason = f"DOI API set state request failed with code: {response.status}"
                    LOG.error(reason)
                    raise web.HTTPInternalServerError(reason=reason)

    async def delete(self, doi: str) -> None:
        """Delete DOI and associated metadata.

        Datacite only support deleting draft DOIs.

        :param doi: identifier to be utilized for deleting draft DOI
        :raises: HTTPInternalServerError if we the Datacite draft DOI delete fails
        :returns: None
        """
        auth = BasicAuth(login=self.doi_user, password=self.doi_key)
        async with ClientSession(headers=self.headers, auth=auth) as session:
            async with session.delete(f"{self.doi_api}/{doi}") as response:
                if response.status == 204:
                    LOG.info(f"Datacite doi {doi} deleted.")
                else:
                    reason = f"DOI API delete request failed with code: {response.status}"
                    LOG.error(reason)
                    raise web.HTTPInternalServerError(reason=reason)
