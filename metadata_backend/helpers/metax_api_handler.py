"""Class for handling calls to METAX API."""
from typing import Any, Dict, List, Union

import aiohttp_session
from aiohttp import BasicAuth, ClientSession
from aiohttp.web import (
    HTTPError,
    HTTPGatewayTimeout,
    HTTPInternalServerError,
    Request,
)

from ..api.operators import UserOperator
from ..conf.conf import metax_config
from .logger import LOG
from .metax_mapper import MetaDataMapper
from .retry import retry


class MetaxServerError(HTTPError):
    """Metax server errors should produce a 502 Bad Gateway response."""

    status_code = 502


class MetaxClientError(HTTPError):
    """Metax client errors should be raised unmodified."""

    def __init__(
        self,
        status_code: int,
        **kwargs: Any,
    ) -> None:
        """Class to raise for Metax http client errors.

        HTTPError doesn't have a setter for status_code, so this allows setting it.

        :param status_code: Set the status code here, as
        """
        self.status_code = status_code
        HTTPError.__init__(self, **kwargs)


def metax_exception(reason: str, status: int) -> HTTPError:
    """Create a Client or Server exception, according to status code.

    :param reason: Error message
    :param status: HTTP status code
    :returns MetaxServerError or MetaxClientError. HTTPInternalServerError on invalid input
    """
    if status < 400:
        LOG.error(f"HTTP status code must be an error code, >400 received {status}.")
        return HTTPInternalServerError(reason="Server encountered an unexpected situation.")
    reason = f"Metax error {status}: {reason}"
    if status >= 500:
        return MetaxServerError(text=reason, reason=reason)
    return MetaxClientError(text=reason, reason=reason, status_code=status)


class MetaxServiceHandler:
    """API handler for uploading submitters' metadata to METAX service."""

    def __init__(self, req: Request) -> None:
        """Define variables and paths.

        Define variables and paths used for connecting to Metax API and
        default inputs for Metax Dataset creation.

        :param req: HTTP request from calling service
        """
        self.req = req
        self.db_client = self.req.app["db_client"]
        self.enabled = metax_config["enabled"]
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
        session = await aiohttp_session.get_session(self.req)
        current_user = session["user_info"]
        user_op = UserOperator(self.db_client)
        user = await user_op.read_user(current_user)
        metadata_provider_user = user["externalId"]
        return metadata_provider_user

    async def check_connection(self, timeout: int = 2) -> None:
        """Check connection for Metax server.

        The request should raise exceptions if it fails, and interrupt code execution.

        :param timeout: Request operations timeout
        """
        await self._request(method="HEAD", url=self.metax_url, timeout=2)

    @retry(total_tries=5)
    async def _request(
        self,
        method: str = "GET",
        url: str = None,
        metax_id: str = None,
        params: Union[str, dict] = None,
        json_data: Any = None,
        timeout: int = 10,
    ) -> Union[str, dict]:
        """Request to Metax REST API.

        :param method: HTTP method
        :param url: Full metax url. If None, one is created
        :param metax_id: ID of a dataset
        :param params: URL parameters, must be url encoded
        :param json_data: Dict with request data
        :param timeout: Request timeout
        :returns: Response body parsed as JSON
        """
        if method not in {"HEAD", "GET", "POST", "PUT", "DELETE", "PATCH"}:
            message = f"{method} request to Metax is not supported."
            LOG.error(message)
            raise HTTPInternalServerError(reason=message)

        if not url:
            url = f"{self.metax_url}{self.rest_route}"
            if metax_id:
                url = f"{self.metax_url}{self.rest_route}/{metax_id}"

        async with ClientSession() as sess:
            try:
                response = await sess.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    auth=self.auth,
                    timeout=timeout,
                )

                if response.content_type.endswith("json"):
                    content = await response.json()
                else:
                    content = await response.text()
                    # We should get a JSON response from metax in most requests.
                    if method in {"GET", "POST", "PUT", "PATCH"}:
                        message = f"{method} request to Metax '{url}' returned an unexpected answer: {content:!r}."
                        LOG.error(message)
                        raise MetaxServerError(text=message, reason=message)

                if not response.ok:
                    log_msg = f"{method} request to Metax '{url}' returned a {response.status}."
                    if content:
                        log_msg += f" Content: {content}"
                    LOG.error(log_msg)
                    raise metax_exception(reason=content, status=response.status)

                return content

            except TimeoutError:
                LOG.exception(f"{method} request to Metax '{url}' timed out.")
                raise HTTPGatewayTimeout(reason="Metax error: Could not reach Metax service provider.")
            except HTTPError:
                # These are expected
                raise
            except Exception:
                LOG.exception(f"{method} request to Metax '{url}' raised an unexpected exception.")
                message = "Metax error 502: Unexpected issue when connecting to Metax service provider."
                raise MetaxServerError(text=message, reason=message)

    async def _get(self, metax_id: str) -> dict:
        result = await self._request(method="GET", metax_id=metax_id)
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
        result = await self._request(method="PUT", metax_id=metax_id, json_data=json_data)
        LOG.info(f"Metax dataset {metax_id} updated.")

        return result

    async def _patch(self, metax_id: str, json_data: Dict) -> Dict:
        """Patch call to Metax REST API.

        :param metax_id: ID of dataset to be updated
        :param json_data: Dict with request data
        :returns: Dict with full Metax dataset
        """
        result = await self._request(method="PATCH", metax_id=metax_id, json_data=json_data)
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
        await self._request(method="DELETE", metax_id=metax_id)
        LOG.debug(f"Deleted draft dataset {metax_id} from Metax service")

    async def _publish(self, metax_id: str) -> str:
        """Post a call to Metax RPC publish endpoint.

        :param metax_id: ID of dataset to be updated
        :returns: Dict with full Metax dataset
        """
        result = await self._request(
            method="POST", url=f"{self.metax_url}{self.publish_route}", params={"identifier": metax_id}
        )
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

    async def update_dataset_with_doi_info(self, doi_info: Dict, _metax_ids: List) -> None:
        """Update dataset for publishing.

        :param doi_info: Dict containing info to complete metax dataset metadata
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
