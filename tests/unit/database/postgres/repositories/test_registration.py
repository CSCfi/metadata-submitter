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

        object_object_type = f"type_{uuid.uuid4()}"
        object_title = f"title_{uuid.uuid4()}"
        object_description = f"description_{uuid.uuid4()}"
        object_doi = f"doi_{uuid.uuid4()}"
        object_metax_id = f"metax_{uuid.uuid4()}"
        object_datacite_url = f"datacite_{uuid.uuid4()}"
        object_rems_url = f"rems_url_{uuid.uuid4()}"
        object_rems_resource_id = f"rems_resource_{uuid.uuid4()}"
        object_rems_catalogue_id = f"rems_catalogue_{uuid.uuid4()}"

        submission_object_type = f"type_{uuid.uuid4()}"
        submission_title = f"title_{uuid.uuid4()}"
        submission_description = f"description_{uuid.uuid4()}"
        submission_doi = f"doi_{uuid.uuid4()}"
        submission_metax_id = f"metax_{uuid.uuid4()}"
        submission_datacite_url = f"datacite_{uuid.uuid4()}"
        submission_rems_url = f"rems_url_{uuid.uuid4()}"
        submission_rems_resource_id = f"rems_resource_{uuid.uuid4()}"
        submission_rems_catalogue_id = f"rems_catalogue_{uuid.uuid4()}"

        def assert_object_registration(entity: RegistrationEntity):
            assert entity is not None
            assert entity.submission_id == submission.submission_id
            assert entity.object_id == obj.object_id
            assert entity.object_type == object_object_type
            assert entity.title == object_title
            assert entity.description == object_description
            assert entity.doi == object_doi
            assert entity.metax_id == object_metax_id
            assert entity.datacite_url == object_datacite_url
            assert entity.rems_url == object_rems_url
            assert entity.rems_resource_id == object_rems_resource_id
            assert entity.rems_catalogue_id == object_rems_catalogue_id

        def assert_submission_registration(entity: RegistrationEntity):
            assert entity is not None
            assert entity.submission_id == submission.submission_id
            assert entity.object_id is None
            assert entity.doi == submission_doi
            assert entity.object_type == submission_object_type
            assert entity.title == submission_title
            assert entity.description == submission_description
            assert entity.metax_id == submission_metax_id
            assert entity.datacite_url == submission_datacite_url
            assert entity.rems_url == submission_rems_url
            assert entity.rems_resource_id == submission_rems_resource_id
            assert entity.rems_catalogue_id == submission_rems_catalogue_id

        object_registration = RegistrationEntity(
            submission_id=submission.submission_id,
            object_id=obj.object_id,
            object_type=object_object_type,
            title=object_title,
            description=object_description,
            doi=object_doi,
            metax_id=object_metax_id,
            datacite_url=object_datacite_url,
            rems_url=object_rems_url,
            rems_resource_id=object_rems_resource_id,
            rems_catalogue_id=object_rems_catalogue_id,
        )

        object_registration_id = await registration_repository.add_registration(object_registration)

        # Object

        # Select the object registration by registration id
        assert_object_registration(await registration_repository.get_registration_by_id(object_registration_id))

        # Select the submission registration by submission id
        assert (await registration_repository.get_registration_by_submission_id(submission.submission_id)) is None

        # Select the object registration by object id
        assert_object_registration(await registration_repository.get_registration_by_object_id(obj.object_id))

        # Select the object registration by getting all registrations for the submission
        assert_object_registration((await registration_repository.get_registrations(submission.submission_id))[0])

        # Submission

        submission_registration = RegistrationEntity(
            submission_id=submission.submission_id,
            object_type=submission_object_type,
            title=submission_title,
            description=submission_description,
            doi=submission_doi,
            metax_id=submission_metax_id,
            datacite_url=submission_datacite_url,
            rems_url=submission_rems_url,
            rems_resource_id=submission_rems_resource_id,
            rems_catalogue_id=submission_rems_catalogue_id,
        )

        submission_registration_id = await registration_repository.add_registration(submission_registration)

        # Select the submission registration by registration id
        assert_submission_registration(await registration_repository.get_registration_by_id(submission_registration_id))

        # Select the submission registration by submission id
        assert_submission_registration(
            await registration_repository.get_registration_by_submission_id(submission.submission_id)
        )

        # Select the object registration by registration id
        assert_object_registration(await registration_repository.get_registration_by_id(object_registration_id))

        # Select the object registration by object id
        assert_object_registration(await registration_repository.get_registration_by_object_id(obj.object_id))
