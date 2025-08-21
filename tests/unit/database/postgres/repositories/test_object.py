import datetime
import uuid

import ulid

from metadata_backend.api.models import SubmissionWorkflow
from metadata_backend.database.postgres.models import ObjectEntity
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction

from ..helpers import create_submission_entity


async def test_add_get_delete_object(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, object_repository: ObjectRepository
) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        now = datetime.datetime.now(datetime.timezone.utc)

        submission_name = f"name_{uuid.uuid4()}"
        project_id = f"project_{uuid.uuid4()}"

        submission = create_submission_entity(
            name=submission_name,
            project_id=project_id,
            folder="test",
            workflow=SubmissionWorkflow.SDS,
            created=now - datetime.timedelta(days=1),
            modified=now - datetime.timedelta(days=1),
            is_published=True,
            is_ingested=True,
        )
        submission_id = await submission_repository.add_submission(submission)

        name = f"name_{uuid.uuid4()}"
        schema = "test"
        title = "test"
        document = {"test": "test"}
        xml_document = "<test/>"

        async def _add_object() -> tuple[ObjectEntity, str]:
            _obj = ObjectEntity(
                name=name,
                schema=schema,
                submission_id=submission_id,
                title=title,
                document=document,
                xml_document=xml_document,
            )
            _object_id = await object_repository.add_object(_obj)
            assert isinstance(ulid.parse(_object_id), ulid.ULID)
            return _obj, _object_id

        obj, object_id = await _add_object()

        def assert_object(entity: ObjectEntity) -> None:
            assert entity is not None
            assert entity.name == name
            assert entity.schema == schema
            assert entity.submission_id == submission_id
            assert entity.title == title
            assert entity.document == document
            assert entity.xml_document == xml_document
            assert not entity.is_draft

        # Select the object by ID
        assert_object(await object_repository.get_object_by_id(object_id))

        # Select the object by name
        assert_object(await object_repository.get_object_by_name(submission_id, name))

        # Select the object by ID, acc or name
        assert_object(await object_repository.get_object_by_id_or_name(submission_id, object_id))
        assert_object(await object_repository.get_object_by_id_or_name(submission_id, name))

        # Delete by id
        assert await object_repository.delete_object_by_id(object_id)
        assert (await object_repository.get_object_by_id(object_id)) is None
        assert (await object_repository.get_object_by_name(submission_id, name)) is None
        assert (await object_repository.get_object_by_id_or_name(submission_id, object_id)) is None
        assert (await object_repository.get_object_by_id_or_name(submission_id, name)) is None

        # Delete by name
        obj, object_id = await _add_object()
        assert_object(await object_repository.get_object_by_id(object_id))
        assert await object_repository.delete_object_by_name(submission_id, name)
        assert (await object_repository.get_object_by_id(object_id)) is None

        # Delete by id, name
        obj, object_id = await _add_object()
        assert_object(await object_repository.get_object_by_id(object_id))
        assert await object_repository.delete_object_by_id_or_name(submission_id, object_id)
        assert (await object_repository.get_object_by_id(object_id)) is None
        obj, object_id = await _add_object()
        assert_object(await object_repository.get_object_by_id(object_id))
        assert await object_repository.delete_object_by_id_or_name(submission_id, name)
        assert (await object_repository.get_object_by_id(object_id)) is None


async def test_get_and_count_objects(
    session_factory: SessionFactory, submission_repository: SubmissionRepository, object_repository: ObjectRepository
) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True) as session:
        now = datetime.datetime.now(datetime.timezone.utc)

        first_submission_name = f"name_{uuid.uuid4()}"
        first_project_id = f"project_{uuid.uuid4()}"

        first_submission = create_submission_entity(
            name=first_submission_name,
            project_id=first_project_id,
            folder="test",
            workflow=SubmissionWorkflow.SDS,
            created=now - datetime.timedelta(days=1),
            modified=now - datetime.timedelta(days=1),
            is_published=True,
            is_ingested=True,
        )

        second_submission_name = f"name_{uuid.uuid4()}"
        second_project_id = f"project_{uuid.uuid4()}"

        second_submission = create_submission_entity(
            name=second_submission_name,
            project_id=second_project_id,
            folder="test",
            workflow=SubmissionWorkflow.SDS,
            created=now - datetime.timedelta(days=1),
            modified=now - datetime.timedelta(days=1),
            is_published=True,
            is_ingested=True,
        )

        first_submission_id = await submission_repository.add_submission(first_submission)
        second_submission_id = await submission_repository.add_submission(second_submission)

        first_object_name = f"name_{uuid.uuid4()}"
        first_schema = "test1"
        first_document = {"test": "test"}

        first_object = ObjectEntity(
            name=first_object_name,
            schema=first_schema,
            submission_id=first_submission_id,
            document=first_document,
            xml_document="<test/>",
            is_draft=True,
        )

        second_object_name = f"name_{uuid.uuid4()}"
        second_schema = "test2"
        second_document = {"test": "test"}

        second_object = ObjectEntity(
            name=second_object_name,
            schema=second_schema,
            submission_id=first_submission_id,
            document=second_document,
            is_draft=False,
        )

        third_object_name = f"name_{uuid.uuid4()}"
        third_schema = "test1"
        third_document = {"test": "test"}

        third_object = ObjectEntity(
            name=third_object_name,
            schema=third_schema,
            submission_id=second_submission_id,
            document=third_document,
            is_draft=False,
        )

        first_object_id = await object_repository.add_object(first_object)
        second_object_id = await object_repository.add_object(second_object)
        third_object_id = await object_repository.add_object(third_object)

        assert (await object_repository.get_object_by_id(first_object_id)) is not None
        assert (await object_repository.get_object_by_id(second_object_id)) is not None
        assert (await object_repository.get_object_by_id(third_object_id)) is not None

        # Test submission id.

        results = [obj async for obj in object_repository.get_objects(submission_id=first_submission_id)]
        assert len(results) == 2
        assert await object_repository.count_objects(submission_id=first_submission_id) == 2
        assert {results[0].object_id, results[1].object_id} == {first_object_id, second_object_id}

        results = [obj async for obj in object_repository.get_objects(submission_id=second_submission_id)]
        assert len(results) == 1
        assert await object_repository.count_objects(submission_id=second_submission_id) == 1
        assert results[0].object_id == third_object_id

        # Test submission id and object type.

        results = [
            obj async for obj in object_repository.get_objects(submission_id=first_submission_id, schema=first_schema)
        ]
        assert len(results) == 1
        assert await object_repository.count_objects(first_submission_id, first_schema) == 1
        assert results[0].object_id == first_object_id

        results = [
            obj async for obj in object_repository.get_objects(submission_id=first_submission_id, schema=second_schema)
        ]
        assert len(results) == 1
        assert await object_repository.count_objects(first_submission_id, second_schema) == 1
        assert results[0].object_id == second_object_id

        # Test submission id and draft.

        results = [obj async for obj in object_repository.get_objects(submission_id=first_submission_id, is_draft=True)]
        assert len(results) == 1
        assert await object_repository.count_objects(first_submission_id, is_draft=True) == 1
        assert results[0].object_id == first_object_id

        results = [
            obj async for obj in object_repository.get_objects(submission_id=first_submission_id, is_draft=False)
        ]
        assert len(results) == 1
        assert await object_repository.count_objects(first_submission_id, is_draft=False) == 1
        assert results[0].object_id == second_object_id
