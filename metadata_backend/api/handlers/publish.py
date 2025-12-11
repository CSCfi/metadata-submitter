"""Handle HTTP methods for server."""

import os
import traceback
from datetime import datetime
from typing import Any

from aiohttp import web
from aiohttp.web import Request, Response

from ...conf.deployment import deployment_config
from ...database.postgres.services.file import FileService
from ...database.postgres.services.object import ObjectService
from ...database.postgres.services.registration import RegistrationService
from ...helpers.logger import LOG
from ..auth import get_authorized_user_id
from ..exceptions import SystemException, UserException
from ..json import to_json
from ..models.datacite import DataCiteMetadata
from ..models.models import File, Registration
from ..models.submission import Rems, Submission, SubmissionMetadata, SubmissionWorkflow
from ..resources import (
    get_file_provider_service,
    get_file_service,
    get_object_service,
    get_registration_service,
    get_submission_service,
)
from ..services.datacite import DataciteService
from ..services.publish import PublishConfig, PublishSource, get_publish_config
from .restapi import RESTAPIIntegrationHandler
from .submission import SubmissionAPIHandler


class PublishSubmissionAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for publishing submissions."""

    @staticmethod
    def _make_discovery_url(registration: Registration, publish_config: PublishConfig) -> str:
        """Make a discovery url.

        :param registration: The registration
        :param publish_config: The discovery service configuration
        :returns: The discovery URL
        """
        if publish_config.use_metax_service:
            return PublishSubmissionAPIHandler._make_metax_discovery_url(registration.metaxId)
        if publish_config.use_bp_beacon_service:
            return PublishSubmissionAPIHandler._make_beacon_discovery_url(registration.doi)

        raise SystemException(f"Invalid publish configuration: {to_json(publish_config)}")

    @staticmethod
    def _make_metax_discovery_url(metax_id: str) -> str:
        """Make a discovery url that points to Metax.

        :param metax_id: The Metax ID
        :returns: The discovery URL
        """
        try:
            return f"{os.environ['METAX_DISCOVERY_URL']}{metax_id}"
        except KeyError as ex:
            raise SystemException("Missing required environment variable: METAX_DISCOVERY_URL") from ex

    @staticmethod
    def _make_beacon_discovery_url(doi: str) -> str:
        """Make a discovery url that points to Beacon.

        :param doi: The DOI
        :returns: The discovery URL
        """
        try:
            return f"{os.environ['BEACON_DISCOVERY_URL']}{doi}"
        except KeyError as ex:
            raise SystemException("Missing required environment variable: BEACON_DISCOVERY_URL") from ex

    async def _register_draft_doi(self, publish_config: PublishConfig) -> str:
        """Register a draft DOI through Datacite directly or through CSC PID.

        :param publish_config: publish configuration.
        :returns: The created DOI
        """
        try:
            if publish_config.use_datacite_service:
                return await self.datacite_handler.create_draft_doi()
            if publish_config.use_pid_service:
                return await self.pid_handler.create_draft_doi()
        except Exception as ex:
            raise SystemException("Failed to register DOI using DataCite. Please try again later.") from ex

        raise SystemException(f"Invalid publish configuration: {to_json(publish_config)}")

    async def _register_metax_id(self, submission_id: str, user_id: str, registration: Registration) -> None:
        try:
            metax_id = await self.metax_handler.post_dataset_as_draft(
                user_id, registration.doi, registration.title, registration.description
            )
            registration.metaxId = metax_id

        except Exception as ex:
            raise SystemException(
                f"Failed to register Metax ID in submission '{submission_id}'. Please try again later."
            ) from ex

    async def _publish_datacite(
        self,
        registration: Registration,
        datacite: DataCiteMetadata,
        registration_service: RegistrationService,
        publish_config: PublishConfig,
    ) -> None:
        """Publish to DataCite.

        :param registration: The registration
        :param datacite: The DataCite metadata
        :param registration_service: The registration service
        :param publish_config: The publish configuration
        """
        try:
            discovery_url = self._make_discovery_url(registration, publish_config)

            if not registration.dataciteUrl:
                if publish_config.use_datacite_service:
                    publish_service: DataciteService = self.datacite_handler
                elif publish_config.use_pid_service:
                    publish_service = self.pid_handler
                else:
                    raise SystemException(f"Invalid publish configuration: {to_json(publish_config)}")

                await publish_service.publish(
                    registration,
                    datacite,
                    discovery_url,
                    require_okm_field_of_science=publish_config.require_okm_field_of_science,
                )

                await registration_service.update_datacite_url(registration.submissionId, discovery_url)
        except Exception as ex:
            raise SystemException(
                f"Failed to publish submission in DataCite. Please try again later: {str(ex)}"
            ) from ex

    async def _update_metax(
        self,
        registration: Registration,
        metadata: SubmissionMetadata,
        file_bytes: int,
    ) -> None:
        """Update information in Metax.

        :param registration: The registration
        :param metadata: The submission metadata
        :param file_bytes: The number of file bytes
        """
        try:
            await self.metax_handler.update_dataset_metadata(
                metadata,
                registration.metaxId,
                file_bytes,
            )
        except Exception as ex:
            raise SystemException(
                f"Failed to update submission '{registration.submissionId}' in Metax. Please try again later."
            ) from ex

    async def _publish_rems(
        self,
        rems: Rems,
        registration: Registration,
        publish_config: PublishConfig,
        registration_service: RegistrationService,
    ) -> None:
        """Prepare dictionary with values to be published to REMS. Adds the metax id if available.

        :param rems: The rems data
        :param registration: The registration
        :param publish_config: The publish configuration
        :param registration_service: The registration service.
        """
        try:
            data: dict[str, Any] = {
                "accession_id": registration.objectId,
                "schema": registration.objectType,
                "doi": registration.doi,
                "description": registration.description,
                "localizations": {
                    "en": {
                        "title": registration.title,
                        "infourl": self._make_discovery_url(registration, publish_config),
                    }
                },
            }
            if registration.metaxId:
                data.update({"metaxIdentifier": registration.metaxId})

            if not registration.remsResourceId:
                resource_id = await self.rems_handler.create_resource(
                    doi=registration.doi, organization_id=rems.organizationId, licenses=rems.licenses
                )
                await registration_service.update_rems_resource_id(registration.submissionId, str(resource_id))
                registration.remsResourceId = str(resource_id)
            else:
                resource_id = int(registration.remsResourceId)

            if not registration.remsCatalogueId:
                catalogue_id = await self.rems_handler.create_catalogue_item(
                    resource_id=resource_id,
                    workflow_id=rems.workflowId,
                    organization_id=rems.organizationId,
                    localizations=data["localizations"],
                )
                await registration_service.update_rems_catalogue_id(registration.submissionId, catalogue_id)
                registration.remsCatalogueId = catalogue_id
            else:
                catalogue_id = registration.remsCatalogueId

            if not registration.remsUrl:
                rems_url = self.rems_handler.application_url(catalogue_id)

                # Add rems URL to Metax description.
                if registration.metaxId:
                    new_description = registration.description + f"\n\nSD Apply's Application link: {rems_url}"
                    await self.metax_handler.update_draft_dataset_description(registration.metaxId, new_description)

                await registration_service.update_rems_url(registration.submissionId, rems_url)
                registration.remsUrl = rems_url
        except Exception as ex:
            LOG.error(
                "Failed to publish submission %s to REMS. Original error: %s\nTraceback:\n%s",
                registration.submissionId,
                ex,
                traceback.format_exc(),
            )
            raise SystemException(
                f"Failed to publish submission '{registration.submissionId}' to REMS. Please try again later."
            ) from ex

    async def _publish_metax(
        self,
        registration: Registration,
    ) -> None:
        """Publish to Metax.

        :param registration: The registration
        """
        try:
            await self.metax_handler.publish_dataset(registration.metaxId, registration.doi)
        except Exception as ex:
            raise SystemException(
                f"Failed to publish submission '{registration.submissionId}' to Metax. Please try again later."
            ) from ex

    async def publish_submission(self, req: Request) -> Response:
        """Publish submission by validating it and registering it to public discovery services.

        # The publish process is designed to fail so that successful registrations are preserved
        # while failed registrations can be retried by retrying the publish process as many
        # times as needed. The submitter will only receive a successful response after the
        validation and all registrations have completed successfully.

        :param req: PATCH request
        :returns: JSON response containing submission ID
        """

        user_id = get_authorized_user_id(req)
        submission_id = req.match_info["submissionId"]
        # Hidden parameter to allow submission to be published without files.
        no_files = req.rel_url.query.get("no_files") == "true"
        submission_service = get_submission_service(req)
        object_service = get_object_service(req)
        file_service = get_file_service(req)
        registration_service = get_registration_service(req)
        file_provider_service = get_file_provider_service(req)

        # Check that the user can modify this submission.
        await SubmissionAPIHandler.check_submission_modifiable(req, submission_id)

        workflow = await submission_service.get_workflow(submission_id)

        # Get publish configuration.
        publish_config = get_publish_config(workflow)

        if not no_files:
            # Add all files in linked bucket to the submission.
            bucket = await submission_service.get_bucket(submission_id)
            if workflow == SubmissionWorkflow.SD:
                project_id = await submission_service.get_project_id(submission_id)
                files = await file_provider_service.list_files_in_bucket(bucket, project_id)
                for file in files.root:
                    # Check that we have not added the file already.
                    # For now, accept that file bytes might have changed and some files
                    # might have been removed if a call to this endpoint has failed before.
                    if not await file_service.is_file_by_path(submission_id, file.path):
                        await file_service.add_file(
                            File(
                                submissionId=submission_id,
                                path=file.path,
                                bytes=file.bytes,
                            ),
                            workflow,
                        )

            # Check that the submission has at least one file.
            if await file_service.count_files(submission_id) == 0:
                raise UserException(f"Submission '{submission_id}' does not have any data files.")

        submission = await submission_service.get_submission_by_id(submission_id)

        # Get DataCite metadata.
        datacite = submission.metadata.to_datacite()
        # Set DataCite publication year.
        datacite.publicationYear = datetime.now().year

        # Get REMS metadata.
        rems = submission.rems

        # Check that the submission contains DataCite information.
        if (publish_config.use_pid_service or publish_config.use_datacite_service) and not datacite:
            raise UserException(f"Submission '{submission_id}' does not have required DataCite information.")

        # Check that the submission contains REMS information.
        if publish_config.use_rems_service and not rems:
            raise UserException(f"Submission '{submission_id}' does not have required REMS information.")

        if deployment_config.ALLOW_REGISTRATION:
            await self._register_submission(
                user_id, submission, datacite, rems, object_service, file_service, registration_service, publish_config
            )

        # Update submission status to published.
        await submission_service.publish(submission_id)

        LOG.info("Publishing submission with ID %r was successful.", submission_id)
        return web.Response(body=to_json({"submissionId": submission_id}), status=200, content_type="application/json")

    async def _register_submission(
        self,
        user_id: str,
        submission: Submission,
        datacite: DataCiteMetadata,
        rems: Rems,
        object_service: ObjectService,
        file_service: FileService,
        registration_service: RegistrationService,
        publish_config: PublishConfig,
    ) -> None:
        """
        Register submission with external discovery services.

        :param user_id: The user id
        :param submission: The submission
        :param datacite: The datacite metadata
        :param rems: The rems metadata
        :param object_service: The object service
        :param file_service: The file service
        :param registration_service: The registration service
        :param publish_config: The publish configuration
        """

        submission_id = submission.submissionId

        # Registrations are external identifiers assigned to the submission, e.g. a DOI or Metax ID.
        # We provide title, description and other descriptive information to register external
        # identifiers. Only some of the metadata objects are assigned external identifiers. These
        # are configured in the workflow. Registrations are created only if they have not been created
        # during a previous failed publish attempt.

        registration: Registration = await registration_service.get_registration(submission_id)

        if publish_config.source == PublishSource.SUBMISSION:
            # Register DOI for submission.
            if registration is None:
                doi = await self._register_draft_doi(publish_config)
                registration = self._create_submission_registration(
                    submission_id, submission.title, submission.description, doi
                )
                await registration_service.add_registration(registration)
            elif registration.objectId is not None:
                raise SystemException("Expected a submission registration but found an object registration.")
        elif publish_config.source == PublishSource.OBJECT:
            # Register DOI for metadata object.
            if registration is None:
                async for obj in object_service.repository.get_objects(submission_id):
                    if publish_config.object_type == obj.object_type:
                        if registration is not None:
                            raise SystemException("More than one object registration.")
                        doi = await self._register_draft_doi(publish_config)
                        registration = self._create_object_registration(
                            submission_id, obj.object_id, obj.object_type, obj.title, obj.description, doi
                        )
                        await registration_service.add_registration(registration)
            elif registration.objectId is None:
                raise SystemException("Expected an object registration but found a submission registration.")

        if registration is None:
            raise SystemException("Expected one registration but found none.")

        # Registration has now been created with a DOI.

        # Register Metax IDs. Requires DOI.

        # Register Metax ID for submission.
        if publish_config.use_metax_service:
            if registration.metaxId is None:
                await self._register_metax_id(submission_id, user_id, registration)
                await registration_service.update_metax_id(submission_id, registration.metaxId)

        # Publish to DataCite. Requires DOIs. Modifies the datacite information.
        if publish_config.use_pid_service or publish_config.use_datacite_service:
            await self._publish_datacite(
                registration,
                datacite,
                registration_service,
                publish_config,
            )

        file_bytes = await file_service.count_bytes(submission_id)

        # Update Metax with DOI information and file bytes.
        if publish_config.use_metax_service:
            # Update datacite metadata changed during DataCite publish.
            metadata = submission.metadata
            metadata.update_datacite(datacite)
            await self._update_metax(registration, metadata, file_bytes)

        # Publish to REMS and add REMS URL to Metax draft description.
        if publish_config.use_rems_service:
            await self._publish_rems(rems, registration, publish_config, registration_service)

        # Publish to Metax.
        if publish_config.use_metax_service:
            await self._publish_metax(registration)

    @staticmethod
    def _create_submission_registration(submission_id: str, title: str, description: str, doi: str) -> Registration:
        """Create a registration for a metadata object.

        :param submission_id: The submission id
        :param title: The submission title
        :param description: The submission description
        :param doi: The DOI
        :returns: The registration information
        """
        return Registration(
            submissionId=submission_id,
            title=title,
            description=description,
            doi=doi,
        )

    @staticmethod
    def _create_object_registration(
        submission_id: str,
        object_id: str,
        object_type: str,
        title: str,
        description: str,
        doi: str,
    ) -> Registration:
        """Create a registration for a metadata object with a title, description and DOI.

        :param submission_id: the submission id
        :param object_id: the object id
        :param object_type: the object type
        :param title: the object title
        :param description: the object description
        :param doi: the generated DOI
        :returns: The registration information
        """
        return Registration(
            submissionId=submission_id,
            objectId=object_id,
            objectType=object_type,
            title=title,
            description=description,
            doi=doi,
        )
