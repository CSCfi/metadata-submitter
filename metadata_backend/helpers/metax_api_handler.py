"""Class for handling calls to METAX API."""
from typing import Any, Dict, List

import aiohttp
from aiohttp.web import HTTPBadRequest, HTTPError, HTTPForbidden, HTTPNotFound, Request

from ..api.middlewares import get_session
from ..api.operators import UserOperator
from ..conf.conf import metax_config
from .logger import LOG


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

        self.username = metax_config["username"]
        self.password = metax_config["password"]
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
                    "access_type": {"identifier": "http://uri.suomi.fi/codelist/fairdata/access_type/code/restricted"},
                },
                # default
                "publisher": {
                    "@type": "Organization",
                    "name": {
                        "en": "CSC Sensitive Data Services for Research",
                        "fi": "CSC:n Arkaluonteisen datan palveluiden aineistokatalogi",
                    },
                },
            },
        }

    async def get_metadata_provider_user(self) -> str:
        """Get current user's external id.

        returns: current users external ID
        """
        current_user = get_session(self.req)["user_info"]
        user_op = UserOperator(self.db_client)
        user = await user_op.read_user(current_user)
        metadata_provider_user = user["externalId"]
        return metadata_provider_user

    async def post_dataset_as_draft(self, collection: str, data: Dict) -> str:
        """Send draft dataset to Metax.

        Construct Metax dataset data from submitters' Study or Dataset and
        send it as new draft dataset to Metax Dataset API.

        :param collection: schema of incomming submitters metadata
        :param data: validated Study or Dataset data dict
        :raises: HTTPError depending on returned error from Metax
        :returns: Metax ID for dataset returned by Metax API
        """
        metax_dataset = self.minimal_dataset_template
        metax_dataset["metadata_provider_user"] = await self.get_metadata_provider_user()
        if collection == "dataset":
            dataset_data = self.create_metax_dataset_data_from_dataset(data)
        else:
            dataset_data = self.create_metax_dataset_data_from_study(data)
        metax_dataset["research_dataset"] = dataset_data
        LOG.debug(
            f"Creating draft dataset to Metax service from Submitter {collection} with accession ID "
            f"{data['accessionId']}"
        )
        async with aiohttp.ClientSession() as sess:
            resp = await sess.post(
                f"{self.metax_url}{self.rest_route}",
                params="draft",
                json=metax_dataset,
                auth=aiohttp.BasicAuth(self.username, self.password),
            )
            status = resp.status
            if status == 201:
                metax_data = await resp.json()
                LOG.debug(
                    f"Created Metax draft dataset {metax_data['identifier']} from Submitter {collection} "
                    f"{data['accessionId']} with data: {metax_dataset}."
                )
                return metax_data["identifier"]
            else:
                # TODO: how front end should react on this??
                reason = await resp.text()
                raise self.process_error(status, reason)

    async def update_draft_dataset(self, collection: str, data: Dict) -> str:
        """Update draft dataset to Metax.

        Construct Metax draft dataset data from submitters' Study or Dataset and
        send it to Metax Dataset API for update.

        :param collection: schema of incomming submitters metadata
        :param data: validated Study or Dataset data dict
        :raises: HTTPError depending on returned error from Metax
        :returns: Metax ID for dataset returned by Metax API
        """
        metax_dataset = self.minimal_dataset_template
        # TODO: should this be changed if person updating data is different from data creator?
        metax_dataset["metadata_provider_user"] = await self.get_metadata_provider_user()
        if collection == "dataset":
            dataset_data = self.create_metax_dataset_data_from_dataset(data)
        else:
            dataset_data = self.create_metax_dataset_data_from_study(data)
        metax_dataset["research_dataset"] = dataset_data
        LOG.info(f"Sending updated {collection} object data to Metax service.")

        async with aiohttp.ClientSession() as sess:
            resp = await sess.put(
                f'{self.metax_url}{self.rest_route}/{data["metaxIdentifier"]}',
                params="draft",
                json=metax_dataset,
                auth=aiohttp.BasicAuth(self.username, self.password),
            )
            status = resp.status
            if status == 200:
                metax_data = await resp.json()
                LOG.info(f"Updated Metax draft dataset with ID {metax_data['identifier']} with data: {metax_dataset}")
                return metax_data["identifier"]
            else:
                # TODO: how front end should react on this??
                reason = await resp.text()
                raise self.process_error(status, reason)

    async def delete_draft_dataset(self, metax_id: str) -> None:
        """Delete draft dataset from Metax service.

        :param metax_id: Identification string pointing to Metax dataset to be deleted
        """
        async with aiohttp.ClientSession() as sess:
            resp = await sess.delete(
                f"{self.metax_url}{self.rest_route}/{metax_id}",
                auth=aiohttp.BasicAuth(self.username, self.password),
            )
            status = resp.status
            if status == 204:
                LOG.info(f"Deleted draft dataset {metax_id} from Metax service")
            else:
                # TODO: how front end should react on this??
                reason = await resp.text()
                raise self.process_error(status, reason)

    async def publish_dataset(self, _metax_ids: List[Dict]) -> None:
        """Publish draft dataset to Metax service.

        Iterate over the metax ids that need to be published.

        :param _metax_ids: List of metax IDs that include study and datasets
        """
        for object in _metax_ids:
            metax_id = object["metaxIdentifier"]
            doi = object["doi"]
            async with aiohttp.ClientSession() as sess:
                resp = await sess.post(
                    f"{self.metax_url}{self.publish_route}",
                    params={"identifier": metax_id},
                    auth=aiohttp.BasicAuth(self.username, self.password),
                )
                status = resp.status
                if status == 200:
                    preferred_id = await resp.json()
                    if doi != preferred_id["preferred_identifier"]:
                        LOG.warning(
                            f"Metax Preferred Identifier {preferred_id['preferred_identifier']} "
                            f"does not match object's DOI {doi}"
                        )
                    LOG.debug(
                        f"Object with metax ID {object['metaxIdentifier']} and DOI {object['doi']} is "
                        "published to Metax service."
                    )
                else:
                    reason = await resp.text()
                    raise self.process_error(status, reason)
            LOG.info(f"Metax ID {object['metaxIdentifier']} was published to Metax service.")

    def create_metax_dataset_data_from_study(self, data: Dict) -> Dict:
        """Construct Metax dataset's research dataset dictionary from Submitters Study.

        :param data: Study data
        :returns: constructed research dataset
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
    def process_error(self, status: int, resp_json: str) -> HTTPError:
        """Construct Metax dataset's research dataset dictionary from Submitters Dataset.

        :param status: Status code of the HTTP exception
        :param resp_json: Response mesage for returning exeption
        :returns: HTTP error depending on incomming status
        """
        LOG.error(resp_json)
        if status == 400:
            return HTTPBadRequest(reason=resp_json)
        if status == 403:
            return HTTPForbidden(reason=resp_json)
        if status == 404:
            return HTTPNotFound(reason=resp_json)
        else:
            return HTTPError(reason=resp_json)
