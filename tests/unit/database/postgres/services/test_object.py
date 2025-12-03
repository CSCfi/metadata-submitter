"""Test ObjectService."""

import uuid

import pytest

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.models.models import Object
from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.database.postgres.models import ObjectEntity
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction
from metadata_backend.database.postgres.services.object import ObjectService
from tests.unit.database.postgres.helpers import create_object_entity, create_submission_entity

workflow = SubmissionWorkflow.SD


async def test_add_update_delete_object(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        submission_id = submission.submission_id

        object_type: str = "test"
        document = {"test": "test"}
        xml_document = "<test/>"
        project_id = f"project_{uuid.uuid4()}"
        object_id = f"id_{uuid.uuid4()}"
        object_id2 = f"id_{uuid.uuid4()}"
        name = f"name_{uuid.uuid4()}"
        name2 = f"name_{uuid.uuid4()}"
        title = "test"
        description = "test"

        def _assert_object(objects: list[Object]):
            assert len(objects) == 1
            obj = objects[0]
            assert obj.objectType == object_type
            assert obj.objectId == object_id
            assert obj.name == name
            assert obj.title == title

        def _assert_entity(entity: ObjectEntity):
            assert entity.object_type == object_type
            assert entity.object_id == object_id
            assert entity.name == name
            assert entity.title == title
            assert entity.document == document
            assert entity.xml_document == xml_document

        # Add

        async def _add_object(name_: str, object_id_: str) -> str:
            return await object_service.add_object(
                project_id,
                submission_id,
                name_,
                object_type,
                workflow,
                document=document,
                xml_document=xml_document,
                object_id=object_id_,
                title=title,
                description=description,
            )

        assert await _add_object(name, object_id) == object_id
        # Add second object to test that it is not returned by get_objects.
        assert await _add_object(name2, object_id2) == object_id2

        assert await object_service.is_object(object_id)

        _assert_entity(await object_repository.get_object_by_id(object_id))
        _assert_object(await object_service.get_objects(submission_id, object_type, object_id=object_id))
        _assert_object(await object_service.get_objects(submission_id, object_type, name=name))
        _assert_object(await object_service.get_objects(submission_id, object_type, object_id=object_id, name=name))
        _assert_object(await object_service.get_objects(submission_id, object_id=object_id))
        _assert_object(await object_service.get_objects(submission_id, name=name))

        # Test that object name must be unique for an object type within a project.
        with pytest.raises(
            UserException,
            match=f"Metadata object of type {object_type} with name {name} already exists in project {project_id}",
        ):
            await object_service.add_object(
                project_id,
                submission.submission_id,
                name,
                object_type,
                workflow,
                document=document,
                xml_document=xml_document,
                object_id=object_id,
                title=title,
                description=description,
            )

        # Update

        document = {"update": "update"}
        xml_document = "<update/>"
        title = "update"
        description = "update"

        await object_service.update_object(
            object_id,
            document=document,
            xml_document=xml_document,
            title=title,
            description=description,
        )

        assert await object_service.is_object(object_id)

        _assert_entity(await object_repository.get_object_by_id(object_id))
        _assert_object(await object_service.get_objects(submission_id, object_type, object_id=object_id))
        _assert_object(await object_service.get_objects(submission_id, object_type, name=name))
        _assert_object(await object_service.get_objects(submission_id, object_type, object_id=object_id, name=name))
        _assert_object(await object_service.get_objects(submission_id, object_id=object_id))
        _assert_object(await object_service.get_objects(submission_id, name=name))

        # Delete

        assert await object_service.is_object(object_id)
        await object_service.delete_object_by_id(object_id)
        assert not await object_service.is_object(object_id)


async def test_is_object(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        obj = create_object_entity(submission.project_id, submission.submission_id)
        assert not await object_service.is_object(obj.object_id)
        await object_repository.add_object(obj, workflow)
        assert await object_service.is_object(obj.object_id)
        assert await object_service.is_object(obj.object_id, submission_id=submission.submission_id)
        assert not await object_service.is_object(obj.object_id, submission_id=submission.submission_id + "other")


async def test_get_document(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        obj = create_object_entity(submission.project_id, submission.submission_id)
        object_id = await object_repository.add_object(obj, workflow)

        assert {**obj.document, "accessionId": object_id} == await object_service.get_document(object_id)
        assert obj.xml_document == await object_service.get_xml_document(object_id)


async def test_get_objects(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        object_type = "test"

        # Create objects.
        object_entities = [
            create_object_entity(submission.project_id, submission.submission_id, object_type=object_type)
            for _ in range(3)
        ]

        objects = []
        for obj in object_entities:
            object_id = await object_repository.add_object(obj, workflow)
            objects.append(
                Object(
                    name=obj.name,
                    objectId=object_id,
                    objectType=object_type,
                    submissionId=submission.submission_id,
                    title=obj.title,
                    description=obj.description,
                )
            )

        # Get objects.
        results = await object_service.get_objects(submission.submission_id, object_type)

        # Compare objects.
        objects_sorted = sorted(objects, key=lambda o: o.objectId)
        results_sorted = sorted(results, key=lambda o: o.objectId)
        for obj, res in zip(objects_sorted, results_sorted, strict=False):
            assert obj.name == res.name
            assert obj.objectId == res.objectId
            assert obj.objectType == res.objectType
            assert obj.submissionId == res.submissionId
            assert obj.title == res.title
            assert obj.description == res.description
            assert res.created is not None
            assert res.modified is not None


async def test_get_documents(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        object_type = "test"

        # Create objects.
        objects = [
            create_object_entity(submission.project_id, submission.submission_id, object_type=object_type)
            for _ in range(3)
        ]
        for obj in objects:
            await object_repository.add_object(obj, workflow)

        # Get documents.
        documents = [document async for document in object_service.get_documents(submission.submission_id, object_type)]
        xml_documents = [
            document async for document in object_service.get_xml_documents(submission.submission_id, object_type)
        ]

        # Assert documents.
        assert {doc["test"] for doc in documents} == {obj.document["test"] for obj in objects}
        assert set(xml_documents) == {"<test/>"}


async def test_count_objects(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        object_type = "test"

        objects = [
            create_object_entity(submission.project_id, submission.submission_id, object_type=object_type)
            for _ in range(3)
        ]
        for obj in objects:
            await object_repository.add_object(obj, workflow)

        assert await object_service.count_objects(submission.submission_id, object_type) == 3
        assert await object_service.count_objects(submission.submission_id, "other") == 0
