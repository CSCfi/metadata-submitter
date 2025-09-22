import datetime
import uuid

import ulid

from metadata_backend.api.models import ChecksumType, SubmissionWorkflow
from metadata_backend.database.postgres.models import FileEntity, IngestStatus
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction
from tests.unit.database.postgres.helpers import create_object_entity, create_submission_entity

workflow = SubmissionWorkflow.SDS


async def add_submission(submission_repository: SubmissionRepository) -> str:
    submission = create_submission_entity()
    now = datetime.datetime.now(datetime.timezone.utc)
    submission.created = now - datetime.timedelta(days=1)
    submission.modified = now - datetime.timedelta(days=1)
    return await submission_repository.add_submission(submission)


async def add_object(submission_id: str, object_repository: ObjectRepository) -> str:
    obj = create_object_entity(submission_id)
    return await object_repository.add_object(obj, workflow)


async def test_add_get_delete_file(
    session_factory: SessionFactory,
    file_repository: FileRepository,
    object_repository: ObjectRepository,
    submission_repository: SubmissionRepository,
) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission_id = await add_submission(submission_repository)
        object_id = await add_object(submission_id, object_repository)
        unencrypted_checksum = f"unencrypted_{uuid.uuid4()}"
        encrypted_checksum = f"encrypted_{uuid.uuid4()}"
        unencrypted_checksum_type = ChecksumType.SHA256
        encrypted_checksum_type = ChecksumType.MD5
        path = f"path_{uuid.uuid4()}"

        def create_file() -> FileEntity:
            return FileEntity(
                submission_id=submission_id,
                object_id=object_id,
                bytes=1024,
                unencrypted_checksum=unencrypted_checksum,
                encrypted_checksum=encrypted_checksum,
                unencrypted_checksum_type=unencrypted_checksum_type,
                encrypted_checksum_type=encrypted_checksum_type,
                path=path,
            )

        # Create file entity.
        file_entity = create_file()

        # Add file entity.
        file_id = await file_repository.add_file(file_entity, workflow)
        assert isinstance(ulid.parse(file_id), ulid.ULID)

        # Assert file entity.
        def assert_file(entity: FileEntity) -> None:
            assert entity is not None
            assert entity.file_id == file_id
            assert entity.submission_id == submission_id
            assert entity.object_id == object_id
            assert entity.bytes == 1024
            assert entity.unencrypted_checksum == unencrypted_checksum
            assert entity.encrypted_checksum == encrypted_checksum
            assert entity.unencrypted_checksum_type == unencrypted_checksum_type
            assert entity.encrypted_checksum_type == encrypted_checksum_type
            assert entity.path == path
            assert entity.ingest_status == IngestStatus.ADDED
            assert entity.ingest_error is None

        # Test delete by file id.
        assert_file(await file_repository.get_file_by_id(file_id))
        assert_file(await file_repository.get_file_by_path(submission_id, path))

        assert await file_repository.delete_file_by_id(file_id)
        assert (await file_repository.get_file_by_id(file_id)) is None
        assert (await file_repository.get_file_by_path(submission_id, path)) is None

        # Create file entity.
        file_entity = create_file()
        file_id = await file_repository.add_file(file_entity, workflow)

        # Test delete by submission id and file path.
        assert_file(await file_repository.get_file_by_id(file_id))
        assert_file(await file_repository.get_file_by_path(submission_id, path))

        assert await file_repository.delete_file_by_path(submission_id, path)
        assert (await file_repository.get_file_by_id(file_id)) is None
        assert (await file_repository.get_file_by_path(submission_id, path)) is None


async def test_get_and_count_files_and_bytes(
    session_factory: SessionFactory,
    file_repository: FileRepository,
    object_repository: ObjectRepository,
    submission_repository: SubmissionRepository,
) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission_id = await add_submission(submission_repository)
        object_id = await add_object(submission_id, object_repository)
        unencrypted_checksum = f"unencrypted_{uuid.uuid4()}"
        encrypted_checksum = f"encrypted_{uuid.uuid4()}"
        unencrypted_checksum_type = ChecksumType.SHA256
        encrypted_checksum_type = ChecksumType.MD5

        path_1 = f"path_{uuid.uuid4()}"

        bytes_1 = bytes_2 = 1024

        file_entity_1 = FileEntity(
            submission_id=submission_id,
            object_id=object_id,
            bytes=bytes_1,
            unencrypted_checksum=unencrypted_checksum,
            encrypted_checksum=encrypted_checksum,
            unencrypted_checksum_type=unencrypted_checksum_type,
            encrypted_checksum_type=encrypted_checksum_type,
            path=path_1,
            ingest_status=IngestStatus.ADDED,
        )

        path_2 = f"path_{uuid.uuid4()}"

        file_entity_2 = FileEntity(
            submission_id=submission_id,
            object_id=object_id,
            bytes=bytes_2,
            unencrypted_checksum=unencrypted_checksum,
            encrypted_checksum=encrypted_checksum,
            unencrypted_checksum_type=unencrypted_checksum_type,
            encrypted_checksum_type=encrypted_checksum_type,
            path=path_2,
            ingest_status=IngestStatus.FAILED,
        )

        file_id_1 = await file_repository.add_file(file_entity_1, workflow)
        file_id_2 = await file_repository.add_file(file_entity_2, workflow)

        # Files

        files = [file async for file in file_repository.get_files(submission_id, ingest_statuses=[IngestStatus.ADDED])]
        assert len(files) == 1
        assert await file_repository.count_files(submission_id, ingest_statuses=[IngestStatus.ADDED]) == 1

        assert files[0].file_id == file_id_1

        files = [
            file
            async for file in file_repository.get_files(
                submission_id, ingest_statuses=[IngestStatus.ADDED, IngestStatus.FAILED]
            )
        ]
        assert len(files) == 2
        assert (
            await file_repository.count_files(submission_id, ingest_statuses=[IngestStatus.ADDED, IngestStatus.FAILED])
            == 2
        )
        assert {file_id_1, file_id_2} == {files[0].file_id, files[1].file_id}

        # Bytes

        assert await file_repository.count_bytes(submission_id) == bytes_1 + bytes_2


async def test_update_ingest_status(
    session_factory: SessionFactory,
    file_repository: FileRepository,
    object_repository: ObjectRepository,
    submission_repository: SubmissionRepository,
) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission_id = await add_submission(submission_repository)
        object_id = await add_object(submission_id, object_repository)
        unencrypted_checksum = f"unencrypted_{uuid.uuid4()}"
        encrypted_checksum = f"encrypted_{uuid.uuid4()}"
        unencrypted_checksum_type = ChecksumType.SHA256
        encrypted_checksum_type = ChecksumType.MD5

        path = f"path_{uuid.uuid4()}"

        file_entity = FileEntity(
            submission_id=submission_id,
            object_id=object_id,
            bytes=1024,
            unencrypted_checksum=unencrypted_checksum,
            encrypted_checksum=encrypted_checksum,
            unencrypted_checksum_type=unencrypted_checksum_type,
            encrypted_checksum_type=encrypted_checksum_type,
            path=path,
            ingest_status=IngestStatus.ADDED,
        )

        file_id = await file_repository.add_file(file_entity, workflow)

        assert (await file_repository.get_file_by_id(file_id)).ingest_status == IngestStatus.ADDED

        def update_callback(file: FileEntity) -> None:
            file.ingest_status = IngestStatus.COMPLETED

        await file_repository.update_file(file_id, update_callback)

        assert (await file_repository.get_file_by_id(file_id)).ingest_status == IngestStatus.COMPLETED
