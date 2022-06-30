"""Class for handling calls to METAX API."""
from typing import Any, Dict, List

import aiohttp_session
from aiohttp import BasicAuth, web
from yarl import URL

from ..api.operators import UserOperator
from ..conf.conf import metax_config, METAX_ENABLED
from ..helpers.logger import LOG
from .metax_mapper import MetaDataMapper
from .service_handler import ServiceHandler


class MetaxServiceHandler(ServiceHandler):
    """API handler for uploading submitters' metadata to METAX service."""

    service_name = "Metax"

    def __init__(self, req: web.Request) -> None:
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
        self.req = req
        self.db_client = req.app["db_client"]

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

    async def get_metadata_provider_user(self) -> str:
        """Get current user's external id.

        TODO: Remove this!
        :returns: Current users external ID
        """
        session = await aiohttp_session.get_session(self.req)
        current_user = session["user_info"]
        user_op = UserOperator(self.db_client)
        user = await user_op.read_user(current_user)
        metadata_provider_user = user["externalId"]
        return metadata_provider_user

    async def _get(self, metax_id: str) -> dict:
        result = await self._request(method="GET", path=metax_id)
        LOG.info(f"Got metax dataset {metax_id}")

        return result

    async def _post_draft(self, json_data: Dict) -> Dict:
        """Post call to Metax REST API.

        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="POST", json_data=json_data, params="draft")
        LOG.info(f"Created Metax draft dataset {result['identifier']}")

        return result

    async def _put(self, metax_id: str, json_data: Dict) -> Dict:
        """Put call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="PUT", path=metax_id, json_data=json_data)
        LOG.info(f"Metax dataset {metax_id} updated.")

        return result

    async def _patch(self, metax_id: str, json_data: Dict) -> Dict:
        """Patch call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="PATCH", path=metax_id, json_data=json_data)
        LOG.info(f"Patch completed for metax dataset {metax_id}")

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
        LOG.debug(f"Deleted draft dataset {metax_id} from Metax service")

    async def _publish(self, metax_id: str) -> str:
        """Post a call to Metax RPC publish endpoint.

        :param metax_id: ID of dataset to be updated
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="POST", url=self.publish_route, params={"identifier": metax_id})
        LOG.info(f"Metax ID {metax_id} was published to Metax service.")

        return result["preferred_identifier"]

    async def post_dataset_as_draft(self, collection: str, data: Dict) -> str:
        """Send draft dataset to Metax.

        Construct Metax dataset data from submitters' Study or Dataset and
        send it as new draft dataset to Metax Dataset API.

        :param collection: Schema of incoming submitters' metadata
        :param data: Validated Study or Dataset data dict
        :raises: HTTPError depending on returned error from Metax
        :returns: Metax ID for dataset returned by Metax API
        """
        LOG.debug(
            f"Creating draft dataset to Metax service from Submitter {collection} with accession ID "
            f"{data['accessionId']}"
        )
        await self.check_connection()
        metax_dataset = self.minimal_dataset_template
        metax_dataset["metadata_provider_user"] = await self.get_metadata_provider_user()
        if collection == "dataset":
            dataset_data = self.create_metax_dataset_data_from_dataset(data)
        else:
            dataset_data = self.create_metax_dataset_data_from_study(data)
        metax_dataset["research_dataset"] = dataset_data

        metax_data = await self._post_draft(metax_dataset)
        LOG.debug(
            f"Created Metax draft dataset from Submitter {collection} "
            f"{data['accessionId']} with data: {metax_data}."
        )
        metax_id = metax_data["identifier"]
        # Metax service overwrites preferred id (DOI) with temporary id for draft datasets
        # Patching dataset with full research_dataset data updates preferred id to the real one
        LOG.debug(f"Updating Metax draft dataset {metax_id} with permanent preferred identifier.")
        await self._patch(metax_id, {"research_dataset": dataset_data})
        return metax_id

    async def update_draft_dataset(self, collection: str, data: Dict) -> None:
        """Update draft dataset to Metax.

        Construct Metax draft dataset data from submitters' Study or Dataset and
        send it to Metax Dataset API for update.

        :param collection: Schema of incoming submitters' metadata
        :param data: Validated Study or Dataset data dict
        :raises: HTTPError depending on returned error from Metax
        :returns: Metax ID for dataset returned by Metax API
        """
        LOG.info(f"Updating {collection} object data to Metax service.")
        await self.check_connection()
        metax_dataset = self.minimal_dataset_template
        metax_dataset["metadata_provider_user"] = await self.get_metadata_provider_user()
        if collection == "dataset":
            dataset_data = self.create_metax_dataset_data_from_dataset(data)
        else:
            dataset_data = self.create_metax_dataset_data_from_study(data)
        metax_dataset["research_dataset"] = dataset_data

        metax_data = await self._put(data["metaxIdentifier"], metax_dataset)
        LOG.debug(f"Updated Metax ID {data['metaxIdentifier']}, new metadata is: {metax_data}")

    async def delete_draft_dataset(self, metax_id: str) -> None:
        """Delete draft dataset from Metax service.

        :param metax_id: Identification string pointing to Metax dataset to be deleted
        """
        LOG.info(f"Deleting Metax draft dataset {metax_id}")
        await self._delete_draft(metax_id)

    async def update_dataset_with_doi_info(self, datacite_info: Dict, _metax_ids: List) -> None:
        """Update dataset for publishing.

        :param datacite_info: Dict containing info to complete metax dataset metadata
        :param _metax_ids: List of Metax id of dataset to be updated
        """
        LOG.info(
            "Updating metadata with datacite info for Metax datasets: "
            f"{','.join([id['metaxIdentifier'] for id in _metax_ids])}"
        )
        bulk_data = []
        for id in _metax_ids:
            metax_data: dict = await self._get(id["metaxIdentifier"])

            # Map fields from doi info to Metax schema
            mapper = MetaDataMapper(id["schema"], metax_data["research_dataset"], datacite_info)
            mapped_metax_data = mapper.map_metadata()

            bulk_data.append({"identifier": id["metaxIdentifier"], "research_dataset": mapped_metax_data})

        await self._bulk_patch(bulk_data)

    async def publish_dataset(self, _metax_ids: List[Dict]) -> None:
        """Publish draft dataset to Metax service.

        Iterate over the metax ids that need to be published.

        :param _metax_ids: List of metax IDs that include study and datasets
        """
        LOG.info(f"Publishing Metax datasets {','.join([id['metaxIdentifier'] for id in _metax_ids])}")

        for object in _metax_ids:
            metax_id = object["metaxIdentifier"]
            doi = object["doi"]
            preferred_id = await self._publish(metax_id)

            if doi != preferred_id:
                LOG.warning(f"Metax Preferred Identifier {preferred_id} " f"does not match object's DOI {doi}")
            LOG.debug(
                f"Object with metax ID {object['metaxIdentifier']} and DOI {object['doi']} is "
                "published to Metax service."
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
        LOG.debug(f"Created Metax dataset from Study with data: {research_dataset}")
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
        LOG.debug(f"Created Metax dataset from Dataset with data: {research_dataset}")
        return research_dataset
