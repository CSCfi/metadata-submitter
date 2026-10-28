"""Service for registrations."""

from typing import Callable

from ....api.exceptions import SystemException
from ....api.models.models import Registration
from ..models import RegistrationEntity
from ..repositories.registration import RegistrationRepository
from ..repository import committed_session


class RegistrationService:
    """Service for registrations.

    Registrations are added and updated in their own committed transactions,
    so that the external identifiers are kept if publishing fails, and a
    retry reuses them rather than registering new ones.
    """

    def __init__(self, repository: RegistrationRepository) -> None:
        """Initialize the service."""
        self.repository = repository

    @staticmethod
    def convert_from_entity(entity: RegistrationEntity) -> Registration | None:
        """
        Convert registration entity to a registration model.

        :param entity: the registration entity
        :returns: the registration model
        """

        if entity is None:
            return None

        return Registration(
            submissionId=entity.submission_id,
            objectId=entity.object_id,
            objectType=entity.object_type,
            title=entity.title,
            description=entity.description,
            doi=entity.doi,
            metaxId=entity.metax_id,
            dataciteUrl=entity.datacite_url,
            remsUrl=entity.rems_url,
            remsResourceId=entity.rems_resource_id,
            remsCatalogueId=entity.rems_catalogue_id,
        )

    async def get_registration(self, submission_id: str) -> Registration | None:
        """Get the registration using submission id.

        :param submission_id: the submission id
        :returns: the registration
        """
        return self.convert_from_entity(await self.repository.get_registration(submission_id))

    async def add_registration(self, registration: Registration) -> str:
        """
        Add a new registration to the database in its own committed transaction.

        Args:
            :param registration: The registration.

        Returns:
            The registration id used as the primary key value.
        """
        async with committed_session():
            return await self.repository.add_registration(
                RegistrationEntity(
                    submission_id=registration.submissionId,
                    object_id=registration.objectId,
                    object_type=registration.objectType,
                    title=registration.title,
                    description=registration.description,
                    doi=registration.doi,
                    metax_id=registration.metaxId,
                    datacite_url=registration.dataciteUrl,
                    rems_url=registration.remsUrl,
                    rems_resource_id=registration.remsResourceId,
                    rems_catalogue_id=registration.remsCatalogueId,
                )
            )

    async def _update_registration(
        self, submission_id: str, update_callback: Callable[[RegistrationEntity], None]
    ) -> str:
        """Update the registration in its own committed transaction.

        :param submission_id: the submission id
        :param update_callback: updates the registration entity
        :returns: the submission id
        """
        async with committed_session():
            if await self.repository.update_registration(submission_id, update_callback) is None:
                raise SystemException("Missing registration.")
            return submission_id

    async def update_title_and_description(self, submission_id: str, title: str, description: str) -> str:
        """Update title and description in its own committed transaction.

        :param submission_id: the submission id
        :param title: new title
        :param description: new description
        :returns: the submission id
        """

        def update_callback(registration: RegistrationEntity) -> None:
            registration.title = title
            registration.description = description

        return await self._update_registration(submission_id, update_callback)

    async def update_metax_id(self, submission_id: str, metax_id: str) -> str:
        """Update metax id in its own committed transaction.

        :param submission_id: the submission id
        :param metax_id: new metax id
        :returns: the submission id
        """

        def update_callback(registration: RegistrationEntity) -> None:
            registration.metax_id = metax_id

        return await self._update_registration(submission_id, update_callback)

    async def update_datacite_url(self, submission_id: str, datacite_url: str) -> str:
        """Update datacite url in its own committed transaction.

        :param submission_id: the submission id
        :param datacite_url: new datacite url
        :returns: the submission id
        """

        def update_callback(registration: RegistrationEntity) -> None:
            registration.datacite_url = datacite_url

        return await self._update_registration(submission_id, update_callback)

    async def update_rems_url(self, submission_id: str, rems_url: str) -> str:
        """Update rems url in its own committed transaction.

        :param submission_id: the submission id
        :param rems_url: new rems url
        :returns: the submission id
        """

        def update_callback(registration: RegistrationEntity) -> None:
            registration.rems_url = rems_url

        return await self._update_registration(submission_id, update_callback)

    async def update_rems_resource_id(self, submission_id: str, rems_resource_id: str) -> str:
        """Update rems resource id in its own committed transaction.

        :param submission_id: the submission id
        :param rems_resource_id: new rems resource id
        :returns: the registration id
        """

        def update_callback(registration: RegistrationEntity) -> None:
            registration.rems_resource_id = rems_resource_id

        return await self._update_registration(submission_id, update_callback)

    async def update_rems_catalogue_id(self, submission_id: str, rems_catalogue_id: str) -> str:
        """Update rems catalogue id in its own committed transaction.

        :param submission_id: the submission id
        :param rems_catalogue_id: new rems catalogue id
        :returns: the submission id
        """

        def update_callback(registration: RegistrationEntity) -> None:
            registration.rems_catalogue_id = rems_catalogue_id

        return await self._update_registration(submission_id, update_callback)
