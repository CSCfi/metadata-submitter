"""Tool for registering DOI at DataCite.

The DOI handler from SDA orchestration was used as reference:
https://github.com/neicnordic/sda-orchestration/blob/master/sda_orchestrator/utils/id_ops.py

Api docs and reference: https://support.datacite.org/
Test account access: https://doi.test.datacite.org/sign-in
"""
import time
from typing import Dict, Union
from uuid import uuid4

import ujson
from aiohttp import BasicAuth, ClientTimeout, web
from aiohttp.client_exceptions import ClientConnectorError, InvalidURL
from yarl import URL

from ..conf.conf import doi_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


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

    @staticmethod
    def _process_error(error: str) -> str:
        """Return error message in a human-readable format.

        Errors come as JSON. Example:
        {
            "errors": [
                {
                    "status": "400",
                    "title": "You need to provide a payload following the JSONAPI spec"
                }
            ]
        }
        {
            "errors": [
                {
                    "source": "url",
                    "uid":"10.xxxx/12345",
                    "title":"Can't be blank"
                }
            ]
        }
        """
        if not error:
            return error
        if isinstance(error, str):
            return error

        error_messages = []
        try:
            json_error = ujson.loads(error)
            for e in json_error["errors"]:
                title = e["title"]
                message = title
                if "source" in e:
                    source = e["source"]
                    uid = e["uid"]
                    message = f"Attribute '{source}' in '{uid}': {title}"
                error_messages.append(message)
        except (KeyError, UnicodeDecodeError, ujson.JSONDecodeError):
            LOG.exception("Unexpected format for error message from Datacite, err: %r.", error)

        return " | ".join(error_messages)

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

        draft_resp = await self._request(method="POST", path="/dois", json_data=doi_payload)
        full_doi = draft_resp["data"]["attributes"]["doi"]
        returned_suffix = draft_resp["data"]["attributes"]["suffix"]
        LOG.info("DOI draft created with identifier: %r.", full_doi)
        doi_data = {
            "fullDOI": full_doi,
            "dataset": str(self.base_url / returned_suffix.lower()),
        }

        return doi_data

    async def publish(self, datacite_payload: Dict) -> None:
        """Set DOI and associated metadata.

        We will only support publish event type, and we expect the data to be
        prepared for the update.
        Partial updates are possible.

        :param datacite_payload: Dictionary with payload to send to Datacite
        :raises: HTTPInternalServerError if the Datacite DOI update fails
        """
        _id = datacite_payload["id"]
        await self._request(method="PUT", path=f"/dois/{_id}", json_data=datacite_payload)
        LOG.info("Datacite DOI: %r updated.", _id)

    async def delete(self, doi: str) -> None:
        """Delete DOI and associated metadata.

        Datacite only support deleting draft DOIs.

        :param doi: identifier to be utilized for deleting draft DOI
        :raises: HTTPInternalServerError if we the Datacite draft DOI delete fails
        """
        await self._request(method="DELETE", path=f"/dois/{doi}")
        LOG.info("Datacite DOI: %r deleted.", doi)

    async def _healtcheck(self) -> Dict:
        """Check DOI service hearthbeat.

        This can return only 200 or 500

        :returns: Dict with status of the datacite status
        """
        try:
            start = time.time()
            async with self._client.request(
                method="GET",
                url=f"{self.base_url}/heartbeat",
                timeout=10,
            ) as response:

                content = await response.text()
                LOG.info("Datacite REST API response content is: %s.", content)
                if response.status == 200 and content == "OK":
                    status = "Ok" if (time.time() - start) < 1000 else "Degraded"
                else:
                    status = "Down"

                return {"status": status}
        except ClientConnectorError as e:
            LOG.exception("Datacite REST API is down with error: %r.", e)
            return {"status": "Down"}
        except InvalidURL as e:
            LOG.exception("Metax Datacite API status retrieval failed with: %r.", e)
            return {"status": "Error"}
        except web.HTTPError as e:
            LOG.exception("Datacite REST API status retrieval failed with: %r.", e)
            return {"status": "Error"}
