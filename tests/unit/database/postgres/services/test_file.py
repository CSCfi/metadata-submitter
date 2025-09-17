"""Test FileService."""

from collections.abc import AsyncGenerator

import pytest

from metadata_backend.api.models import SubmissionWorkflow
from metadata_backend.database.postgres.models import IngestStatus
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction
from metadata_backend.database.postgres.services.file import FileService, UnknownFileException
from tests.unit.database.postgres.helpers import create_file, create_object_entity, create_submission_entity

workflow = SubmissionWorkflow.SDS

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


async def test_is_file(
        session_factory: SessionFactory,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        service: FileService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj, workflow)

        file = create_file(submission.submission_id, obj.object_id)
        file_id = await service.add_file(file, workflow)
        assert await service.is_file(file_id)
        assert await service.is_file(file_id, submission_id=submission.submission_id)
        assert not await service.is_file(file_id, submission_id="other")


async def test_get_file(
        session_factory: SessionFactory,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        service: FileService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        file = create_object_entity(submission.submission_id)
        await object_repository.add_object(file, workflow)

        # Create file.
        file = create_file(submission.submission_id, file.object_id)

        file.file_id = await service.add_file(file, workflow)
        result = await service.get_file_by_id(file.file_id)

        # Assert file.
        assert sorted(file.to_json_dict().items()) == sorted(result.to_json_dict().items())


async def test_get_files(
        session_factory: SessionFactory,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        service: FileService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        file = create_object_entity(submission.submission_id)
        await object_repository.add_object(file, workflow)

        # Create files.
        files = [create_file(submission.submission_id, file.object_id) for _ in range(3)]
        for file in files:
            file.file_id = await service.add_file(file, workflow)

        # Get files.
        results = [file async for file in service.get_files(submission.submission_id)]

        # Assert files.
        assert sorted(f.to_json_dict().items() for f in files) == sorted(r.to_json_dict().items() for r in results)

        # Get files using initial ingest status.
        results = [
            file async for file in service.get_files(submission.submission_id, ingest_statuses=[IngestStatus.ADDED])
        ]

        # Assert files.
        assert sorted(f.to_json_dict().items() for f in files) == sorted(r.to_json_dict().items() for r in results)

        # Get files using other ingest status.
        results = [
            file async for file in service.get_files(submission.submission_id, ingest_statuses=[IngestStatus.FAILED])
        ]

        # Assert files.
        assert len(results) == 0


async def test_count_files(
        session_factory: SessionFactory,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        service: FileService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        file = create_object_entity(submission.submission_id)
        await object_repository.add_object(file, workflow)

        # Create files.
        files = [create_file(submission.submission_id, file.object_id) for _ in range(3)]
        for file in files:
            file.file_id = await service.add_file(file, workflow)

        # Assert file count.
        assert await service.count_files(submission.submission_id) == 3
        assert await service.count_files(submission.submission_id, ingest_statuses=[IngestStatus.ADDED]) == 3
        assert await service.count_files(submission.submission_id, ingest_statuses=[IngestStatus.FAILED]) == 0


async def test_count_bytes(
        session_factory: SessionFactory,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        service: FileService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        file = create_object_entity(submission.submission_id)
        await object_repository.add_object(file, workflow)

        file_bytes = 1024

        # Create files.
        files = [create_file(submission.submission_id, file.object_id, bytes=file_bytes) for _ in range(3)]
        for file in files:
            file.file_id = await service.add_file(file, workflow)

        # Assert file bytes.
        assert await service.count_bytes(submission.submission_id) == 3 * file_bytes


async def test_update_ingest_status(
        session_factory: SessionFactory,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        file_repository: FileRepository,
        service: FileService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj, workflow)

        file = create_file(submission.submission_id, obj.object_id)
        file_id = await service.add_file(file, workflow)

        assert (await file_repository.get_file_by_id(file_id)).ingest_status == IngestStatus.ADDED
        await service.update_ingest_status(file_id, ingest_status=IngestStatus.FAILED)
        assert (await file_repository.get_file_by_id(file_id)).ingest_status == IngestStatus.FAILED

        with pytest.raises(UnknownFileException):
            await service.update_ingest_status("unknown", ingest_status=IngestStatus.FAILED)


async def test_delete_file_by_id(
        session_factory: SessionFactory,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        service: FileService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj, workflow)

        file = create_file(submission.submission_id, obj.object_id)
        file_id = await service.add_file(file, workflow)

        assert await service.is_file(file_id)
        await service.delete_file_by_id(file_id)
        assert not await service.is_file(file_id)

        with pytest.raises(UnknownFileException):
            await service.delete_file_by_id(file_id)


async def test_delete_file_by_path(
        session_factory: SessionFactory,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        service: FileService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj, workflow)

        file = create_file(submission.submission_id, obj.object_id)
        file_id = await service.add_file(file, workflow)

        assert await service.is_file(file_id)
        await service.delete_file_by_path(submission.submission_id, file.path)
        assert not await service.is_file(file_id)

        with pytest.raises(UnknownFileException):
            await service.delete_file_by_path(submission.submission_id, file.path)
