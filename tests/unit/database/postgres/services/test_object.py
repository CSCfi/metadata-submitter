"""Test ObjectService."""

import uuid

from metadata_backend.api.models import Object
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction
from metadata_backend.database.postgres.services.object import ObjectService
from tests.unit.database.postgres.helpers import create_object_entity, create_submission_entity


async def test_add_object(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        schema: str = "test"
        document = {"test": "test"}
        xml_document = "<test/>"
        object_id = f"id_{uuid.uuid4()}"
        name = f"name_{uuid.uuid4()}"
        title = "test"
        description = "test"

        assert (
            await object_service.add_object(
                submission.submission_id,
                schema,
                document=document,
                xml_document=xml_document,
                object_id=object_id,
                name=name,
                title=title,
                description=description,
            )
            == object_id
        )

        assert await object_service.is_object(object_id)
        result = await object_repository.get_object_by_id(object_id)
        assert result.schema == schema
        assert result.object_id == object_id
        assert result.name == name
        assert result.title == title
        assert result.document == document
        assert result.xml_document == xml_document
        assert result.title == title


async def test_is_object(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        obj = create_object_entity(submission.submission_id)
        assert not await object_service.is_object(obj.object_id)
        await object_repository.add_object(obj)
        assert await object_service.is_object(obj.object_id)
        assert await object_service.is_object(obj.object_id, submission_id=submission.submission_id)
        assert not await object_service.is_object(obj.object_id, submission_id=submission.submission_id + "other")


async def test_get_document(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        obj = create_object_entity(submission.submission_id)
        object_id = await object_repository.add_object(obj)

        assert {**obj.document, "accessionId": object_id} == await object_service.get_document(object_id)
        assert obj.xml_document == await object_service.get_xml_document(object_id)


async def test_get_objects(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        schema_type = "test"

        # Create objects.
        object_entities = [create_object_entity(submission.submission_id, schema=schema_type) for _ in range(3)]

        objects = []
        for obj in object_entities:
            object_id = await object_repository.add_object(obj)
            objects.append(Object(object_id=object_id, submission_id=submission.submission_id, schema_type=schema_type))

        # Assert objects.
        result = await object_service.get_objects(submission.submission_id, schema_type)
        assert sorted([o.json_dump() for o in objects], key=lambda x: x["objectId"]) == sorted(
            [r.json_dump() for r in result], key=lambda x: x["objectId"]
        )


async def test_get_documents(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        schema = "test"

        # Create objects.
        objects = [create_object_entity(submission.submission_id, schema=schema) for _ in range(3)]
        for obj in objects:
            await object_repository.add_object(obj)

        # Get documents.
        documents = [document async for document in object_service.get_documents(submission.submission_id, schema)]
        xml_documents = [
            document async for document in object_service.get_xml_documents(submission.submission_id, schema)
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
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)

        schema = "test"

        objects = [create_object_entity(submission.submission_id, schema=schema) for _ in range(3)]
        for obj in objects:
            await object_repository.add_object(obj)

        assert await object_service.count_objects(submission.submission_id, schema) == 3
        assert await object_service.count_objects(submission.submission_id, "other") == 0


async def test_update_object(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj)

        # document
        document = {"test": str(uuid.uuid4())}
        await object_service.update_document(obj.object_id, document)
        assert (await object_repository.get_object_by_id(obj.object_id)).document == document

        # xml document
        xml_document = f'<test test="{str(uuid.uuid4())}"/>'
        await object_service.update_xml_document(obj.object_id, xml_document)
        assert (await object_repository.get_object_by_id(obj.object_id)).xml_document == xml_document


async def test_delete_object(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    object_service: ObjectService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj)

        assert await object_service.is_object(obj.object_id)
        await object_service.delete_object_by_id(obj.object_id)
        assert not await object_service.is_object(obj.object_id)
