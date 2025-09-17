"""Test SubmissionService."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from pydantic_core import to_jsonable_python
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from metadata_backend.api.models import Rems, SubmissionWorkflow
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository, SubmissionSort
from metadata_backend.database.postgres.repository import SessionFactory, transaction
from metadata_backend.database.postgres.services.submission import (
    PublishedSubmissionUserException,
    SubmissionService,
    SubmissionUserException,
    UnknownSubmissionUserException,
)
from tests.unit.database.postgres.helpers import create_submission_entity


async def test_add_and_get_submission(
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"
        folder = "test"
        workflow = SubmissionWorkflow.SDS
        title = "test"
        description = "test"
        rems_organization_id = "1"
        rems_workflow_id = 2
        rems_licence_ids = [3, 4]

        submission = {
            # Should be extracted from the document
            "name": name,
            "projectId": project_id,
            "workflow": workflow.value,
            "linkedFolder": folder,
            "rems": {
                "organizationId": rems_organization_id,
                "workflowId": rems_workflow_id,
                "licenses": rems_licence_ids,
            },
            # Should be removed from the document
            "submissionId": "test",
            "dateCreated": "test",
            "datePublished": "test",
            "lastModified": "test",
            "published": "test",
            # Should remain unchanged in the document
            "title": title,
            "description": description,
        }

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
        assert entity.folder == folder
        assert entity.created is not None
        assert_recent(entity.created)
        assert entity.modified is not None
        assert_recent(entity.modified)
        assert entity.published is None
        assert entity.is_published is False
        assert entity.document["rems"] == {
            "licenses": rems_licence_ids,
            "organizationId": rems_organization_id,
            "workflowId": rems_workflow_id,
        }

        assert await submission_service.get_submission_by_id(submission_id) == {
            "name": to_jsonable_python(name),
            "text_name": to_jsonable_python(" ".join(re.split("[\\W_]", name))),
            "projectId": to_jsonable_python(project_id),
            "workflow": to_jsonable_python(workflow.value),
            "linkedFolder": to_jsonable_python(folder),
            "submissionId": to_jsonable_python(submission_id),
            "dateCreated": to_jsonable_python(entity.created),
            "lastModified": to_jsonable_python(entity.modified),
            "published": to_jsonable_python(False),
            "title": to_jsonable_python(title),
            "description": to_jsonable_python(description),
            "rems": {
                "organizationId": to_jsonable_python(rems_organization_id),
                "workflowId": to_jsonable_python(rems_workflow_id),
                "licenses": to_jsonable_python(rems_licence_ids),
            },
        }


async def test_get_submissions(
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        project_id = f"project_{uuid.uuid4()}"

        search = "word"
        search_name_1 = f"{search} {uuid.uuid4()}"
        search_name_2 = f"{uuid.uuid4()} {search}"
        names = [search_name_1, search_name_2, f"{uuid.uuid4()}"]

        submissions = []
        for name in names:
            submissions.append(create_submission_entity(project_id=project_id, name=name))
        for submission in submissions:
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
            documents, cnt = await submission_service.get_submissions(
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
            assert {s.submission_id for s in submissions} == {d["submissionId"] for d in documents}

            # Search by name.
            documents, cnt = await submission_service.get_submissions(
                project_id,
                name=search,
            )
            assert cnt == 2
            assert len(documents) == 2
            assert search_name_1 in {d["name"] for d in documents}
            assert search_name_2 in {d["name"] for d in documents}


async def test_is_and_check_submission(
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        assert not await submission_service.is_submission_by_id(submission.submission_id)
        with pytest.raises(UnknownSubmissionUserException):
            await submission_service.check_submission_by_id(submission.submission_id)
        await submission_repository.add_submission(submission)
        assert await submission_service.is_submission_by_id(submission.submission_id)
        assert await submission_service.check_submission_by_id(submission.submission_id) is None


async def test_is_and_check_not_published(
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
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
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        assert await submission_service.get_project_id(submission.submission_id) == submission.project_id


async def test_get_workflow(
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        assert await submission_service.get_workflow(submission.submission_id) == submission.workflow


async def test_get_folder(
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        assert await submission_service.get_folder(submission.submission_id) == submission.folder


async def test_update_submission(
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        submission.folder = None
        await submission_repository.add_submission(submission)

        # name
        name = f"name_{uuid.uuid4()}"
        await submission_service.update_name(submission.submission_id, name)
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).name == name

        # description
        description = f"description_{uuid.uuid4()}"
        await submission_service.update_description(submission.submission_id, description)
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).document[
                   "description"
               ] == description

        # folder
        folder = f"folder_{uuid.uuid4()}"
        await submission_service.update_folder(submission.submission_id, folder)
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).folder == folder
        with pytest.raises(SubmissionUserException):
            await submission_service.update_folder(submission.submission_id, folder)

        # doi info
        doi_info = {
            "creators": [{"givenName": "Alice", "familyName": "Smith", "affiliation": []}],
            "subjects": [{"subject": "999 - Other"}],
            "keywords": "test",
        }

        assert "doiInfo" not in (await submission_repository.get_submission_by_id(submission.submission_id)).document
        await submission_service.update_doi_info(submission.submission_id, doi_info)
        assert (await submission_service.get_doi_document(submission.submission_id)) == doi_info

        # rems
        rems = Rems(workflowId=1, organizationId="2", licenses=[3, 4])
        await submission_service.update_rems(submission.submission_id, rems)
        assert (await submission_service.get_rems_document(submission.submission_id)) == rems

        # document: update fields
        document = await submission_service.get_submission_by_id(submission.submission_id)
        document["description"] = f"description_{uuid.uuid4()}"
        document["rems"]["organizationId"] = f"organisation_{uuid.uuid4()}"
        document["doiInfo"]["keywords"] = f"keyword_{uuid.uuid4()}"
        await submission_service.update_submission(submission.submission_id, document)
        expected = {k: v for k, v in document.items() if k != "lastModified"}
        actual = {
            k: v
            for k, v in (await submission_service.get_submission_by_id(submission.submission_id)).items()
            if k != "lastModified"
        }
        assert expected == actual

        # document: immutable fields can't be updated
        document = await submission_service.get_submission_by_id(submission.submission_id)
        document["workflow"] = f"workflow_{uuid.uuid4()}"
        document["projectId"] = f"project_{uuid.uuid4()}"
        document["linkedFolder"] = f"folder_{uuid.uuid4()}"
        await submission_service.update_submission(submission.submission_id, document)
        actual = {
            k: v
            for k, v in (await submission_service.get_submission_by_id(submission.submission_id)).items()
            if k != "lastModified"
        }
        # Expect that nothing has changed.
        assert expected == actual

        # document: preserved fields can't be removed
        document = await submission_service.get_submission_by_id(submission.submission_id)
        document.pop("name", None)
        document.pop("description", None)
        document.pop("projectId", None)
        document.pop("workflow", None)
        document.pop("linkedFolder", None)
        document.pop("rems", None)
        document.pop("doiInfo", None)
        await submission_service.update_submission(submission.submission_id, document)
        actual = {
            k: v
            for k, v in (await submission_service.get_submission_by_id(submission.submission_id)).items()
            if k != "lastModified"
        }
        # Expect that nothing has changed.
        assert expected == actual

        # published
        assert not (await submission_repository.get_submission_by_id(submission.submission_id)).is_published
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).published is None
        await submission_service.publish(submission.submission_id)
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).is_published
        assert (await submission_repository.get_submission_by_id(submission.submission_id)).published is not None


async def test_delete_submission(
        session_factory: SessionFactory, submission_repository: SubmissionRepository,
        submission_service: SubmissionService
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        assert await submission_service.is_submission_by_id(submission.submission_id)

        await submission_service.delete_submission(submission.submission_id)
        assert not await submission_service.is_submission_by_id(submission.submission_id)
