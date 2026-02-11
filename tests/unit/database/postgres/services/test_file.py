"""Test FileService."""

from collections.abc import AsyncGenerator

import pytest

from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.database.postgres.models import IngestStatus
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.services.file import FileService, UnknownFileException
from tests.unit.database.postgres.helpers import create_file, create_object_entity, create_submission_entity

workflow = SubmissionWorkflow.SD


@pytest.fixture()
async def submission_repository() -> AsyncGenerator[SubmissionRepository, None]:
    repository = SubmissionRepository()
    yield repository


@pytest.fixture()
async def object_repository() -> AsyncGenerator[ObjectRepository, None]:
    repository = ObjectRepository()
    yield repository


@pytest.fixture()
async def file_repository() -> AsyncGenerator[FileRepository, None]:
    repository = FileRepository()
    yield repository


@pytest.fixture()
async def service(file_repository: FileRepository) -> AsyncGenerator[FileService, None]:
    service = FileService(file_repository)
    yield service


async def test_is_file(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    service: FileService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    obj = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(obj, workflow)

    file = create_file(submission.submission_id, obj.object_id)
    file_id = await service.add_file(file, workflow)
    assert await service.is_file(file_id)
    assert await service.is_file(file_id, submission_id=submission.submission_id)
    assert not await service.is_file(file_id, submission_id="other")


async def test_get_file(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    service: FileService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    file = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(file, workflow)

    # Create file.
    file = create_file(submission.submission_id, file.object_id)

    file.fileId = await service.add_file(file, workflow)
    result = await service.get_file_by_id(file.fileId)

    # Assert file.
    assert sorted(to_json_dict(file).items()) == sorted(to_json_dict(result).items())


async def test_get_files(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    service: FileService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    file = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(file, workflow)

    # Create files.
    files = [create_file(submission.submission_id, file.object_id) for _ in range(3)]
    for file in files:
        file.fileId = await service.add_file(file, workflow)

    # Get files.
    results = [file async for file in service.get_files(submission_id=submission.submission_id)]

    # Assert files.
    assert sorted(to_json_dict(f).items() for f in files) == sorted(to_json_dict(r).items() for r in results)

    # Get files using initial ingest status.
    results = [
        file
        async for file in service.get_files(
            submission_id=submission.submission_id, ingest_statuses=[IngestStatus.SUBMITTED]
        )
    ]

    # Assert files.
    assert sorted(to_json_dict(f).items() for f in files) == sorted(to_json_dict(r).items() for r in results)

    # Get files using other ingest status.
    results = [
        file
        async for file in service.get_files(
            submission_id=submission.submission_id, ingest_statuses=[IngestStatus.ERROR]
        )
    ]

    # Assert files.
    assert len(results) == 0


async def test_count_files(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    service: FileService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    file = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(file, workflow)

    # Create files.
    files = [create_file(submission.submission_id, file.object_id) for _ in range(3)]
    for file in files:
        file.fileId = await service.add_file(file, workflow)

    # Assert file count.
    assert await service.count_files(submission.submission_id) == 3
    assert await service.count_files(submission.submission_id, ingest_statuses=[IngestStatus.SUBMITTED]) == 3
    assert await service.count_files(submission.submission_id, ingest_statuses=[IngestStatus.ERROR]) == 0


async def test_count_bytes(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    service: FileService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    file = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(file, workflow)

    file_bytes = 1024

    # Create files.
    files = [create_file(submission.submission_id, file.object_id, bytes=file_bytes) for _ in range(3)]
    for file in files:
        file.fileId = await service.add_file(file, workflow)

    # Assert file bytes.
    assert await service.count_bytes(submission.submission_id) == 3 * file_bytes


async def test_update_ingest_status(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    file_repository: FileRepository,
    service: FileService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    obj = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(obj, workflow)

    file = create_file(submission.submission_id, obj.object_id)
    file_id = await service.add_file(file, workflow)

    assert (await file_repository.get_file_by_id(file_id)).ingest_status == IngestStatus.SUBMITTED
    await service.update_ingest_status(file_id, ingest_status=IngestStatus.ERROR)
    assert (await file_repository.get_file_by_id(file_id)).ingest_status == IngestStatus.ERROR

    with pytest.raises(UnknownFileException):
        await service.update_ingest_status("unknown", ingest_status=IngestStatus.ERROR)


async def test_delete_file_by_id(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    service: FileService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    obj = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(obj, workflow)

    file = create_file(submission.submission_id, obj.object_id)
    file_id = await service.add_file(file, workflow)

    assert await service.is_file(file_id)
    await service.delete_file_by_id(file_id)
    assert not await service.is_file(file_id)

    with pytest.raises(UnknownFileException):
        await service.delete_file_by_id(file_id)


async def test_delete_file_by_path(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    service: FileService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    obj = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(obj, workflow)

    file = create_file(submission.submission_id, obj.object_id)
    file_id = await service.add_file(file, workflow)

    assert await service.is_file(file_id)
    await service.delete_file_by_path(submission.submission_id, file.path)
    assert not await service.is_file(file_id)

    with pytest.raises(UnknownFileException):
        await service.delete_file_by_path(submission.submission_id, file.path)
