"""Test RegistrationService."""

import uuid

from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from metadata_backend.database.postgres.services.registration import RegistrationService

from ..helpers import create_object_entity, create_submission_entity

workflow = SubmissionWorkflow.SD


async def test_add_and_get_registration(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    registration_service: RegistrationService,
):
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

    registration = Registration(
        submissionId=submission.submission_id,
        objectId=obj.object_id,
        objectType=object_type,
        title=title,
        description=description,
        doi=doi,
        metaxId=metax_id,
        dataciteUrl=datacite_url,
        remsUrl=rems_url,
        remsResourceId=rems_resource_id,
        remsCatalogueId=rems_catalogue_id,
    )

    await registration_service.add_registration(registration)
    assert registration == await registration_service.get_registration(submission.submission_id)


async def test_update_registration(
    submission_repository: SubmissionRepository,
    object_repository: ObjectRepository,
    registration_service: RegistrationService,
):
    submission = create_submission_entity()
    await submission_repository.add_submission(submission)
    obj = create_object_entity(submission.project_id, submission.submission_id)
    await object_repository.add_object(obj, workflow)

    doi = f"doi_{uuid.uuid4()}"
    metax_id = f"metax_{uuid.uuid4()}"
    datacite_url = f"datacite_{uuid.uuid4()}"
    rems_url = f"rems_url_{uuid.uuid4()}"
    rems_resource_id = f"rems_resource_{uuid.uuid4()}"
    rems_catalogue_id = f"rems_catalogue_{uuid.uuid4()}"

    registration = Registration(
        submissionId=submission.submission_id,
        objectId=obj.object_id,
        objectType="test",
        title="test",
        description="test",
        doi=doi,
    )
    await registration_service.add_registration(registration)

    # metax id
    await registration_service.update_metax_id(submission.submission_id, metax_id)
    assert (await registration_service.get_registration(submission.submission_id)).metaxId == metax_id

    # datacite
    await registration_service.update_datacite_url(submission.submission_id, datacite_url)
    assert (await registration_service.get_registration(submission.submission_id)).dataciteUrl == datacite_url

    # rems url
    await registration_service.update_rems_url(submission.submission_id, rems_url)
    assert (await registration_service.get_registration(submission.submission_id)).remsUrl == rems_url

    # rems resource id
    await registration_service.update_rems_resource_id(submission.submission_id, rems_resource_id)
    assert (await registration_service.get_registration(submission.submission_id)).remsResourceId == rems_resource_id

    # rems catalogue id
    await registration_service.update_rems_catalogue_id(submission.submission_id, rems_catalogue_id)
    assert (await registration_service.get_registration(submission.submission_id)).remsCatalogueId == rems_catalogue_id
