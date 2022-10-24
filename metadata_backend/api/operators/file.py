"""File operator class."""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from aiohttp import web
from pymongo.errors import ConnectionFailure, OperationFailure

from ...helpers.logger import LOG
from .base import BaseOperator


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

    # def _file_from_data(self, file: dict) -> File:
    #     """Make a File from last version of a file document.

    #     :param file: file data as dict, as in `file` schema
    #     :param version: version number to extract. Defaults to latest
    #     :returns: File object
    #     """
    #     return File(
    #         name=file["name"],
    #         path=file["path"],
    #         project=file["project"],
    #         bytes=file["bytes"],
    #         encrypted_checksums=file["encrypted_checksums"],
    #         unencrypted_checksums=file["unencrypted_checksums"],
    #     )

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
        _projection = {
            "_id": 0,
            "currentVersion": {"$first": {"$sortArray": {"input": "$versions", "sortBy": {"version": -1}}}},
        }
        try:
            file_in_db = await self.db_service.read_by_key_value("file", "path", file.path, _projection)
            if file_in_db:
                if file_in_db["project"] != file.project:
                    reason = f"File '{file.path}' already belongs to another project."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                # pass in list of versions, which returns the file version with the highest version number
                _current_version = file_in_db["currentVersion"]["version"]
                file_version = _current_version + 1
                accession_id = file_in_db["accessionId"]
                version_data = self._from_version_template(file, file_version)
                await self.db_service.append(
                    "file",
                    accession_id,
                    # update flagDeleted to false if a new version is added.
                    {"$set": {"flagDeleted": False}, "$addToSet": {"versions": version_data}},
                    upsert=True,
                )

            accession_id = await self._create_file(file)
            LOG.info("Inserting file with ID: %r to database succeeded.", accession_id)
            return accession_id, 1
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting file: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason)

    async def read_file(self, accession_id: str, version: Optional[int] = None) -> Dict:
        """Read file object from database.

        :param accession_id: Accession ID of the file to read
        :param version: version number to extract. Defaults to latest
        :raises: HTTPBadRequest if reading was not successful
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
            raise web.HTTPInternalServerError(reason=reason)
        if not file:
            reason = f"File '{accession_id}' was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        return file[0]

    # TO_DO figure out if we need this
    # async def read_files(self, filter_type: str, identifiers: List[str]) -> List[Dict]:
    #     """Read files from DB based on a specific filter type and corresponding identifier.

    #     The files are read by the latest version, filtered either by list of projectId or accessionId.

    #     :param filter_type: Type of filter for the query. Can be accessionId or projectId
    #     :param identifiers: list of accession IDs or project IDs to get files
    #     :returns: List of files
    #     """
    #     _specific_version = {"$filter": {"input": "$versions", "as": "item", "cond": {"$eq": ["$$item.version", 2]}}}
    #     aggregate_query = [
    #         {"$match": {"$expr": {"$in": [f"${filter_type}", identifiers]}}},
    #         {
    #             "$project": {
    #                 "_id": 0,
    #                 "name": 1,
    #                 "path": 1,
    #                 "project": 1,
    #                 "version": {"$first": {"$sortArray": {"input": "$versions", "sortBy": {"version": -1}}}},
    #             }
    #         },
    #         {
    #             "$project": {
    #                 "_id": 0,
    #                 "name": 1,
    #                 "path": 1,
    #                 "project": 1,
    #                 "bytes": "$version.bytes",
    #                 "encrypted_checksums": "$version.encrypted_checksums",
    #                 "unencrypted_checksums": "$version.unencrypted_checksums",
    #             }
    #         },
    #     ]
    #     try:
    #         files = await self.db_service.do_aggregate("file", aggregate_query)
    #     except (ConnectionFailure, OperationFailure) as error:
    #         reason = f"Error happened while getting file, err: {error}"
    #         LOG.exception(reason)
    #         raise web.HTTPInternalServerError(reason=reason)
    #     return files

    async def read_submission_files(self, submission_id: str) -> List[Dict]:
        """Get files in a submission.

        The files are identified in a submission by version.

        :param submission_id: Submission ID to get files for
        :returns: List of files specific to a submission
        """
        # TO_DO: add check for ready status
        aggregate_query = [
            {"$match": {"submissionId": 1}},
            {"$unwind": "$files"},
            {"$project": {"_id": 0, "accessionId": "$files.accessionId", "version": "$files.version"}},
        ]
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
        """
        try:
            delete_success = await self.db_service.update_by_key_value(
                "file", "path", file_path, {"flagDeleted": deleted}
            )
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while flagging file as deleted, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not delete_success:
            reason = f"Flagging file with '{file_path}' as deleted failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Flagging file with file_path: %r as Deleted succeeded.", file_path)

    async def add_files_submission(self, files: List[dict], submission_id: str) -> bool:
        """Add files to a submission.

        Doesn't check if files are already present in the submission.

        :param files: list of files according to submission schema
        :param submission_id: Submission ID to add files to
        :returns: True if operation to append was successful
        """
        return await self.db_service.append("submission", submission_id, {"$addToSet": {"files": {"$each": files}}})
