"""Test SubmissionService."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.datacite import Creator, Publisher, Subject
from metadata_backend.api.models.submission import Rems, Submission, SubmissionMetadata, SubmissionWorkflow
from metadata_backend.database.postgres.repositories.submission import (
    SUB_FIELD_METADATA,
    SUB_FIELD_REMS,
    SubmissionRepository,
    SubmissionSort,
)
from metadata_backend.database.postgres.repository import SessionFactory, transaction
from metadata_backend.database.postgres.services.submission import (
    PublishedSubmissionUserException,
    SubmissionService,
    UnknownSubmissionUserException,
)
from tests.unit.database.postgres.helpers import create_submission_entity


async def test_add_and_get_submission(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"
        bucket = "test"
        workflow = SubmissionWorkflow.SD
        title = "test"
        description = "test"
        date = datetime.now() - timedelta(days=1)
        rems_organization_id = "1"
        rems_workflow_id = 2
        rems_licence_ids = [3, 4]

        submission = Submission(
            # Should be extracted from the document
            name=name,
            projectId=project_id,
            workflow=workflow.value,
            bucket=bucket,
            rems=Rems(
                organizationId=rems_organization_id,
                workflowId=rems_workflow_id,
                licenses=rems_licence_ids,
            ),
            # Should be removed from the document
            submissionId="test",
            dateCreated=date,
            datePublished=date,
            lastModified=date,
            published=True,
            # Should remain unchanged in the document
            title=title,
            description=description,
        )

        submission_id = await submission_service.add_submission(submission)

        def assert_recent(dt: datetime, window: timedelta = timedelta(minutes=1)) -> None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            now = datetime.now(UTC)
            assert now - dt < window, f"Expected datetime within {window}, got {dt}"

        entity = await submission_repository.get_submission_by_id(submission_id)
        assert entity.name == name
        assert entity.project_id == project_id
        assert entity.workflow == workflow
        assert entity.bucket == bucket
        assert entity.created is not None
        assert entity.created != date
        assert_recent(entity.created)
        assert entity.modified is not None
        assert entity.modified != date
        assert_recent(entity.modified)
        assert entity.published is None
        assert entity.is_published is False
        assert entity.document["rems"] == to_json_dict(
            Rems(
                licenses=rems_licence_ids,
                organizationId=rems_organization_id,
                workflowId=rems_workflow_id,
            )
        )

        assert await submission_service.get_submission_by_id(submission_id) == Submission(
            name=name,
            projectId=project_id,
            workflow=workflow.value,
            bucket=bucket,
            submissionId=submission_id,
            dateCreated=entity.created,
            lastModified=entity.modified,
            datePublished=entity.published,
            published=False,
            title=title,
            description=description,
            rems=Rems(
                organizationId=rems_organization_id,
                workflowId=rems_workflow_id,
                licenses=rems_licence_ids,
            ),
        )

        # Test that submission name must be unique within a project.
        with pytest.raises(UserException, match=f"Submission with name {name} already exists in project {project_id}"):
            await submission_service.add_submission(submission)


async def test_get_submissions(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        project_id = f"project_{uuid.uuid4()}"

        search = "word"
        search_name_1 = f"{search} {uuid.uuid4()}"
        search_name_2 = f"{uuid.uuid4()} {search}"
        names = [search_name_1, search_name_2, f"{uuid.uuid4()}"]

        entities = []
        for name in names:
            entities.append(create_submission_entity(project_id=project_id, name=name))
        for submission in entities:
            await submission_repository.add_submission(submission)

        now = datetime.now(ZoneInfo("UTC"))
        created_start = now - timedelta(days=1)
        created_end = now + timedelta(days=1)
        modified_start = now - timedelta(days=1)
        modified_end = now + timedelta(days=1)
        sort = SubmissionSort.CREATED_DESC
        page = 1
        page_size = 10

        with patch.object(
            submission_service.repository,
            "get_submissions",
            new_callable=lambda: AsyncMock(wraps=submission_service.repository.get_submissions),
        ) as spy:
            submissions, cnt = await submission_service.get_submissions(
                project_id,
                is_published=False,
                is_ingested=False,
                created_start=created_start,
                created_end=created_end,
                modified_start=modified_start,
                modified_end=modified_end,
                sort=sort,
                page=page,
                page_size=page_size,
            )

            spy.assert_awaited_once_with(
                project_id,
                name=None,
                is_published=False,
                is_ingested=False,
                created_start=created_start,
                created_end=created_end,
                modified_start=modified_start,
                modified_end=modified_end,
                sort=sort,
                page=page,
                page_size=page_size,
            )

            assert cnt == 3
            assert {s.submission_id for s in entities} == {s.submissionId for s in submissions.submissions}

            # Search by name.
            submissions, cnt = await submission_service.get_submissions(
                project_id,
                name=search,
            )
            assert cnt == 2
            assert len(submissions.submissions) == 2
            assert search_name_1 in {s.name for s in submissions.submissions}
            assert search_name_2 in {s.name for s in submissions.submissions}


async def test_is_and_check_submission(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        assert not await submission_service.is_submission_by_id(submission.submission_id)
        with pytest.raises(UnknownSubmissionUserException):
            await submission_service.check_submission_by_id(submission.submission_id)
        await submission_repository.add_submission(submission)
        assert await submission_service.is_submission_by_id(submission.submission_id)
        assert await submission_service.check_submission_by_id(submission.submission_id) is None


async def test_is_and_check_not_published(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity(is_published=False)
        await submission_repository.add_submission(submission)
        assert not await submission_service.is_published(submission.submission_id)
        await submission_service.check_not_published(submission.submission_id)

        submission.is_published = True
        await session.flush()
        assert await submission_service.is_published(submission.submission_id)
        with pytest.raises(PublishedSubmissionUserException):
            await submission_service.check_not_published(submission.submission_id)


async def test_get_project_id(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        assert await submission_service.get_project_id(submission.submission_id) == submission.project_id


async def test_get_workflow(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        assert await submission_service.get_workflow(submission.submission_id) == submission.workflow


async def test_get_bucket(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        assert await submission_service.get_bucket(submission.submission_id) == submission.bucket


async def test_update_submission(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        submission.bucket = None
        await submission_repository.add_submission(submission)

        # bucket
        bucket = f"bucket{uuid.uuid4()}"
        await submission_service.update_bucket(submission.submission_id, bucket)
        updated_submission = await submission_repository.get_submission_by_id(submission.submission_id)
        assert updated_submission.bucket == bucket
        with pytest.raises(UserException):
            await submission_service.update_bucket(submission.submission_id, f"bucket{uuid.uuid4()}")

        # metadata
        metadata = SubmissionMetadata(
            creators=[Creator(nameType="Personal", name="Name", givenName="Alice", familyName="Smith")],
            subjects=[Subject(subject="999 - Other")],
            keywords="test",
            publisher=Publisher(name="University Health Care System"),
        )

        assert (
            SUB_FIELD_METADATA
            not in (await submission_repository.get_submission_by_id(submission.submission_id)).document
        )
        await submission_service.update_metadata(submission.submission_id, metadata)
        assert (await submission_service.get_metadata(submission.submission_id)) == metadata
        actual_dict = (await submission_repository.get_submission_by_id(submission.submission_id)).document
        assert SubmissionMetadata.model_validate(actual_dict[SUB_FIELD_METADATA]) == metadata

        # rems
        rems = Rems(workflowId=1, organizationId="2", licenses=[3, 4])
        await submission_service.update_rems(submission.submission_id, rems)
        assert (await submission_service.get_rems_document(submission.submission_id)) == rems
        actual_dict = (await submission_repository.get_submission_by_id(submission.submission_id)).document
        assert Rems.model_validate(actual_dict[SUB_FIELD_REMS]) == rems

        # update description and title
        updated_submission = await submission_service.get_submission_by_id(submission.submission_id)
        updated_submission.description = f"description_{uuid.uuid4()}"
        updated_submission.title = f"title_{uuid.uuid4()}"
        await submission_service.update_submission(
            submission.submission_id, {"description": updated_submission.description, "title": updated_submission.title}
        )
        expected_dict = updated_submission.model_dump(exclude={"lastModified"})
        actual_submission = await submission_service.get_submission_by_id(submission.submission_id)
        actual_dict = actual_submission.model_dump(exclude={"lastModified"})
        assert expected_dict == actual_dict

        # Some fields can't be changed
        async def assert_update_exception(_field: str) -> None:
            with pytest.raises(UserException):
                await submission_service.update_submission(submission.submission_id, {_field: f"{uuid.uuid4()}"})

        await assert_update_exception("name")
        await assert_update_exception("projectId")
        await assert_update_exception("bucket")

        with pytest.raises(UserException):
            await submission_service.update_submission(submission.submission_id, {"workflow": SubmissionWorkflow.BP})

        # published
        assert not (await submission_repository.get_submission_by_id(submission.submission_id)).is_published
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).published is None
        await submission_service.publish(submission.submission_id)
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).is_published
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).published is not None


async def test_delete_submission(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        assert await submission_service.is_submission_by_id(submission.submission_id)

        await submission_service.delete_submission(submission.submission_id)
        assert not await submission_service.is_submission_by_id(submission.submission_id)
