"""File operator class."""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import ujson
from aiohttp import web
from pymongo.errors import ConnectionFailure, OperationFailure

from ...helpers.logger import LOG
from .base import BaseOperator


@dataclass
class File:
    """File class that should be used for handling a file version."""

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

    async def _create_file(self, file: File) -> str:
        """Create new object file to database.

        If a file with the same path already exists, add a new file version instead.

        :raises: HTTPBadRequest if file creation in the db was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
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
            raise web.HTTPInternalServerError(reason=reason) from error

    async def create_file_or_version(self, file: File) -> Tuple[str, int]:
        """Create new object file to database.

        If a file with the same path already exists, add a new file version instead.

        :param file: file data as in the `file.json` schema
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: Tuple of file accession id and file version
        """
        _projection = {
            "_id": 0,
            "accessionId": 1,
            # get only the last version of a file
            "currentVersion": {"$first": {"$sortArray": {"input": "$versions", "sortBy": {"version": -1}}}},
        }
        try:
            file_in_db = await self.db_service.read_by_key_value(
                "file", {"path": file.path, "projectId": file.project}, _projection
            )
            if file_in_db:
                accession_id = file_in_db["accessionId"]
                file_in_db = file_in_db["currentVersion"]

                # pass latest versions number
                _current_version = file_in_db["version"]
                file_version = _current_version + 1
                version_data = self._from_version_template(file, file_version)
                await self.db_service.append(
                    "file",
                    accession_id,
                    # update flagDeleted to false if a new version is added.
                    {"$set": {"flagDeleted": False}, "$addToSet": {"versions": version_data}},
                    upsert=True,
                )
                return accession_id, file_version

            accession_id = await self._create_file(file)
            LOG.info("Inserting file with ID: %r to database succeeded.", accession_id)
            return accession_id, 1
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting file: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def read_file(self, accession_id: str, version: Optional[int] = None) -> Dict:
        """Read file object from database.

        :param accession_id: Accession ID of the file to read
        :param version: version number to extract. Defaults to latest
        :raises: HTTPBadRequest if reading was not successful
        :raises: HTTPNotFound if file not found
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: File object of the latest file version
        """
        aggregate_query = [
            {"$match": {"accessionId": accession_id}},
            {"$unwind": "$versions"},
            {
                "$project": {
                    "_id": 0,
                    "name": 1,
                    "path": 1,
                    "project": 1,
                    "bytes": "$versions.bytes",
                    "encrypted_checksums": "$versions.encrypted_checksums",
                    "unencrypted_checksums": "$versions.unencrypted_checksums",
                }
            },
        ]
        if version:
            # get a specific version
            aggregate_query.insert(2, {"$match": {"versions.version": version}})
        else:
            # sort to get the latest version
            aggregate_query.insert(2, {"$sort": {"versions.version": -1}})
            # get only the latest version
            aggregate_query.insert(3, {"$limit": 1})
        try:
            file = await self.db_service.do_aggregate("file", aggregate_query)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not file:
            reason = f"File '{accession_id}' was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        return file[0]

    async def read_project_files(self, project_id: str) -> List[Dict]:
        """Read files from DB based on a specific filter type and corresponding identifier.

        The files are read by the latest version, and filtered either by projectId.

        :param project_id: Project ID to get files for
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: List of files
        """
        aggregate_query = [
            {"$match": {"projectId": project_id}},
            {"$sort": {"versions.version": -1}},
            {"$unwind": "$versions"},
            {
                "$project": {
                    "_id": 0,
                    "name": 1,
                    "path": 1,
                    "project": 1,
                    "bytes": "$version.bytes",
                    "encrypted_checksums": "$version.encrypted_checksums",
                    "unencrypted_checksums": "$version.unencrypted_checksums",
                }
            },
        ]
        try:
            return await self.db_service.do_aggregate("file", aggregate_query)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting files for project {project_id}, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def check_submission_files_ready(self, submission_id: str) -> None:
        """Check all files in a submission are marked as ready.

        Files marked as ready in a submission, means an metadata object has been
        attached to the file.

        :param submission_id: Submission ID to get associated files status
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        aggregate_query = [
            {"$match": {"submissionId": submission_id}},
            {"$unwind": "$files"},
            # check the status is not in failed or added
            # failed can occour when an file ingestion/verification/mapping fails
            {"$match": {"files.status": {"$in": ["added", "failed"]}}},
            {
                "$project": {
                    "_id": 0,
                    "accessionId": "$files.accessionId",
                    "version": "$files.version",
                    "status": "$files.status",
                }
            },
        ]
        try:
            problematic_files = await self.db_service.do_aggregate("submission", aggregate_query)
            if len(problematic_files) > 0:
                reason = (
                    f"There are a problematic files: {','.join([i['accessionId'] for i in problematic_files])} "
                    f"in the submission with id: {submission_id}"
                )
                LOG.error(reason)
                raise web.HTTPBadRequest(
                    reason=reason,
                    text=ujson.dumps({"problematic-files": problematic_files}),
                    content_type="application/json",
                )
            LOG.debug("All files have been marked as ready")
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def read_submission_files(self, submission_id: str, expected_status: Optional[List] = None) -> List[Dict]:
        """Get files in a submission.

        The files are identified in a submission by version.

        :param submission_id: Submission ID to read files associated with a submission
        :param expected_status: List of expected statuses (can be one or more statuses)
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue or db aggregate does not return a list
        :returns: List of files specific to a submission
        """
        aggregate_query = [
            {"$match": {"submissionId": submission_id}},
            {"$unwind": "$files"},
            {"$project": {"_id": 0, "accessionId": "$files.accessionId", "version": "$files.version"}},
        ]
        if expected_status:
            # we match only the files that have a specific status
            aggregate_query.insert(
                2,
                {"$match": {"files.status": {"$in": expected_status}}},
            )
        files = []
        try:
            submission_files = await self.db_service.do_aggregate("submission", aggregate_query)
            if not isinstance(submission_files, list):
                reason = f"Reading submission files for '{submission_id}' failed"
                LOG.error(reason)
                raise web.HTTPInternalServerError(reason=reason)
            for file in submission_files:
                files.append(await self.read_file(file["accessionId"], file["version"]))

            return files
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def flag_file_deleted(self, file_path: str, deleted: bool = True) -> None:
        """Flag file as deleted.

        File should not be deleted from DB, only flagged as not available anymore

        :param file_path: Path of the file to flag as deleted
        :param deleted: Whether file is marked as deleted, set to `False` to mark a file as available again
        :raises: HTTPBadRequest if deleting was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        try:
            delete_success = await self.db_service.update_by_key_value(
                "file", {"path": file_path}, {"flagDeleted": deleted}
            )
            await self.remove_file_submission(file_path, id_type="path")
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while flagging file as deleted, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not delete_success:
            reason = f"Flagging file with '{file_path}' as deleted failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Flagging file with file_path: %r as Deleted succeeded.", file_path)

    async def remove_file_submission(
        self, accession_id: str, id_type: Optional[str] = None, submission_id: Optional[str] = None
    ) -> None:
        """Flag file as deleted.

        If we flag the file as deleted we should remove it from any submission it has been attached to

        :param accession_id: Accession ID of the file to read
        :param id_type: depending on the file id this can be either ``path`` or ``accessionId``.
        :param submission_id: Submission ID to remove file associated with it
        :raises: HTTPBadRequest if deleting was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        try:
            if id_type == "path":
                _fileId = await self.db_service.read_by_key_value("file", {"path": accession_id}, {"accessionId": 1})
            elif id_type == "accessionId":
                _fileId["accessionId"] = accession_id
            else:
                reason = f"Cannot recognize '{id_type}' as a type of id for file deletion from submission."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            if submission_id:
                delete_success = await self.db_service.remove(
                    "submission", submission_id, {"files": {"accession_id": _fileId["accessionId"]}}
                )
                LOG.info("Removing file: %r from submission: %r succeeded.", accession_id, submission_id)
            else:
                delete_success = await self.db_service.remove_many(
                    "submission", {"files": {"accession_id": _fileId["accessionId"]}}
                )
                LOG.info(
                    "Removing file with path: %r from submissions, by accessionID: %r succeeded.",
                    accession_id,
                    _fileId["accessionId"],
                )
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while removing file from submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not delete_success:
            reason = f"Removing file identified via '{id_type}': '{accession_id}' from submission failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def update_file_submission(self, accession_id: str, submission_id: str, update_data: dict) -> None:
        """Update file in a submission.

        File should not be deleted from DB, only flagged as not available anymore

        :param accession_id: Accession ID of the file to update
        :param submission_id: Submission ID to update file associated with it
        :param update_data: Mongodb ``$set`` operation to be performed on the submission
        :raises: HTTPBadRequest if deleting was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        try:
            update_success = await self.db_service.update_by_key_value(
                "submission",
                {"submissionId": submission_id, "files": {"$elemMatch": {"accessionId": accession_id}}},
                # this can take the form of: {"files.$.status": "failed"} or
                # {"files.$.status": "failed", "files.$.version": 3,
                # "files.$.objectId": {"accessionId": 4, "schema": "study"}
                # ideally we check before that we don't update the accessionId
                update_data,
            )
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while updating file in submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not update_success:
            reason = f"Updating file with '{accession_id}' in '{submission_id}' failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Updating file with file ID: %r in submission %r succeeded.", accession_id, submission_id)

    async def add_files_submission(self, files: List[dict], submission_id: str) -> bool:
        """Add files to a submission.

        Doesn't check if files are already present in the submission.

        :param files: list of files according to submission schema
        :param submission_id: Submission ID to add files to
        :returns: True if operation to append was successful
        """
        return await self.db_service.append("submission", submission_id, {"$addToSet": {"files": {"$each": files}}})
