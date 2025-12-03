import uuid

from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.database.postgres.models import RegistrationEntity
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.registration import RegistrationRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction
from tests.unit.database.postgres.helpers import create_object_entity, create_submission_entity

workflow = SubmissionWorkflow.SD


async def test_add_get_registration(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    registration_repository: RegistrationRepository,
) -> None:
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.project_id, submission.submission_id)
        await object_repository.add_object(obj, workflow)

        object_type = f"type_{uuid.uuid4()}"
        title = f"title_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        doi = f"doi_{uuid.uuid4()}"
        metax_id = f"metax_{uuid.uuid4()}"
        datacite_url = f"datacite_{uuid.uuid4()}"
        rems_url = f"rems_url_{uuid.uuid4()}"
        rems_resource_id = f"rems_resource_{uuid.uuid4()}"
        rems_catalogue_id = f"rems_catalogue_{uuid.uuid4()}"

        def assert_registration(entity: RegistrationEntity):
            assert entity is not None
            assert entity.submission_id == submission.submission_id
            assert entity.object_id == obj.object_id
            assert entity.object_type == object_type
            assert entity.title == title
            assert entity.description == description
            assert entity.doi == doi
            assert entity.metax_id == metax_id
            assert entity.datacite_url == datacite_url
            assert entity.rems_url == rems_url
            assert entity.rems_resource_id == rems_resource_id
            assert entity.rems_catalogue_id == rems_catalogue_id

        registration = RegistrationEntity(
            submission_id=submission.submission_id,
            object_id=obj.object_id,
            object_type=object_type,
            title=title,
            description=description,
            doi=doi,
            metax_id=metax_id,
            datacite_url=datacite_url,
            rems_url=rems_url,
            rems_resource_id=rems_resource_id,
            rems_catalogue_id=rems_catalogue_id,
        )

        await registration_repository.add_registration(registration)

        assert_registration(await registration_repository.get_registration(registration.submission_id))
