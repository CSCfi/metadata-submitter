"""Test FileService."""

from collections.abc import AsyncGenerator

import pytest

from metadata_backend.database.postgres.services.file import FileService, UnknownFileException
from metadata_backend.database.postgres.models import IngestStatus
from metadata_backend.database.postgres.repository import transaction, SessionFactory
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from tests.unit.database.postgres.helpers import create_submission_entity, create_object_entity, create_file


@pytest.fixture()
async def submission_repository(session_factory: SessionFactory) -> AsyncGenerator[SubmissionRepository, None]:
    repository = SubmissionRepository(session_factory)
    yield repository


@pytest.fixture()
async def object_repository(session_factory: SessionFactory) -> AsyncGenerator[ObjectRepository, None]:
    repository = ObjectRepository(session_factory)
    yield repository


@pytest.fixture()
async def file_repository(session_factory: SessionFactory) -> AsyncGenerator[FileRepository, None]:
    repository = FileRepository(session_factory)
    yield repository


@pytest.fixture()
async def service(file_repository: FileRepository) -> AsyncGenerator[FileService, None]:
    service = FileService(file_repository)
    yield service


async def test_is_file(session_factory: SessionFactory,
                       submission_repository: SubmissionRepository,
                       object_repository: ObjectRepository,
                       file_repository: FileRepository,
                       service: FileService):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj)

        file = create_file(submission.submission_id, obj.object_id)
        file_id = await service.add_file(file)
        assert await service.is_file(file_id)
        assert await service.is_file(file_id, submission_id=submission.submission_id)
        assert not await service.is_file(file_id, submission_id="other")


async def test_get_file(session_factory: SessionFactory,
                        submission_repository: SubmissionRepository,
                        object_repository: ObjectRepository,
                        file_repository: FileRepository,
                        service: FileService):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        file = create_object_entity(submission.submission_id)
        await object_repository.add_object(file)

        # Create file.
        file = create_file(submission.submission_id, file.object_id)

        file.file_id = await service.add_file(file)
        result = await service.get_file_by_id(file.file_id)

        # Assert file.
        assert sorted(file.json_dump().items()) == sorted(result.json_dump().items())


async def test_get_files(session_factory: SessionFactory,
                         submission_repository: SubmissionRepository,
                         object_repository: ObjectRepository,
                         file_repository: FileRepository,
                         service: FileService):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        file = create_object_entity(submission.submission_id)
        await object_repository.add_object(file)

        # Create files.
        files = [create_file(submission.submission_id, file.object_id) for _ in range(3)]
        for file in files:
            file.file_id = await service.add_file(file)

        # Get files.
        results = [file async for file in service.get_files(submission.submission_id)]

        # Assert files.
        assert sorted(f.json_dump().items() for f in files) == sorted(r.json_dump().items() for r in results)

        # Get files using initial ingest status.
        results = [file async for file in
                   service.get_files(submission.submission_id, ingest_statuses=[IngestStatus.ADDED])]

        # Assert files.
        assert sorted(f.json_dump().items() for f in files) == sorted(r.json_dump().items() for r in results)

        # Get files using other ingest status.
        results = [file async for file in
                   service.get_files(submission.submission_id, ingest_statuses=[IngestStatus.FAILED])]

        # Assert files.
        assert len(results) == 0


async def test_count_files(session_factory: SessionFactory,
                           submission_repository: SubmissionRepository,
                           object_repository: ObjectRepository,
                           file_repository: FileRepository,
                           service: FileService):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        file = create_object_entity(submission.submission_id)
        await object_repository.add_object(file)

        # Create files.
        files = [create_file(submission.submission_id, file.object_id) for _ in range(3)]
        for file in files:
            file.file_id = await service.add_file(file)

        # Assert file count.
        assert await service.count_files(submission.submission_id) == 3
        assert await service.count_files(submission.submission_id, ingest_statuses=[IngestStatus.ADDED]) == 3
        assert await service.count_files(submission.submission_id, ingest_statuses=[IngestStatus.FAILED]) == 0


async def test_count_bytes(session_factory: SessionFactory,
                           submission_repository: SubmissionRepository,
                           object_repository: ObjectRepository,
                           file_repository: FileRepository,
                           service: FileService):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        file = create_object_entity(submission.submission_id)
        await object_repository.add_object(file)

        file_bytes = 1024

        # Create files.
        files = [create_file(submission.submission_id, file.object_id, bytes=file_bytes) for _ in range(3)]
        for file in files:
            file.file_id = await service.add_file(file)

        # Assert file bytes.
        assert await service.count_bytes(submission.submission_id) == 3 * file_bytes


async def test_update_ingest_status(session_factory: SessionFactory,
                                    submission_repository: SubmissionRepository,
                                    object_repository: ObjectRepository,
                                    file_repository: FileRepository,
                                    service: FileService):
    async with (transaction(session_factory, requires_new=True, rollback_new=True) as session):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj)

        file = create_file(submission.submission_id, obj.object_id)
        file_id = await service.add_file(file)

        assert (await file_repository.get_file_by_id(file_id)).ingest_status == IngestStatus.ADDED
        await service.update_ingest_status(file_id, ingest_status=IngestStatus.FAILED)
        assert (await file_repository.get_file_by_id(file_id)).ingest_status == IngestStatus.FAILED

        with pytest.raises(UnknownFileException):
            await service.update_ingest_status("unknown", ingest_status=IngestStatus.FAILED)


async def test_delete_file_by_id(session_factory: SessionFactory,
                                 submission_repository: SubmissionRepository,
                                 object_repository: ObjectRepository,
                                 file_repository: FileRepository,
                                 service: FileService):
    async with (transaction(session_factory, requires_new=True, rollback_new=True) as session):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj)

        file = create_file(submission.submission_id, obj.object_id)
        file_id = await service.add_file(file)

        assert await service.is_file(file_id)
        await service.delete_file_by_id(file_id)
        assert not await service.is_file(file_id)

        with pytest.raises(UnknownFileException):
            await service.delete_file_by_id(file_id)


async def test_delete_file_by_path(session_factory: SessionFactory,
                                   submission_repository: SubmissionRepository,
                                   object_repository: ObjectRepository,
                                   file_repository: FileRepository,
                                   service: FileService):
    async with (transaction(session_factory, requires_new=True, rollback_new=True) as session):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj)

        file = create_file(submission.submission_id, obj.object_id)
        file_id = await service.add_file(file)

        assert await service.is_file(file_id)
        await service.delete_file_by_path(submission.submission_id, file.path)
        assert not await service.is_file(file_id)

        with pytest.raises(UnknownFileException):
            await service.delete_file_by_path(submission.submission_id, file.path)
