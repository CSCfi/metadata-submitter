"""Tool for registering DOI at DataCite.

The DOI handler from SDA orchestration was used as reference:
https://github.com/neicnordic/sda-orchestration/blob/master/sda_orchestrator/utils/id_ops.py
"""
from typing import Dict, Union
from uuid import uuid4

from aiohttp import web, ClientSession, BasicAuth

from ..helpers.logger import LOG
from ..conf import conf


class DOIHandler:
    """DOI registration methods."""

    def __init__(self) -> None:
        """Get DOI credentials from config."""
        self.doi_api = conf.doi_api
        self.doi_prefix = conf.doi_prefix
        self.doi_user = conf.doi_user
        self.doi_key = conf.doi_key
        self.doi_url = f"{conf.datacite_url.rstrip('/')}/{self.doi_prefix}"

    async def create_draft(self, prefix: Union[str, None] = None) -> Dict:
        """Generate random suffix and POST request a draft DOI to DataCite DOI API."""
        suffix = uuid4().hex[:10]
        doi_suffix = f"{prefix}.{suffix[:4]}-{suffix[4:]}" if prefix else f"{suffix[:4]}-{suffix[4:]}"
        headers = {"Content-Type": "application/json"}
        doi_payload = {"data": {"type": "dois", "attributes": {"doi": f"{self.doi_prefix}/{doi_suffix}"}}}

        auth = BasicAuth(login=self.doi_user, password=self.doi_key)
        async with ClientSession(headers=headers, auth=auth) as session:
            async with session.post(self.doi_api, json=doi_payload) as response:
                if response.status == 201 or response.status == 200:  # This should only ever be 201
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
                    raise web.HTTPBadRequest(reason=reason)  # 400 might not be the correct error for this

        return doi_data
