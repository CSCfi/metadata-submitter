"""Class for handling calls to METAX API."""

import asyncio
from typing import Any, Dict, List

from aiohttp import BasicAuth, ClientConnectorError, ClientSession
from aiohttp.web import (
    HTTPBadRequest,
    HTTPError,
    HTTPForbidden,
    HTTPNotFound,
    HTTPRequestTimeout,
    HTTPServerError,
    HTTPUnauthorized,
    Request,
)

from ..api.middlewares import get_session
from ..api.operators import UserOperator
from ..conf.conf import metax_config
from .logger import LOG
from .metax_mapper import MetaDataMapper
from .retry import retry


class MetaxServiceHandler:
    """API handler for uploading submitter's metadata to METAX service."""

    def __init__(self, req: Request) -> None:
        """Define variables and paths.

        Define variables and paths used for connecting to Metax API and
        default inputs for Metax Dataset creation.

        :param req: HTTP request from calling service
        """
        self.req = req
        self.db_client = self.req.app["db_client"]
        self.auth = BasicAuth(metax_config["username"], metax_config["password"])
        self.metax_url = metax_config["url"]
        self.rest_route = metax_config["rest_route"]
        self.publish_route = metax_config["publish_route"]
        catalog_pid = metax_config["catalog_pid"]

        self.minimal_dataset_template: Dict[Any, Any] = {
            "data_catalog": catalog_pid,
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

    async def get_metadata_provider_user(self) -> str:
        """Get current user's external id.

        :returns: Current users external ID
        """
        current_user = get_session(self.req)["user_info"]
        user_op = UserOperator(self.db_client)
        user = await user_op.read_user(current_user)
        metadata_provider_user = user["externalId"]
        return metadata_provider_user

        """
        async with ClientSession() as sess:
            try:

    @retry(total_tries=5)
    async def _get(self, metax_id: str) -> str:
        async with ClientSession() as sess:
            resp = await sess.get(
                f"{self.metax_url}{self.rest_route}/{metax_id}",
                auth=self.auth,
            )
            status = resp.status
            if status == 200:
                return await resp.json()
            else:
                reason = await resp.text()
                raise self.metax_error(status, reason)

    @retry(total_tries=3)
    async def _post_draft(self, json_data: Dict) -> Dict:
        """Post call to Metax REST API.

        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        async with ClientSession() as sess:
            resp = await sess.post(
                f"{self.metax_url}{self.rest_route}",
                params="draft",
                json=json_data,
                auth=self.auth,
            )
            status = resp.status
            if status == 201:
                metax_data = await resp.json()
                LOG.info(f"Created Metax draft dataset {metax_data['identifier']}")
                return metax_data
            else:
                reason = await resp.text()
                raise self.metax_error(status, reason)

    @retry(total_tries=3)
    async def _put(self, metax_id: str, json_data: Dict) -> Dict:
        """Put call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        async with ClientSession() as sess:
            resp = await sess.put(
                f"{self.metax_url}{self.rest_route}/{metax_id}",
                json=json_data,
                auth=self.auth,
            )
            status = resp.status
            if status == 200:
                LOG.info(f"Updated Metax dataset {metax_id}")
                return await resp.json()
            else:
                reason = await resp.text()
                raise self.metax_error(status, reason)

    @retry(total_tries=3)
    async def _patch(self, metax_id: str, json_data: Dict) -> Dict:
        """Patch call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        async with ClientSession() as sess:
            resp = await sess.patch(
                f"{self.metax_url}{self.rest_route}/{metax_id}",
                json=json_data,
                auth=self.auth,
            )
            status = resp.status
            if status == 200:
                LOG.info(f"Patched Metax dataset {metax_id}")
                return await resp.json()
            else:
                reason = await resp.text()
                raise self.metax_error(status, reason)

    @retry(total_tries=5)
    async def _bulk_patch(self, json_data: Dict) -> Dict:
        """Bulk patch call to Metax REST API.

        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        async with ClientSession() as sess:
            resp = await sess.patch(
                f"{self.metax_url}{self.rest_route}",
                json=json_data,
                auth=self.auth,
            )
            status = resp.status
            if status == 200:
                LOG.info("Updated Metax datasets")
                return await resp.json()
            else:
                reason = await resp.text()
                raise self.metax_error(status, reason)

    @retry((HTTPServerError, ClientConnectorError), 3)
    async def _delete_draft(self, metax_id: str) -> None:
        """Delete draft dataset from Metax service.

        :param metax_id: Identification string pointing to Metax dataset to be deleted
        """
        async with ClientSession() as sess:
            resp = await sess.delete(
                f"{self.metax_url}{self.rest_route}/{metax_id}",
                auth=self.auth,
            )
            status = resp.status
            if status == 204:
                LOG.debug(f"Deleted draft dataset {metax_id} from Metax service")
            else:
                reason = await resp.text()
                raise self.metax_error(status, reason)

    @retry(total_tries=5)
    async def _publish(self, metax_id: str) -> str:
        """Post call to Metax RPC publish endpoint.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        async with ClientSession() as sess:
            resp = await sess.post(
                f"{self.metax_url}{self.publish_route}",
                params={"identifier": metax_id},
                auth=self.auth,
            )
            status = resp.status
            if status == 200:
                LOG.info(f"Metax ID {metax_id} was published to Metax service.")
                res = await resp.json()
                return res["preferred_identifier"]
            else:
                reason = await resp.text()
                raise self.metax_error(status, reason)

    async def post_dataset_as_draft(self, collection: str, data: Dict) -> str:
        """Send draft dataset to Metax.

        Construct Metax dataset data from submitters' Study or Dataset and
        send it as new draft dataset to Metax Dataset API.

        :param collection: Schema of incomming submitters metadata
        :param data: Validated Study or Dataset data dict
        :raises: HTTPError depending on returned error from Metax
        :returns: Metax ID for dataset returned by Metax API
        """
        LOG.debug(
            f"Creating draft dataset to Metax service from Submitter {collection} with accession ID "
            f"{data['accessionId']}"
        )
        try:
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
        except (HTTPRequestTimeout, HTTPServerError, ClientConnectorError):
            return ""

    async def update_draft_dataset(self, collection: str, data: Dict) -> None:
        """Update draft dataset to Metax.

        Construct Metax draft dataset data from submitters' Study or Dataset and
        send it to Metax Dataset API for update.

        :param collection: Schema of incomming submitters metadata
        :param data: Validated Study or Dataset data dict
        :raises: HTTPError depending on returned error from Metax
        :returns: Metax ID for dataset returned by Metax API
        """
        LOG.info(f"Updating {collection} object data to Metax service.")
        try:
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
        except (HTTPRequestTimeout, HTTPServerError, ClientConnectorError) as e:
            LOG.debug(f"Updating draft dataset failed due to: {e}")
            pass

    async def delete_draft_dataset(self, metax_id: str) -> None:
        """Delete draft dataset from Metax service.

        :param metax_id: Identification string pointing to Metax dataset to be deleted
        """
        LOG.info(f"Deleting Metax draft dataset {metax_id}")
        try:
            await self.check_connection()
            await self._delete_draft(metax_id)
        except (HTTPRequestTimeout, HTTPServerError, ClientConnectorError) as e:
            LOG.debug(f"Updating draft dataset failed due to: {e}")
            pass

    async def update_dataset_with_doi_info(self, doi_info: Dict, _metax_ids: List) -> None:
        """Update dataset for publishing.

        :param doi_info: Dict containing info to complete metax dataset metadata
        :param metax_id: Metax id of dataset to be updated
        """
        LOG.info(
            "Updating metadata with datacite info for Metax datasets: "
            f"{','.join([id['metaxIdentifier'] for id in _metax_ids])}"
        )
        await self.check_connection()
        bulk_data = []
        for id in _metax_ids:
            metax_data = await self._get(id["metaxIdentifier"])

            # Map fields from doi info to Metax schema
            mapper = MetaDataMapper(metax_data["research_dataset"], doi_info)
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

    # we dont know exactly what is comming from Metax so we try it all
    def metax_error(self, status: int, resp_json: str) -> HTTPError:
        """Construct Metax dataset's research dataset dictionary from Submitters Dataset.

        :param status: Status code of the HTTP exception
        :param resp_json: Response mesage for returning exeption
        :returns: HTTP error depending on incomming status
        """
        LOG.error(resp_json)
        if status == 400:
            return HTTPBadRequest(reason=resp_json)
        if status == 401:
            return HTTPUnauthorized(reason=resp_json)
        if status == 403:
            return HTTPForbidden(reason=resp_json)
        if status == 404:
            return HTTPNotFound(reason=resp_json)
        else:
            return HTTPServerError(reason=resp_json)
