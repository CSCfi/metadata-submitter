"""Class for handling calls to METAX API.

API docs https://metax.fairdata.fi/docs/
Swagger https://metax.fairdata.fi/swagger/v2
"""

import time
from typing import Any

from aiohttp import BasicAuth, ClientTimeout, web
from aiohttp.client_exceptions import ClientConnectorError, InvalidURL
from yarl import URL

from ..api.models.submission import SubmissionMetadata
from ..conf.conf import metax_config
from ..helpers.logger import LOG
from .metax_mapper import MetaDataMapper, SubjectNotFoundException
from .service_handler import ServiceHandler


class MetaxServiceHandler(ServiceHandler):
    """API handler for uploading submitters' metadata to METAX service."""

    service_name = "Metax"

    def __init__(self) -> None:
        """Define variables and paths.

        Define variables and paths used for connecting to Metax API and
        default inputs for Metax Dataset creation.

        :param req: HTTP request from calling service
        """
        metax_url = URL(metax_config["url"])
        super().__init__(
            base_url=metax_url / metax_config["rest_route"][1:],
            auth=BasicAuth(metax_config["username"], metax_config["password"]),
        )

        self.connection_check_url = metax_url
        self.publish_route = metax_url / metax_config["publish_route"][1:]

        self.minimal_dataset_template: dict[Any, Any] = {
            "data_catalog": metax_config["catalog_pid"],
            "metadata_provider_org": "csc.fi",
            "research_dataset": {
                # submitter given DOI
                "preferred_identifier": "",
                "title": {"en": ""},
                # study abstract or dataset description
                "description": {"en": ""},
                # default
                "access_rights": {
                    "access_type": {
                        "in_scheme": "http://uri.suomi.fi/codelist/fairdata/access_type",
                        "identifier": "http://uri.suomi.fi/codelist/fairdata/access_type/code/restricted",
                    }
                },
                # default
                "publisher": {
                    "name": {
                        "en": "CSC Sensitive Data Services for Research",
                        "fi": "CSC:n Arkaluonteisen datan palveluiden aineistokatalogi",
                    },
                    "@type": "Organization",
                },
            },
        }

    async def _get(self, metax_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self._request(method="GET", path=metax_id)
        LOG.info("Got metax dataset with ID: %r.", metax_id)

        return result

    async def _post_draft(self, json_data: dict[str, Any]) -> dict[str, Any]:
        """Post call to Metax REST API.

        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result: dict[str, Any] = await self._request(method="POST", json_data=json_data, params="draft")
        LOG.info("Created Metax draft dataset with ID: %r.", result["identifier"])

        return result

    async def _put(self, metax_id: str, json_data: dict[str, Any]) -> dict[str, Any]:
        """Put call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result: dict[str, Any] = await self._request(method="PUT", path=metax_id, json_data=json_data)
        LOG.info("Metax dataset with ID: %r updated.", metax_id)

        return result

    async def _patch(self, metax_id: str, json_data: dict[str, Any]) -> dict[str, Any]:
        """Patch call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result: dict[str, Any] = await self._request(method="PATCH", path=metax_id, json_data=json_data)
        LOG.info("Patch completed for metax dataset with ID: %r.", metax_id)

        return result

    async def _bulk_patch(self, json_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Bulk patch call to Metax REST API.

        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result: dict[str, Any] = await self._request(method="PATCH", json_data=json_data)
        LOG.info("Bulk patch completed for metax datasets")

        return result

    async def _publish(self, metax_id: str) -> str:
        """Post a call to Metax RPC publish endpoint.

        :param metax_id: ID of dataset to be updated
        :returns: Dict with full Metax dataset
        """
        result: dict[str, Any] = await self._request(
            method="POST", url=self.publish_route, params={"identifier": metax_id}
        )
        LOG.info("Metax ID %s was published to Metax service.", metax_id)

        dataset: str = result["preferred_identifier"]
        return dataset

    async def post_dataset_as_draft(self, user_id: str, doi: str, title: str, description: str) -> str:
        """Create a draft Metax dataset.

        :param user_id: The user id
        :param doi: The DOI
        :param title: The title
        :param description: The description
         :returns: The Metax ID
        """
        LOG.debug("Creating draft dataset to Metax service with DOI: %r.", doi)
        await self.check_connection()
        metax_dataset = self.minimal_dataset_template
        metax_dataset["metadata_provider_user"] = user_id
        research_dataset = self.create_metax_research_dataset(doi, title, description)
        metax_dataset["research_dataset"] = research_dataset

        metax_data = await self._post_draft(metax_dataset)
        LOG.debug("Created Metax draft dataset with data: %r.", metax_data)
        metax_id: str = metax_data["identifier"]
        # Metax service overwrites preferred id (DOI) with temporary id for draft datasets
        # Patching dataset with full research_dataset data updates preferred id to the real one
        LOG.debug("Updating Metax draft dataset with ID: %r with permanent preferred identifier.", metax_id)
        await self._patch(metax_id, {"research_dataset": research_dataset})
        return metax_id

    # async def update_draft_dataset(self, external_id: str, collection: str, data: Dict) -> None:
    #     """Update draft dataset to Metax.
    #
    #     Construct Metax draft dataset data from submitters' Study or Dataset and
    #     send it to Metax Dataset API for update.
    #
    #     :param external_id: external user id, from OIDC provider
    #     :param collection: Schema of incoming submitters' metadata
    #     :param data: Validated Study or Dataset data dict
    #     :raises: HTTPError depending on returned error from Metax
    #     """
    #     LOG.info("Updating collection: %r object data to Metax service.", collection)
    #     await self.check_connection()
    #     metax_dataset = self.minimal_dataset_template
    #     metax_dataset["metadata_provider_user"] = external_id
    #     if collection == "dataset":
    #         dataset_data = self.create_metax_dataset_data_from_dataset(data)
    #     else:
    #         dataset_data = self.create_metax_dataset_data_from_study(data)
    #     metax_dataset["research_dataset"] = dataset_data
    #
    #     metax_data = await self._put(data["metaxIdentifier"], metax_dataset)
    #     LOG.debug("Updated metax ID: %r, new metadata is: %r", data["metaxIdentifier"], metax_data)
    #
    # async def delete_draft_dataset(self, metax_id: str) -> None:
    #     """Delete draft dataset from Metax service.
    #
    #     :param metax_id: Identification string pointing to Metax dataset to be deleted
    #     """
    #     LOG.info("Deleting Metax draft dataset metax ID: %r", metax_id)
    #     await self._delete_draft(metax_id)

    async def update_dataset_metadata(
        self,
        metadata: SubmissionMetadata,
        metax_id: str,
        file_bytes: int,
    ) -> None:
        """Update dataset for publishing.

        :param metadata: The submission metadata
        :param metax_id: The Metax ID
        :param file_bytes: The number of file bytes
        """
        LOG.info("Updating metadata with datacite info for Metax dataset: %r", metax_id)

        metax_data: dict[str, Any] = await self._get(metax_id)

        # Map fields from doi info to Metax schema
        mapper = MetaDataMapper(metax_data["research_dataset"], metadata, file_bytes)
        try:
            mapped_metax_data = await mapper.map_metadata()
        except SubjectNotFoundException as error:
            # in case the datacite subject cannot be mapped to metax field of science
            reason = f"{error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        await self._patch(metax_id, {"identifier": metax_id, "research_dataset": mapped_metax_data})

    async def update_draft_dataset_description(self, metax_id: str, description: str) -> None:
        """Update the description of the draft dataset.

        :param metax_id: metax dataset id
        :param description: New description
        :raises: HTTPError depending on returned error from Metax
        """
        LOG.info("Updating the description of Metax ID: %r.", metax_id)
        data = await self._get(metax_id)
        data["research_dataset"]["description"]["en"] = description
        metax_data = await self._put(metax_id, data)
        LOG.debug("Updated description of Metax ID: %r, new metadata is: %r", metax_id, metax_data)

    async def publish_dataset(self, metax_id: str, doi: str) -> str:
        """Publish draft dataset to Metax service.

        :param metax_id: The metax id
        :param doi: The DOI
        :returns: The Metax preferred ID
        """
        LOG.info("Publishing Metax dataset: %s", metax_id)

        preferred_id = await self._publish(metax_id)

        if doi != preferred_id:
            LOG.warning("Metax Preferred Identifier: %r does not match object's DOI: %r.", preferred_id, doi)

        LOG.debug("Object with Metax ID: %r and DOI: %r is published to Metax service.", metax_id, doi)
        return preferred_id

    def create_metax_research_dataset(self, doi: str, title: str, description: str) -> dict[str, Any]:
        """Create Metax research dataset dictionary.

        :param doi: The DOI
        :param title: The title
        :param description: The description
        :returns: The Metax research dataset dictionary.
        """
        research_dataset: dict[str, Any] = self.minimal_dataset_template["research_dataset"]
        research_dataset["preferred_identifier"] = doi
        research_dataset["title"]["en"] = title
        research_dataset["description"]["en"] = description
        LOG.debug("Created Metax dataset with data: %r", research_dataset)
        return research_dataset

    async def _healthcheck(self) -> dict[str, str]:
        """Check Metax service health.

        This responds with pong, when pinged.

        :returns: Dict with status of the datacite status
        """
        try:
            start = time.time()
            async with self._client.request(
                method="GET",
                url=f"{URL(metax_config['url'])}/watchman/ping/",
                timeout=ClientTimeout(total=10),
            ) as response:
                LOG.debug("Metax REST API status is: %s.", response.status)
                content = await response.text()
                if response.status == 200 and content == "pong":
                    status = "Ok" if (time.time() - start) < 1000 else "Degraded"
                else:
                    status = "Down"

                return {"status": status}
        except ClientConnectorError as e:
            LOG.exception("Metax REST API is down with error: %r.", e)
            return {"status": "Down"}
        except InvalidURL as e:
            LOG.exception("Metax REST API status retrieval failed with: %r.", e)
            return {"status": "Error"}
        except web.HTTPError as e:
            LOG.exception("Metax REST API status retrieval failed with: %r.", e)
            return {"status": "Error"}
