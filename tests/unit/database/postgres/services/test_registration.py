"""Test RegistrationService."""

import uuid

from metadata_backend.api.models import Registration, SubmissionWorkflow
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.repository import SessionFactory, transaction
from metadata_backend.database.postgres.services.registration import RegistrationService

from ..helpers import create_object_entity, create_submission_entity

workflow = SubmissionWorkflow.SDS


async def test_add_and_get_registration(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    registration_service: RegistrationService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj, workflow)

        # Object

        object_type = f"type_{uuid.uuid4()}"
        title = f"title_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        doi = f"doi_{uuid.uuid4()}"
        metax_id = f"metax_{uuid.uuid4()}"
        datacite_url = f"datacite_{uuid.uuid4()}"
        rems_url = f"rems_url_{uuid.uuid4()}"
        rems_resource_id = f"rems_resource_{uuid.uuid4()}"
        rems_catalogue_id = f"rems_catalogue_{uuid.uuid4()}"

        registration = Registration(
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

        registration_id = await registration_service.add_registration(registration)

        assert registration == await registration_service.get_registration_by_id(registration_id)
        assert await registration_service.get_registration_by_submission_id(submission.submission_id) is None
        assert registration == await registration_service.get_registration_by_object_id(obj.object_id)
        assert registration == (await registration_service.get_registrations(submission.submission_id))[0]

        # Submission

        object_type = f"schema_{uuid.uuid4()}"
        title = f"title_{uuid.uuid4()}"
        description = f"description_{uuid.uuid4()}"
        doi = f"doi_{uuid.uuid4()}"
        metax_id = f"metax_{uuid.uuid4()}"
        datacite_url = f"datacite_{uuid.uuid4()}"
        rems_url = f"rems_url_{uuid.uuid4()}"
        rems_resource_id = f"rems_resource_{uuid.uuid4()}"
        rems_catalogue_id = f"rems_catalogue_{uuid.uuid4()}"

        registration = Registration(
            submission_id=submission.submission_id,
            title=title,
            description=description,
            doi=doi,
            metax_id=metax_id,
            datacite_url=datacite_url,
            rems_url=rems_url,
            rems_resource_id=rems_resource_id,
            rems_catalogue_id=rems_catalogue_id,
        )

        registration_id = await registration_service.add_registration(registration)

        assert registration == await registration_service.get_registration_by_id(registration_id)
        assert registration == await registration_service.get_registration_by_submission_id(submission.submission_id)


async def test_update_registration(
    session_factory: SessionFactory,
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    registration_service: RegistrationService,
):
    async with transaction(session_factory, requires_new=True, rollback_new=True):
        submission = create_submission_entity()
        await submission_repository.add_submission(submission)
        obj = create_object_entity(submission.submission_id)
        await object_repository.add_object(obj, workflow)

        object_doi = f"doi_{uuid.uuid4()}"
        object_metax_id = f"metax_{uuid.uuid4()}"
        object_datacite_url = f"datacite_{uuid.uuid4()}"
        object_rems_url = f"rems_url_{uuid.uuid4()}"
        object_rems_resource_id = f"rems_resource_{uuid.uuid4()}"
        object_rems_catalogue_id = f"rems_catalogue_{uuid.uuid4()}"

        submission_doi = f"doi_{uuid.uuid4()}"
        submission_metax_id = f"metax_{uuid.uuid4()}"
        submission_datacite_url = f"datacite_{uuid.uuid4()}"
        submission_rems_url = f"rems_url_{uuid.uuid4()}"
        submission_rems_resource_id = f"rems_resource_{uuid.uuid4()}"
        submission_rems_catalogue_id = f"rems_catalogue_{uuid.uuid4()}"

        # Object

        object_registration_id = await registration_service.add_registration(
            Registration(
                submission_id=submission.submission_id,
                object_id=obj.object_id,
                object_type="test",
                title="test",
                description="test",
                doi=object_doi,
            )
        )

        # metax id
        assert object_registration_id == await registration_service.update_metax_id(
            submission.submission_id, object_metax_id, object_id=obj.object_id
        )
        assert (await registration_service.get_registration_by_id(object_registration_id)).metax_id == object_metax_id

        # datacite
        assert object_registration_id == await registration_service.update_datacite_url(
            submission.submission_id, object_datacite_url, object_id=obj.object_id
        )
        assert (
            await registration_service.get_registration_by_id(object_registration_id)
        ).datacite_url == object_datacite_url

        # rems url
        assert object_registration_id == await registration_service.update_rems_url(
            submission.submission_id, object_rems_url, object_id=obj.object_id
        )
        assert (await registration_service.get_registration_by_id(object_registration_id)).rems_url == object_rems_url

        # rems resource id
        assert object_registration_id == await registration_service.update_rems_resource_id(
            submission.submission_id, object_rems_resource_id, object_id=obj.object_id
        )
        assert (
            await registration_service.get_registration_by_id(object_registration_id)
        ).rems_resource_id == object_rems_resource_id

        # rems catalogue id
        assert object_registration_id == await registration_service.update_rems_catalogue_id(
            submission.submission_id, object_rems_catalogue_id, object_id=obj.object_id
        )
        assert (
            await registration_service.get_registration_by_id(object_registration_id)
        ).rems_catalogue_id == object_rems_catalogue_id

        # Submission

        submission_registration_id = await registration_service.add_registration(
            Registration(
                submission_id=submission.submission_id,
                object_type="test",
                title="test",
                description="test",
                doi=submission_doi,
            )
        )

        # metax id
        assert submission_registration_id == await registration_service.update_metax_id(
            submission.submission_id, submission_metax_id
        )
        assert (
            await registration_service.get_registration_by_id(submission_registration_id)
        ).metax_id == submission_metax_id

        # datacite
        assert submission_registration_id == await registration_service.update_datacite_url(
            submission.submission_id, submission_datacite_url
        )
        assert (
            await registration_service.get_registration_by_id(submission_registration_id)
        ).datacite_url == submission_datacite_url

        # rems url
        assert submission_registration_id == await registration_service.update_rems_url(
            submission.submission_id, submission_rems_url
        )
        assert (
            await registration_service.get_registration_by_id(submission_registration_id)
        ).rems_url == submission_rems_url

        # rems resource id
        assert submission_registration_id == await registration_service.update_rems_resource_id(
            submission.submission_id, submission_rems_resource_id
        )
        assert (
            await registration_service.get_registration_by_id(submission_registration_id)
        ).rems_resource_id == submission_rems_resource_id

        # rems catalogue id
        assert submission_registration_id == await registration_service.update_rems_catalogue_id(
            submission.submission_id, submission_rems_catalogue_id
        )
        assert (
            await registration_service.get_registration_by_id(submission_registration_id)
        ).rems_catalogue_id == submission_rems_catalogue_id
