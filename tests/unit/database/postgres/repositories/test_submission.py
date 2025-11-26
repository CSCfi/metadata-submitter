import datetime
import uuid

import ulid

from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.database.postgres.models import SubmissionEntity
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction

from ..helpers import create_submission_entity


async def test_add_get_delete_submission(
    session_factory: SessionFactory, submission_repository: SubmissionRepository
) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"

        async def _add_submission() -> tuple[SubmissionEntity, str]:
            _submission = create_submission_entity(
                name=name,
                project_id=project_id,
                bucket="test",
                workflow=SubmissionWorkflow.SD,
            )

            _submission_id = await submission_repository.add_submission(_submission)
            assert isinstance(ulid.parse(_submission_id), ulid.ULID)
            return _submission, _submission_id

        submission, submission_id = await _add_submission()

        def assert_submission(entity: SubmissionEntity):
            assert entity is not None
            assert entity.name == name
            assert entity.project_id == project_id
            assert entity.bucket == "test"
            assert entity.workflow == SubmissionWorkflow.SD
            assert entity.document == submission.document

            assert entity.submission_id == submission_id
            assert entity.created is not None
            assert abs(entity.modified - entity.created) < datetime.timedelta(seconds=1)
            assert not entity.is_published
            assert not entity.is_ingested

        # Select the submission by ID
        assert_submission(await submission_repository.get_submission_by_id(submission_id))

        # Select the submission by name
        assert_submission(await submission_repository.get_submission_by_name(project_id, name))

        # Select the submission by ID, acc or name
        assert_submission(await submission_repository.get_submission_by_id_or_name(project_id, submission_id))
        assert_submission(await submission_repository.get_submission_by_id_or_name(project_id, name))

        # Delete by id
        assert await submission_repository.delete_submission_by_id(submission_id)
        assert (await submission_repository.get_submission_by_id(submission_id)) is None
        assert (await submission_repository.get_submission_by_name(project_id, name)) is None

        # Delete by name
        submission, submission_id = await _add_submission()
        assert await submission_repository.delete_submission_by_name(project_id, name)
        assert (await submission_repository.get_submission_by_id(submission_id)) is None

        # Delete by id, name
        submission, submission_id = await _add_submission()
        assert await submission_repository.delete_submission_by_id_or_name(project_id, submission_id)
        assert (await submission_repository.get_submission_by_id(submission_id)) is None
        submission, submission_id = await _add_submission()
        assert await submission_repository.delete_submission_by_id_or_name(project_id, name)
        assert (await submission_repository.get_submission_by_id(submission_id)) is None


async def test_submitted_ingested_date(
    session_factory: SessionFactory, submission_repository: SubmissionRepository
) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"

        submission = create_submission_entity(
            name=name,
            project_id=project_id,
            bucket="test",
            workflow=SubmissionWorkflow.SD,
        )

        submission_id = await submission_repository.add_submission(submission)

        assert (await submission_repository.get_submission_by_id(submission_id)).is_published is False
        assert (await submission_repository.get_submission_by_id(submission_id)).is_ingested is False
        assert (await submission_repository.get_submission_by_id(submission_id)).published is None
        assert (await submission_repository.get_submission_by_id(submission_id)).ingested is None

        submission.is_published = True
        submission.is_ingested = True
        await session.flush()

        assert (await submission_repository.get_submission_by_id(submission_id)).is_published is True
        assert (await submission_repository.get_submission_by_id(submission_id)).is_ingested is True
        assert (await submission_repository.get_submission_by_id(submission_id)).published is not None
        assert (await submission_repository.get_submission_by_id(submission_id)).ingested is not None


async def test_get_submissions(session_factory: SessionFactory, submission_repository: SubmissionRepository) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        now = datetime.datetime.now(datetime.timezone.utc)

        first_submission_name = f"name_{uuid.uuid4()}"
        first_project_id = f"project_{uuid.uuid4()}"

        first_submission = create_submission_entity(
            name=first_submission_name,
            project_id=first_project_id,
            bucket="test",
            workflow=SubmissionWorkflow.SD,
            created=now - datetime.timedelta(days=1),
            modified=now - datetime.timedelta(days=1),
            is_published=True,
            is_ingested=True,
        )

        second_submission_name = f"name_{uuid.uuid4()}"
        second_and_third_project_id = f"project_{uuid.uuid4()}"

        second_submission = create_submission_entity(
            name=second_submission_name,
            project_id=second_and_third_project_id,
            bucket="test",
            workflow=SubmissionWorkflow.SD,
            created=now - datetime.timedelta(days=2),
            modified=now - datetime.timedelta(days=2),
            is_published=False,
            is_ingested=False,
        )

        third_submission_name = f"name_{uuid.uuid4()}"

        third_submission = create_submission_entity(
            name=third_submission_name,
            project_id=second_and_third_project_id,
            bucket="test",
            workflow=SubmissionWorkflow.SD,
            created=now - datetime.timedelta(days=3),
            modified=now - datetime.timedelta(days=3),
            is_published=False,
            is_ingested=True,
        )

        first_submission_id = await submission_repository.add_submission(first_submission)
        second_submission_id = await submission_repository.add_submission(second_submission)
        third_submission_id = await submission_repository.add_submission(third_submission)

        assert (await submission_repository.get_submission_by_id(first_submission_id)) is not None
        assert (await submission_repository.get_submission_by_id(second_submission_id)) is not None
        assert (await submission_repository.get_submission_by_id(third_submission_id)) is not None

        # Test project id.

        results, total = await submission_repository.get_submissions(
            project_id=first_project_id,
        )
        assert len(results) == 1
        assert total == 1
        assert results[0].name == first_submission_name

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
        )
        assert len(results) == 2
        assert total == 2
        assert second_submission_name in (results[0].name, results[1].name)

        # Test project id and is_published.

        results, total = await submission_repository.get_submissions(project_id=first_project_id, is_published=False)
        assert len(results) == 0
        assert total == 0

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id, is_published=False
        )
        assert len(results) == 2
        assert total == 2
        assert second_submission_name in (results[0].name, results[1].name)

        # Test project id and is_ingested.

        results, total = await submission_repository.get_submissions(project_id=first_project_id, is_ingested=False)
        assert len(results) == 0
        assert total == 0

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id, is_ingested=False
        )
        assert len(results) == 1
        assert total == 1
        assert second_submission_name in results[0].name

        # Test project id and created.

        results, total = await submission_repository.get_submissions(
            project_id=first_project_id,
            created_start=now - datetime.timedelta(days=1),
            created_end=now - datetime.timedelta(days=1),
        )

        assert len(results) == 1
        assert total == 1
        assert results[0].name == first_submission_name

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            created_start=now - datetime.timedelta(days=2),
            created_end=now - datetime.timedelta(days=2),
        )
        assert len(results) == 1
        assert total == 1
        assert second_submission_name in results[0].name

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            created_start=now - datetime.timedelta(days=3),
            created_end=now - datetime.timedelta(days=2),
        )
        assert len(results) == 2
        assert total == 2
        assert second_submission_name in (results[0].name, results[1].name)
        assert third_submission_name in (results[0].name, results[1].name)

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            created_start=now - datetime.timedelta(days=3),
        )
        assert len(results) == 2
        assert total == 2
        assert second_submission_name in (results[0].name, results[1].name)
        assert third_submission_name in (results[0].name, results[1].name)

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            created_end=now - datetime.timedelta(days=3),
        )
        assert len(results) == 1
        assert total == 1
        assert third_submission_name in results[0].name

        # Test project id and modified.

        results, total = await submission_repository.get_submissions(
            project_id=first_project_id,
            modified_start=now - datetime.timedelta(days=1),
            modified_end=now - datetime.timedelta(days=1),
        )

        assert len(results) == 1
        assert total == 1
        assert results[0].name == first_submission_name

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            modified_start=now - datetime.timedelta(days=2),
            modified_end=now - datetime.timedelta(days=2),
        )
        assert len(results) == 1
        assert total == 1
        assert second_submission_name in results[0].name

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            modified_start=now - datetime.timedelta(days=3),
            modified_end=now - datetime.timedelta(days=2),
        )
        assert len(results) == 2
        assert total == 2
        assert second_submission_name in (results[0].name, results[1].name)
        assert third_submission_name in (results[0].name, results[1].name)

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            modified_start=now - datetime.timedelta(days=3),
        )
        assert len(results) == 2
        assert total == 2
        assert second_submission_name in (results[0].name, results[1].name)
        assert third_submission_name in (results[0].name, results[1].name)

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            modified_end=now - datetime.timedelta(days=3),
        )
        assert len(results) == 1
        assert total == 1
        assert third_submission_name in results[0].name

        # Test pagination.

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            page=1,
            page_size=1,
        )
        assert len(results) == 1
        assert total == 2
        assert second_submission_name in results[0].name

        results, total = await submission_repository.get_submissions(
            project_id=second_and_third_project_id,
            page=2,
            page_size=1,
        )
        assert len(results) == 1
        assert total == 2
        assert third_submission_name in results[0].name
