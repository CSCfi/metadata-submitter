"""NeIC SDA Admin service."""

from typing import Any

from yarl import URL

from ..api.exceptions import SystemException
from ..conf.admin import admin_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class AdminServiceHandler(ServiceHandler):
    """NeIC SDA Admin service."""

    def __init__(self) -> None:
        """NeIC SDA Admin service."""

        self._config = admin_config()

        super().__init__(
            service_name="admin",
            base_url=URL(self._config.ADMIN_URL),
            healthcheck_url=URL(self._config.ADMIN_URL) / "ready",
        )

    def get_admin_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for Admin API service."""
        if self._config.ADMIN_TOKEN:
            return {"Authorization": f"Bearer {self._config.ADMIN_TOKEN}"}
        else:
            raise SystemException("Admin token is not configured")

    async def ingest_file(self, data: dict[str, str]) -> None:
        """Start the ingestion of a file.

        :param data: Dict with request data including 'user' and 'filepath'
        :raises: HTTPInternalServerError if the file ingestion fails
        """
        admin_auth_headers = self.get_admin_auth_headers()
        ingestion_data = {"user": data["user"], "filepath": data["filepath"]}
        await self._request(method="POST", path="/file/ingest", json_data=ingestion_data, headers=admin_auth_headers)
        LOG.info("File in submission %s with path %r is being ingested", data["submissionId"], data["filepath"])

    async def get_user_files(self, username: str) -> list[dict[str, Any]]:
        """Return information on all the user's files in inbox.

        :param username: Username of the user whose files are retrieved
        :raises: HTTPInternalServerError if the file ingestion fails
        """
        # TODO(improve): Use ?path_prefix= query param to only fetch files relevant for the submission
        admin_auth_headers = self.get_admin_auth_headers()
        user_files: list[dict[str, Any]] = await self._request(
            method="GET", path=f"/users/{username}/files", headers=admin_auth_headers
        )
        LOG.info("Fetched files from inbox for user %s", username)
        return user_files

    async def post_accession_id(self, data: dict[str, str]) -> None:
        """Assign accession ID to a file.

        :param data: Dict with request data including 'user', 'filepath' and 'accessionId'
        :raises: HTTPInternalServerError if the file ingestion fails
        :raises: HTTPBadRequest if file does not belong to user
        """
        admin_auth_headers = self.get_admin_auth_headers()
        accession_data = {"user": data["user"], "filepath": data["filepath"], "accession_id": data["accessionId"]}
        await self._request(method="POST", path="/file/accession", json_data=accession_data, headers=admin_auth_headers)
        LOG.info("Accession ID %s assigned to file %s", accession_data["accession_id"], accession_data["filepath"])

    async def create_dataset(self, data: dict[str, str | list[str]]) -> None:
        """Create dataset for user.

        :param data: Dict with request data including 'user', 'fileIds' and 'datasetId'
        :raises: HTTPInternalServerError if the file accession IDs are not valid
        """
        admin_auth_headers = self.get_admin_auth_headers()
        dataset_data = {"user": data["user"], "accession_ids": data["fileIds"], "dataset_id": data["datasetId"]}
        await self._request(method="POST", path="/dataset/create", json_data=dataset_data, headers=admin_auth_headers)
        LOG.info("Dataset %s has been created", dataset_data["dataset_id"])

    async def release_dataset(self, dataset: str) -> None:
        """Create dataset for user.

        :param dataset: Dataset accession ID
        :raises: HTTPNotFound if the dataset is not found
        :raises: HTTPBadRequest if the dataset does not have status 'registered'
        """
        admin_auth_headers = self.get_admin_auth_headers()
        await self._request(method="POST", path=f"/dataset/release/{dataset}", headers=admin_auth_headers)
        LOG.info("Dataset %s has been released", dataset)
