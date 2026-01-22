"""Publish API handler."""

import traceback
from datetime import datetime

from aiohttp import web
from aiohttp.web import Request, Response

from ...conf.deployment import deployment_config
from ...helpers.logger import LOG
from ..exceptions import SystemException, UserException
from ..json import to_json
from ..models.datacite import DataCiteMetadata
from ..models.models import File, Registration
from ..models.submission import Rems, Submission, SubmissionMetadata, SubmissionWorkflow
from ..services.datacite import DataciteService
from .restapi import RESTAPIHandler
from .submission import SubmissionAPIHandler


class PublishAPIHandler(RESTAPIHandler):
    """Publish API handler."""

    def _get_rems_discovery_url(self, registration: Registration) -> str:
        """Get REMS discovery url.

        :param registration: The registration
        :returns: The discovery URL
        """
        if self._handlers.metax is not None:
            return self._handlers.rems.get_discovery_url(registration.metaxId)
        else:
            return self._handlers.rems.get_discovery_url(registration.doi)

    async def _register_draft_doi(self) -> str:
        """Register a draft DOI through Datacite directly or through CSC PID.

        :returns: The created DOI
        """
        try:
            if self._handlers.datacite is not None:
                return await self._handlers.datacite.create_draft_doi()
            elif self._handlers.pid is not None:
                return await self._handlers.pid.create_draft_doi()

            raise SystemException("Failed to register DOI. No service configured.")

        except Exception as ex:
            raise SystemException("Failed to register DOI. Please try again later.") from ex

    async def _register_metax_id(self, submission_id: str, registration: Registration) -> None:
        try:
            metax_id = await self._handlers.metax.create_draft_dataset(
                registration.doi, registration.title, registration.description
            )
            registration.metaxId = metax_id

        except Exception as ex:
            raise SystemException(
                f"Failed to register Metax ID in submission '{submission_id}'. Please try again later."
            ) from ex

    async def _publish_datacite_or_pid(self, registration: Registration, datacite: DataCiteMetadata) -> None:
        """Publish to DataCite or CSC PID.

        :param registration: The registration
        :param datacite: The DataCite metadata
        """
        try:
            discovery_url = self._get_rems_discovery_url(registration)

            if not registration.dataciteUrl:
                publish_service: DataciteService | None = None
                require_field_of_science: bool | None = None

                if self._handlers.datacite is not None:
                    publish_service = self._handlers.datacite
                    require_field_of_science = False
                elif self._handlers.pid is not None:
                    publish_service = self._handlers.pid
                    require_field_of_science = True

                if publish_service:
                    await publish_service.publish(
                        registration, datacite, discovery_url, require_field_of_science=require_field_of_science
                    )

                await self._services.registration.update_datacite_url(registration.submissionId, discovery_url)
        except Exception as ex:
            raise SystemException(
                f"Failed to publish submission in DataCite. Please try again later: {str(ex)}"
            ) from ex

    async def _update_metax(self, registration: Registration, metadata: SubmissionMetadata) -> None:
        """Update information in Metax.

        :param registration: The registration
        :param metadata: The submission metadata
        """
        try:
            await self._handlers.metax.update_dataset_metadata(metadata, registration.metaxId, self._handlers.ror)
        except Exception as ex:
            raise SystemException(
                f"Failed to update submission '{registration.submissionId}' in Metax. Please try again later."
            ) from ex

    async def _publish_rems(self, rems: Rems, registration: Registration) -> None:
        """Prepare dictionary with values to be published to REMS. Adds the metax id if available.

        :param rems: The rems data
        :param registration: The registration
        """
        try:
            if not registration.remsResourceId:
                resource_id = await self._handlers.rems.create_resource(
                    rems.organizationId, rems.workflowId, rems.licenses, registration.doi
                )
                await self._services.registration.update_rems_resource_id(registration.submissionId, str(resource_id))
                registration.remsResourceId = str(resource_id)
            else:
                resource_id = int(registration.remsResourceId)

            if not registration.remsCatalogueId:
                catalogue_id = str(
                    await self._handlers.rems.create_catalogue_item(
                        rems.organizationId,
                        rems.workflowId,
                        resource_id,
                        registration.title,
                        self._get_rems_discovery_url(registration),
                    )
                )
                await self._services.registration.update_rems_catalogue_id(registration.submissionId, catalogue_id)
                registration.remsCatalogueId = catalogue_id
            else:
                catalogue_id = registration.remsCatalogueId

            if not registration.remsUrl:
                rems_url = self._handlers.rems.get_application_url(catalogue_id)

                # Add rems URL to Metax description.
                if registration.metaxId:
                    new_description = registration.description + f"\n\nSD Apply's Application link: {rems_url}"
                    await self._handlers.metax.update_dataset_description(registration.metaxId, new_description)

                await self._services.registration.update_rems_url(registration.submissionId, rems_url)
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
            await self._handlers.metax.publish_dataset(registration.metaxId, registration.doi)
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

        submission_id = req.match_info["submissionId"]
        # Hidden parameter to allow submission to be published without files.
        no_files = req.rel_url.query.get("no_files") == "true"
        submission_service = self._services.submission
        project_service = self._services.project
        file_service = self._services.file
        file_provider_service = self._services.file_provider

        # Check that the user can modify this submission.
        await SubmissionAPIHandler.check_submission_modifiable(req, submission_id, submission_service, project_service)

        workflow = await self._services.submission.get_workflow(submission_id)

        if not no_files:
            # Add all files in linked bucket to the submission.
            bucket = await submission_service.get_bucket(submission_id)
            if not bucket:
                raise UserException(f"Submission '{submission_id}' is not linked to any bucket.")
            if workflow == SubmissionWorkflow.SD:
                files = await file_provider_service.list_files_in_bucket(bucket)
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
        if (self._handlers.datacite is not None or self._handlers.pid is not None) and not datacite:
            raise UserException(f"Submission '{submission_id}' does not have required DataCite information.")

        # Check that the submission contains REMS information.
        if not rems:
            raise UserException(f"Submission '{submission_id}' does not have required REMS information.")

        if deployment_config().ALLOW_REGISTRATION:
            await self._register_submission(submission, datacite, rems)

        # Update submission status to published.
        await submission_service.publish(submission_id)

        LOG.info("Publishing submission with ID %r was successful.", submission_id)
        return web.Response(body=to_json({"submissionId": submission_id}), status=200, content_type="application/json")

    async def _register_submission(self, submission: Submission, datacite: DataCiteMetadata, rems: Rems) -> None:
        """
        Register submission with external discovery services.

        :param submission: The submission
        :param datacite: The datacite metadata
        :param rems: The rems metadata
        """

        registration_service = self._services.registration

        submission_id = submission.submissionId

        # Registrations are external identifiers assigned to the submission, e.g. a DOI or Metax ID.
        # We provide title, description and other descriptive information to register external
        # identifiers. Only some of the metadata objects are assigned external identifiers. These
        # are configured in the workflow. Registrations are created only if they have not been created
        # during a previous failed publish attempt.

        registration: Registration = await registration_service.get_registration(submission_id)

        if registration is None:
            # Register DOI.
            doi = await self._register_draft_doi()
            registration = self._create_registration(submission_id, submission.title, submission.description, doi)
            await registration_service.add_registration(registration)

        # Registration has now been created with a DOI.

        # Register Metax IDs. Requires DOI.

        # Register Metax ID for submission.
        if self._handlers.metax is not None:
            if registration.metaxId is None:
                await self._register_metax_id(submission_id, registration)
                await registration_service.update_metax_id(submission_id, registration.metaxId)

        # Publish to DataCite. Requires DOIs. Modifies the datacite information.
        if self._handlers.datacite is not None or self._handlers.pid is not None:
            await self._publish_datacite_or_pid(registration, datacite)

        # Update Metax with DOI information.
        if self._handlers.metax is not None:
            # Update datacite metadata changed during DataCite publish.
            metadata = submission.metadata
            metadata.update_datacite(datacite)
            await self._update_metax(registration, metadata)

        # Publish to REMS and add REMS URL to Metax draft description.
        await self._publish_rems(rems, registration)

        # Publish to Metax.
        if self._handlers.metax is not None:
            await self._publish_metax(registration)

    @staticmethod
    def _create_registration(submission_id: str, title: str, description: str, doi: str) -> Registration:
        """Create submission registration.

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
