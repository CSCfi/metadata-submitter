"""Metax Service."""

from datetime import timedelta
from typing import Any, override

from aiocache import SimpleMemoryCache, cached
from aiohttp import ClientResponse
from yarl import URL

from ..api.models.metax import DraftMetax, FieldOfScience, MetaxFields
from ..api.models.submission import SubmissionMetadata
from ..api.services.metax import MetaxMapper, MetaxService
from ..api.services.ror import RorService
from ..conf.metax import metax_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class MetaxServiceHandler(MetaxService, ServiceHandler):
    """Metax Service."""

    def __init__(self) -> None:
        """Metax Service."""

        # Deferred import to avoid loading environment variables when module is imported.

        self._config = metax_config()

        super().__init__(
            service_name="metax",
            base_url=URL(self._config.METAX_URL),
            http_client_headers={"Authorization": f"Token {self._config.METAX_TOKEN}"},
            healthcheck_url=(URL(self._config.METAX_URL) / "datasets").update_query(limit=1, fields="id"),
            healthcheck_callback=self.healthcheck_callback,
        )

    @override
    @cached(ttl=int(timedelta(weeks=1).total_seconds()), cache=SimpleMemoryCache)  # type: ignore
    async def get_fields_of_science(self) -> list[FieldOfScience]:
        """
        Get Metax fields of science.

        :return: The Metax fields of science.
        """

        resp: dict[str, Any] = await self._request(
            method="GET", path="reference-data/fields-of-science", params={"limit": "1000"}
        )

        fields = [FieldOfScience.model_validate(f) for f in resp.get("results", [])]
        return fields

    async def create_draft_dataset(self, doi: str, title: str, description: str) -> str:
        """Create a draft Metax dataset.

        :param doi: DOI
        :param title: Dataset's title
        :param description: Dataset's description
        :returns: Metax ID
        """

        LOG.debug("Creating draft dataset to Metax service with DOI: %r.", doi)

        draft = DraftMetax(title=title, description=description, persistent_identifier=doi)
        metax_dataset = await self._post_draft(draft.model_dump())
        metax_id: str = metax_dataset["id"]
        LOG.debug("Created draft dataset with Metax ID: %r.", metax_id)

        return metax_id

    async def update_dataset_metadata(
        self, metadata: SubmissionMetadata, metax_id: str, ror_service: RorService
    ) -> None:
        """Update dataset for publishing.

        :param metadata: The submission metadata
        :param metax_id: The Metax ID
        :param ror_service: The ROR service
        """

        LOG.info("Updating Metax fields with ID %r from submission metadata", metax_id)

        metax_mapper = MetaxMapper(self, ror_service)

        metax_data: dict[str, Any] = await self.get_dataset(metax_id)
        # Map DataCite metadata to Metax metadata.
        mapped_metax_data = await metax_mapper.map_metadata(MetaxFields(**metax_data), metadata)
        await self._patch(metax_id, mapped_metax_data.model_dump())

    async def update_dataset_description(self, metax_id: str, description: str) -> None:
        """Update the draft dataset's description.

        :param metax_id: Metax ID
        :param description: Dataset's description with REMS link
        :raises: HTTPError depending on returned error from Metax
        """
        LOG.info("Updating the description of Metax ID: %r.", metax_id)
        await self._patch(metax_id, {"description": {"en": description}})
        LOG.debug("Updated dataset's description with Metax ID: %s", metax_id)

    async def publish_dataset(self, metax_id: str, doi: str) -> dict[str, Any]:
        """Publish draft dataset to Metax service.

        :param metax_id: Metax ID
        :param doi: DOI
        :returns: Published Metax dataset with "state": "published"
        """
        LOG.info("Publishing Metax dataset: %s", metax_id)
        published_dataset = await self._publish(metax_id)
        LOG.debug("Dataset with Metax ID %s and DOI %s has been published to Metax service.", metax_id, doi)
        return published_dataset

    async def delete_dataset(self, metax_id: str) -> None:
        """
        Published dataset: Deleting will hide it from listings.
        Draft dataset: Deleting will removes it permanently.

        :param metax_id: Metax ID
        """
        resp = await self._request(method="DELETE", path=f"/datasets/{metax_id}")
        if resp.get("detail", "No Dataset matches the given query."):
            raise ValueError(f"Invalid Metax ID: {metax_id}")
        LOG.debug("Deleted dataset with Metax ID: %s from Metax service", metax_id)

    async def _post_draft(self, json_data: dict[str, Any]) -> dict[str, Any]:
        """Post call to Metax REST API.

        :param json_data: Dict with request data
        :returns: Metax dataset response
        """
        dataset: dict[str, Any] = await self._request(method="POST", path="/datasets", json_data=json_data)
        LOG.info("Draft dataset is created: %r", dataset)

        return dataset

    async def get_dataset(self, metax_id: str) -> dict[str, Any]:
        """Get Metax dataset.

        :param metax_id: Metax ID
        :returns: The Metax dataset
        """
        resp: dict[str, Any] = await self._request(method="GET", path=f"/datasets/{metax_id}")
        if "not found" in resp.get("detail", "").lower():
            raise ValueError(f"Invalid Metax ID: {metax_id}")
        LOG.info("Retrieved the dataset with Metax ID: %r.", metax_id)

        return resp

    async def _patch(self, metax_id: str, json_data: dict[str, Any]) -> dict[str, Any]:
        """Patch call to Metax REST API.

        :param metax_id: Metax ID
        :param json_data: Mapped metax data
        :returns: Metax dataset
        """
        resp: dict[str, Any] = await self._request(method="PATCH", path=f"/datasets/{metax_id}", json_data=json_data)
        if "not found" in resp.get("detail", "").lower():
            raise ValueError(f"Invalid Metax ID: {metax_id}")
        LOG.info("Dataset with Metax ID %s is updated: %r", metax_id, resp)

        return resp

    async def _publish(self, metax_id: str) -> dict[str, Any]:
        """Post call to Metax REST API publish endpoint.

        :param metax_id: Metax ID
        :returns: Published Metax dataset with "state": "published"
        """
        resp: dict[str, Any] = await self._request(method="POST", path=f"/datasets/{metax_id}/publish")
        if "no dataset matches the given query" in resp.get("detail", "").lower():
            raise ValueError(f"Invalid Metax ID: {metax_id}")
        LOG.info("Dataset with Metax ID %s has been published to Metax service.", metax_id)

        return resp

    @staticmethod
    async def healthcheck_callback(response: ClientResponse) -> bool:
        content = await response.json()
        results = content.get("results", [])
        return len(results) == 1 and results[0].get("id") is not None
