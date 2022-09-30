"""Class for handling calls to METAX API.

API docs https://metax.fairdata.fi/docs/
Swagger https://metax.fairdata.fi/swagger/v2
"""
import time
from typing import Any, Dict, List

from aiohttp import BasicAuth, web
from aiohttp.client_exceptions import ClientConnectorError, InvalidURL
from yarl import URL

from ..conf.conf import METAX_ENABLED, metax_config
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

        self.minimal_dataset_template: Dict[Any, Any] = {
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

    @property
    def enabled(self) -> bool:
        """Indicate whether service is enabled."""
        return METAX_ENABLED

    async def _get(self, metax_id: str) -> dict:
        result = await self._request(method="GET", path=metax_id)
        LOG.info("Got metax dataset with ID: %r.", metax_id)

        return result

    async def _post_draft(self, json_data: Dict) -> Dict:
        """Post call to Metax REST API.

        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="POST", json_data=json_data, params="draft")
        LOG.info("Created Metax draft dataset with ID: %r.", result["identifier"])

        return result

    async def _put(self, metax_id: str, json_data: Dict) -> Dict:
        """Put call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="PUT", path=metax_id, json_data=json_data)
        LOG.info("Metax dataset with ID: %r updated.", metax_id)

        return result

    async def _patch(self, metax_id: str, json_data: Dict) -> Dict:
        """Patch call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="PATCH", path=metax_id, json_data=json_data)
        LOG.info("Patch completed for metax dataset with ID: %r.", metax_id)

        return result

    async def _bulk_patch(self, json_data: List[Dict]) -> Dict:
        """Bulk patch call to Metax REST API.

        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="PATCH", json_data=json_data)
        LOG.info("Bulk patch completed for metax datasets")

        return result

    async def _delete_draft(self, metax_id: str) -> None:
        """Delete draft dataset from Metax service.

        :param metax_id: Identification string pointing to Metax dataset to be deleted
        """
        await self._request(method="DELETE", path=metax_id)
        LOG.debug("Deleted draft dataset metax ID: %r from Metax service", metax_id)

    async def _publish(self, metax_id: str) -> str:
        """Post a call to Metax RPC publish endpoint.

        :param metax_id: ID of dataset to be updated
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="POST", url=self.publish_route, params={"identifier": metax_id})
        LOG.info("Metax ID %s was published to Metax service.", metax_id)

        return result["preferred_identifier"]

    async def post_dataset_as_draft(self, external_id: str, collection: str, data: Dict) -> str:
        """Send draft dataset to Metax.

        Construct Metax dataset data from submitters' Study or Dataset and
        send it as new draft dataset to Metax Dataset API.

        :param external_id: external user id, from OIDC provider
        :param collection: Schema of incoming submitters' metadata
        :param data: Validated Study or Dataset data dict
        :raises: HTTPError depending on returned error from Metax
        :returns: Metax ID for dataset returned by Metax API
        """
        LOG.debug(
            "Creating draft dataset to Metax service from collection: %r with accession ID: %r.",
            collection,
            {data["accessionId"]},
        )
        await self.check_connection()
        metax_dataset = self.minimal_dataset_template
        metax_dataset["metadata_provider_user"] = external_id
        if collection == "dataset":
            dataset_data = self.create_metax_dataset_data_from_dataset(data)
        else:
            dataset_data = self.create_metax_dataset_data_from_study(data)
        metax_dataset["research_dataset"] = dataset_data

        metax_data = await self._post_draft(metax_dataset)
        LOG.debug(
            "Created Metax draft dataset for: %r with accession ID: %r with data: %r.",
            collection,
            data["accessionId"],
            metax_data,
        )
        metax_id = metax_data["identifier"]
        # Metax service overwrites preferred id (DOI) with temporary id for draft datasets
        # Patching dataset with full research_dataset data updates preferred id to the real one
        LOG.debug("Updating Metax draft dataset with ID: %r with permanent preferred identifier.", metax_id)
        await self._patch(metax_id, {"research_dataset": dataset_data})
        return metax_id

    async def update_draft_dataset(self, external_id: str, collection: str, data: Dict) -> None:
        """Update draft dataset to Metax.

        Construct Metax draft dataset data from submitters' Study or Dataset and
        send it to Metax Dataset API for update.

        :param external_id: external user id, from OIDC provider
        :param collection: Schema of incoming submitters' metadata
        :param data: Validated Study or Dataset data dict
        :raises: HTTPError depending on returned error from Metax
        """
        LOG.info("Updating collection: %r object data to Metax service.", collection)
        await self.check_connection()
        metax_dataset = self.minimal_dataset_template
        metax_dataset["metadata_provider_user"] = external_id
        if collection == "dataset":
            dataset_data = self.create_metax_dataset_data_from_dataset(data)
        else:
            dataset_data = self.create_metax_dataset_data_from_study(data)
        metax_dataset["research_dataset"] = dataset_data

        metax_data = await self._put(data["metaxIdentifier"], metax_dataset)
        LOG.debug("Updated metax ID: %r, new metadata is: %r", data["metaxIdentifier"], metax_data)

    async def delete_draft_dataset(self, metax_id: str) -> None:
        """Delete draft dataset from Metax service.

        :param metax_id: Identification string pointing to Metax dataset to be deleted
        """
        LOG.info("Deleting Metax draft dataset metax ID: %r", metax_id)
        await self._delete_draft(metax_id)

    async def update_dataset_with_doi_info(self, datacite_info: Dict, _metax_ids: List) -> None:
        """Update dataset for publishing.

        :param datacite_info: Dict containing info to complete metax dataset metadata
        :param _metax_ids: List of Metax id of dataset to be updated
        :raises: HTTPBadRequest if mapping datacite info to metax fails
        """
        LOG.info(
            "Updating metadata with datacite info for Metax datasets: %r",
            ",".join([id["metaxIdentifier"] for id in _metax_ids]),
        )
        bulk_data = []
        for metax_id in _metax_ids:
            metax_data: dict = await self._get(metax_id["metaxIdentifier"])

            # Map fields from doi info to Metax schema
            mapper = MetaDataMapper(metax_id["schema"], metax_data["research_dataset"], datacite_info)
            try:
                mapped_metax_data = mapper.map_metadata()
            except SubjectNotFoundException as error:
                # in case the datacite subject cannot be mapped to metax field of science
                reason = f"{error}"
                LOG.exception(reason)
                raise web.HTTPBadRequest(reason=reason)

            bulk_data.append({"identifier": metax_id["metaxIdentifier"], "research_dataset": mapped_metax_data})

        await self._bulk_patch(bulk_data)

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

    async def publish_dataset(self, _metax_ids: List[Dict]) -> None:
        """Publish draft dataset to Metax service.

        Iterate over the metax ids that need to be published.

        :param _metax_ids: List of metax IDs that include study and datasets
        """
        LOG.info("Publishing Metax datasets: %s", ",".join([id["metaxIdentifier"] for id in _metax_ids]))

        for obj in _metax_ids:
            metax_id = obj["metaxIdentifier"]
            doi = obj["doi"]
            preferred_id = await self._publish(metax_id)

            if doi != preferred_id:
                LOG.warning("Metax Preferred Identifier: %r does not match object's DOI: %r.", preferred_id, doi)
            LOG.debug(
                "Object with Metax ID: %r and DOI: %r is published to Metax service.",
                obj["metaxIdentifier"],
                obj["doi"],
            )

    def create_metax_dataset_data_from_study(self, data: Dict) -> Dict:
        """Construct Metax dataset's research dataset dictionary from Submitters Study.

        :param data: Study data
        :returns: Constructed research dataset
        """
        research_dataset = self.minimal_dataset_template["research_dataset"]
        research_dataset["preferred_identifier"] = data["doi"]
        research_dataset["title"]["en"] = data["descriptor"]["studyTitle"]
        research_dataset["description"]["en"] = data["descriptor"]["studyAbstract"]
        LOG.debug("Created Metax dataset from Study with data: %r", research_dataset)
        return research_dataset

    def create_metax_dataset_data_from_dataset(self, data: Dict) -> Dict:
        """Construct Metax dataset's research dataset dictionary from Submitters Dataset.

        :param data: Dataset data
        :returns: constructed research dataset
        """
        research_dataset = self.minimal_dataset_template["research_dataset"]
        research_dataset["preferred_identifier"] = data["doi"]
        research_dataset["title"]["en"] = data["title"]
        research_dataset["description"]["en"] = data["description"]
        LOG.debug("Created Metax dataset from Dataset with data: %r", research_dataset)
        return research_dataset

    async def _healtcheck(self) -> Dict:
        """Check Metax service health.

        This responds with pong, when pinged.

        :returns: Dict with status of the datacite status
        """
        try:
            start = time.time()
            async with self._client.request(
                method="GET",
                url=f"{URL(metax_config['url'])}/watchman/ping/",
                timeout=10,
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
