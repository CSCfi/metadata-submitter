"""File operator class."""
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional, Tuple, Union

from aiohttp import web
from pymongo.errors import ConnectionFailure, OperationFailure

from ...helpers.logger import LOG
from .base import BaseOperator
from .submission import SubmissionOperator


@dataclass
class File:
    """File class that should be used for adding files to DB."""

    name: str
    path: str
    project: str

    # specific to each file version
    bytes: int
    encrypted_checksums: List[Dict[str, str]]
    unencrypted_checksums: List[Dict[str, str]]


class FileOperator(BaseOperator):
    """FileOperator class for handling database operations of files."""

    @staticmethod
    def _from_version_template(file: File, version: int) -> dict:
        """Create a file version.

        :param file: File to be used for the new file version
        """
        _now = int(datetime.now().timestamp())
        return {
            "date": _now,
            "version": version,
            "bytes": file.bytes,
            "submissions": [],
            "published": False,
            "encrypted_checksums": file.encrypted_checksums,
            "unencrypted_checksums": file.unencrypted_checksums,
        }

    @staticmethod
    def _latest_version(file: dict) -> dict:
        """Get the latest version of a file.

        :param file: file data as dict, as in `file` schema
        """
        return max(file["versions"], key=lambda file_version: file_version["version"])

    def _file_from_data(self, file: dict, version: Optional[int] = None) -> File:
        """Make a File from last version of a file document.

        :param file: file data as dict, as in `file` schema
        :param version: version number to extract. Defaults to latest
        :returns: File object
        """
        if version:
            file_version = next((f for f in file["versions"] if f["version"] == version), None)
            if not file_version:
                accession_id = file["accessionId"]
                available = [v["version"] for v in file["versions"]]
                reason = f"Invalid file '{accession_id}' version '{version}'. Available: '{available}'"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
        else:
            file_version = self._latest_version(file)

        return File(
            name=file["name"],
            path=file["path"],
            project=file["project"],
            bytes=file_version["bytes"],
            encrypted_checksums=file_version["encrypted_checksums"],
            unencrypted_checksums=file_version["unencrypted_checksums"],
        )

    async def _create_file(self, file: File) -> str:
        """Create new object file to database.

        If a file with the same path already exists, add a new file version instead.

        :param file: file data as in the `file.json` schema
        :returns: Tuple of File id and file version
        """
        try:
            file_id = self._generate_accession_id()
            file_data = {
                "accessionId": file_id,
                "name": file.name,
                "path": file.path,
                "project": file.project,
                "flagDeleted": False,
                "versions": [self._from_version_template(file, 1)],
            }

            insert_success = await self.db_service.create("file", file_data)
            if not insert_success:
                reason = "Inserting file to database failed for some reason."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            return file_id
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting file to DB: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason)

    async def create_file_or_version(self, file: File) -> Tuple[str, int]:
        """Create new object file to database.

        If a file with the same path already exists, add a new file version instead.

        :param file: file data as in the `file.json` schema
        :returns: Tuple of file accession id and file version
        """
        try:
            file_in_db = await self.db_service.exists_by_key_value("file", "path", file.path)
            if file_in_db:
                if file_in_db["project"] != file.project:
                    reason = f"File '{file.path}' already belongs to another project."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                # pass in list of versions, which returns the file version with the highest version number
                max_version = self._latest_version(file_in_db)["version"]
                file_version = max_version + 1
                accession_id = file_in_db["accessionId"]
                file_data = self._from_version_template(file, file_version)
                await self.db_service.append("file", accession_id, {"versions": file_data})
                if file_in_db["flagDeleted"]:
                    # mark file as available again
                    await self.flag_file_deleted(accession_id, deleted=False)
                return accession_id, file_version

            accession_id = await self._create_file(file)
            LOG.info("Inserting file with ID: %r to database succeeded.", accession_id)
            return accession_id, 1
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting file: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason)

    async def read_file(self, accession_id: str, version: Optional[int] = None) -> File:
        """Read file object from database.

        :param accession_id: Accession ID of the file to read
        :param version: version number to extract. Defaults to latest
        :raises: HTTPBadRequest if reading was not successful
        :returns: File object of the latest file version
        """
        try:
            file = await self.db_service.read("file", accession_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason)
        if not file:
            reason = f"File '{accession_id}' was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        return self._file_from_data(file, version)

    async def read_files(self, accession_ids: List[str]) -> AsyncIterator[File]:
        """Read all files from DB asynchronously.

        :param accession_ids: list of accession_id to get files
        """
        for accession_id in accession_ids:
            yield await self.read_file(accession_id)

    async def read_submission_files(
        self, submission_op: SubmissionOperator, submission_id: str
    ) -> AsyncIterator[Tuple[dict, File]]:
        """Get files in a submission.

        :param submission_op: Submission operator to read files from
        :param submission_id: Submission ID to get files for
        """
        try:
            submission_files = submission_op.get_submission_field(submission_id, "files")
            if not isinstance(submission_files, list):
                reason = f"Reading submission files for '{submission_id}' failed"
                LOG.error(reason)
                raise web.HTTPInternalServerError(reason=reason)
            for submission_file in submission_files:
                version = submission_file["version"]
                accession_id = submission_file["accessionId"]
                file = await self.read_file(accession_id, version)
                yield submission_file, file
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def read_project_files(self, project: str) -> AsyncIterator[File]:
        """Get files available for a project.

        :param project: Project ID to get files for
        """
        try:
            cursor = self.db_service.query("file", {"project": project}, {"_id": False})
            async for file in cursor:
                yield self._file_from_data(file)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def flag_file_deleted(self, accession_id: str, deleted: bool = True) -> Union[str, None]:
        """Flag file as deleted.

        File should not be deleted from DB, only flagged as not available anymore

        :param accession_id: ID of the file to flag as deleted
        :param deleted: Whether file is marked as deleted, set to `False` to mark a file as available again
        :raises: HTTPBadRequest if deleting was not successful
        :returns: ID of the submission deleted from database
        """
        try:
            delete_success = await self.db_service.update("submission", accession_id, {"flagDeleted": deleted})
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while flagging file as deleted, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not delete_success:
            reason = f"Flagging file '{accession_id}' as deleted failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Flagging file with ID: %r as Deleted succeeded.", accession_id)
        return accession_id

    async def add_files_submission(self, files: List[dict], submission_id: str) -> bool:
        """Add files to a submission.

        Doesn't check if files are already present in the submission.

        :param files: list of files according to submission schema
        :param submission_id: Submission ID to add files to
        """
        return await self.db_service.append("submission", submission_id, {"files": {"$each": files}})
