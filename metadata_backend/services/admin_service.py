"""NeIC SDA Admin service."""

from typing import Any

from starlette import status
from yarl import URL

from ..api.exceptions import ServiceHandlerSystemException, SystemException
from ..api.models.sda import (
    CreateDatasetRequest,
    DatasetStatus,
    FileItem,
    GetDatasetResponse,
    IngestFileRequest,
    PostAccessionIdRequest,
    UserFilesResponse,
)
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

    async def get_user_files(self, username: str, dataset_id: str = "") -> list[FileItem]:
        """Return information on all the user's files in inbox.

        :param username: Username of the user whose files are retrieved
        :param dataset_id: Dataset accession ID for path prefix filtering
        :returns: List of file information
        """
        admin_auth_headers = self.get_admin_auth_headers()

        user_files_resp: list[dict[str, Any]] = await self._request(
            method="GET",
            path=f"/users/{username}/files",
            params={"path_prefix": f"DATASET_{dataset_id}"} if dataset_id else None,
            headers=admin_auth_headers,
        )
        LOG.info("Fetched files from inbox for user %s", username)
        user_files = UserFilesResponse.model_validate(user_files_resp)
        return user_files.root

    async def ingest_file(self, *, data: IngestFileRequest | None = None, file_id: str | None = None) -> None:
        """Start the ingestion of a file.

        :param data: Request data including 'user' and 'filepath'
        :param file_id: File ID of the file to be ingested
        """
        admin_auth_headers = self.get_admin_auth_headers()

        if data is None and file_id is None:
            raise SystemException("Either data or file_id must be provided for file ingestion")

        if data:
            ingestion_data = {"user": data.user, "filepath": data.filepath}
            await self._request(
                method="POST", path="/file/ingest", json_data=ingestion_data, headers=admin_auth_headers
            )
            LOG.info("File with path %r is being ingested", data.filepath)

        if file_id:
            await self._request(
                method="POST", path="/file/ingest", params={"fileid": file_id}, headers=admin_auth_headers
            )
            LOG.info("File with ID %s is being ingested", file_id)

    async def post_accession_id(
        self, *, data: PostAccessionIdRequest | None = None, file_id: str | None = None, accession_id: str | None = None
    ) -> None:
        """Assign accession ID to a file.

        :param data: Request data including 'user', 'filepath' and 'accessionId'
        :param file_id: File ID of the file to which the accession ID is assigned
        :param accession_id: Accession ID to assign
        """
        admin_auth_headers = self.get_admin_auth_headers()

        if data is None and (file_id is None or accession_id is None):
            raise SystemException("Either data or file_id and accession_id must be provided for posting accession ID")

        if data:
            accession_data = {"user": data.user, "filepath": data.filepath, "accession_id": data.accession_id}
            await self._request(
                method="POST", path="/file/accession", json_data=accession_data, headers=admin_auth_headers
            )
            LOG.info("Accession ID %s assigned to file %s", data.accession_id, data.filepath)

        if file_id and accession_id:
            await self._request(
                method="POST",
                path="/file/accession",
                params={"fileid": file_id, "accessionid": accession_id},
                headers=admin_auth_headers,
            )
            LOG.info("Accession ID %s assigned to file with ID %s", accession_id, file_id)

    async def create_dataset(self, data: CreateDatasetRequest) -> None:
        """Create dataset for user.

        :param data: Request data including 'user', 'accession_ids' and 'dataset_id'
        """
        admin_auth_headers = self.get_admin_auth_headers()
        dataset_data = {"user": data.user, "accession_ids": data.accession_ids, "dataset_id": data.dataset_id}
        await self._request(method="POST", path="/dataset/create", json_data=dataset_data, headers=admin_auth_headers)
        LOG.info("Dataset %s has been created", dataset_data["dataset_id"])

    async def release_dataset(self, dataset: str) -> None:
        """Release dataset for user.

        :param dataset: Dataset accession ID
        """
        admin_auth_headers = self.get_admin_auth_headers()
        await self._request(method="POST", path=f"/dataset/release/{dataset}", headers=admin_auth_headers)
        LOG.info("Dataset %s has been released", dataset)

    async def get_dataset_status(self, dataset: str) -> DatasetStatus | None:
        """Return the current status of a dataset.

        :param dataset: Dataset accession ID
        :returns: the dataset's status, or ``None`` if the Admin API has no record of it yet (not
            created, or reported with a status this client does not recognise).
        """
        admin_auth_headers = self.get_admin_auth_headers()

        try:
            dataset_resp: dict[str, Any] = await self._request(
                method="GET", path=f"/dataset/{dataset}", headers=admin_auth_headers
            )
        except ServiceHandlerSystemException as e:
            if e.service_status_code == status.HTTP_404_NOT_FOUND:
                return None
            raise

        raw_status = GetDatasetResponse.model_validate(dataset_resp).status
        if raw_status is None:
            return None

        try:
            return DatasetStatus(raw_status)
        except ValueError:
            LOG.warning("Unknown dataset status %r for dataset %s", raw_status, dataset)
            return None
