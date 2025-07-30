"""Service for submission files."""

from typing import AsyncIterator, Sequence

from ....api.exceptions import NotFoundUserException
from ....api.models import File
from ..models import FileEntity, IngestStatus
from ..repositories.file import FileRepository


class UnknownFileException(NotFoundUserException):
    """Raised when a file cannot be found."""

    def __init__(self, file_id: str) -> None:
        """
        Initialize the exception.

        :param file_id: The file id or file path.
        """

        message = f"File '{file_id}' not found."
        super().__init__(message)


class FileService:
    """Service for submission files."""

    def __init__(self, repository: FileRepository) -> None:
        """Initialize the service."""
        self.__repository = repository

    @staticmethod
    def convert_to_entity(file: File) -> FileEntity:
        """
        Convert submission file to file entity.

        :param file: the submission file
        "return the file entity
        """

        return FileEntity(
            file_id=file.file_id,
            object_id=file.object_id,
            submission_id=file.submission_id,
            path=file.path,
            bytes=file.bytes,
            unencrypted_checksum=file.unencrypted_checksum,
            unencrypted_checksum_type=file.unencrypted_checksum_type,
            encrypted_checksum=file.encrypted_checksum,
            encrypted_checksum_type=file.encrypted_checksum_type,
        )

    @staticmethod
    def convert_from_entity(entity: FileEntity) -> File:
        """
        Convert file entity to submission file.

        :param entity: the file entity
        "return the submission file
        """

        return File(
            file_id=entity.file_id,
            object_id=entity.object_id,
            submission_id=entity.submission_id,
            path=entity.path,
            bytes=entity.bytes,
            unencrypted_checksum=entity.unencrypted_checksum,
            unencrypted_checksum_type=entity.unencrypted_checksum_type,
            encrypted_checksum=entity.encrypted_checksum,
            encrypted_checksum_type=entity.encrypted_checksum_type,
        )

    async def add_file(self, file: File) -> str:
        """Add a new submission file.

        :param file: the submission file
        :returns: the automatically assigned file id
        """
        return await self.__repository.add_file(self.convert_to_entity(file))

    async def is_file(self, file_id: str, *, submission_id: str | None = None) -> bool:
        """Check if the file exists.

        Optionally checks if the file is associated with the given submission id.

        :param file_id: the file id
        :param submission_id: the submission id
        :returns: True if the file exists. If the submission id is given then returns True
                  only if the file is associated with the submission.
        """
        obj = await self.__repository.get_file_by_id(file_id)
        if obj is None:
            return False

        if submission_id is not None:
            return obj.submission_id == submission_id

        return True

    async def is_file_by_path(self, submission_id: str, path: str) -> bool:
        """
        Check if the file exists.

          Args:
              submission_id: The submission id.
              path: The file path.

        Returns:
            True if the file exists.
        """
        file = await self.__repository.get_file_by_path(submission_id, path)
        return file is not None

    async def get_file_by_id(self, file_id: str) -> File:
        """
        Get submission file with the given file id.

        Args:
            file_id: the file id.

        Returns:
            The submission file.
        """
        file = await self.__repository.get_file_by_id(file_id)
        if file is None:
            raise UnknownFileException(file_id)

        return self.convert_from_entity(file)

    async def get_file_by_path(self, submission_id: str, path: str) -> File:
        """
        Get submission file with the given file path.

          Args:
              submission_id: The submission id.
              path: The file path.

        Returns:
            The submission file.
        """
        file = await self.__repository.get_file_by_path(submission_id, path)
        if file is None:
            raise UnknownFileException(path)

        return self.convert_from_entity(file)

    async def get_files(
        self, submission_id: str, *, ingest_statuses: Sequence[IngestStatus] | None = None
    ) -> AsyncIterator[File]:
        """
        Get files associated with the submission.

        Args:
            submission_id: the submission id.
            ingest_statuses: filter by ingest statuses.

        Returns:
            Asynchronous interator of files.
        """
        async for obj in self.__repository.get_files(submission_id, ingest_statuses=ingest_statuses):
            yield self.convert_from_entity(obj)

    async def count_files(self, submission_id: str, *, ingest_statuses: Sequence[IngestStatus] | None = None) -> int:
        """Count files associated with the given submission.

        :param submission_id: The submission id.
        :param ingest_statuses: filter by ingest statuses.
        :return: A count of files in the submission.
        """
        return await self.__repository.count_files(submission_id, ingest_statuses=ingest_statuses)

    async def count_bytes(self, submission_id: str) -> int:
        """Count files bytes associated with the given submission.

        :param submission_id: The submission id.
        :return: Bytes of files in the submission.
        """
        return await self.__repository.count_bytes(submission_id)

    async def update_ingest_status(self, file_id: str, ingest_status: IngestStatus) -> None:
        """Update file ingest status.

        :param file_id: the file id
        :param ingest_status: new file ingest status
        """

        def update_callback(file: FileEntity) -> None:
            file.ingest_status = ingest_status

        if await self.__repository.update_file(file_id, update_callback) is None:
            raise UnknownFileException(file_id)

    async def delete_file_by_id(self, file_id: str) -> None:
        """Delete file with the given file id.

        :param file_id: the file id
        """
        if not await self.__repository.delete_file_by_id(file_id):
            raise UnknownFileException(file_id)

    async def delete_file_by_path(self, submission_id: str, path: str) -> None:
        """Delete file with the given submission id and path.

        :param submission_id: the submission id
        :param path: the file path
        """
        if not await self.__repository.delete_file_by_path(submission_id, path):
            raise UnknownFileException(path)
