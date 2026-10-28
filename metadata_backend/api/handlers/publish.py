"""Publish API handler."""

from datetime import datetime

from fastapi import Request

from ...api.dependencies import SubmissionIdPathParam, UserDependency, WorkflowDependency
from ...conf.deployment import deployment_config
from ...conf.discovery import discovery_config
from ...helpers.logger import LOG
from ..exceptions import SystemException, UserException, external_service_call
from ..models.datacite import DataCiteMetadata
from ..models.models import Registration, SubmissionId
from ..models.rems import RemsCatalogueItem
from ..models.submission import Rems, Submission, SubmissionMetadata
from ..services.datacite import DataciteService
from ..services.rems import (
    find_rems_catalogue_item,
    find_rems_resource,
    resolve_rems_license_ids,
)
from ..services.workflow import workflow_profile
from .restapi import RESTAPIHandler
from .submission import SubmissionAPIHandler


class PublishAPIHandler(RESTAPIHandler):
    """Publish API handler."""

    @staticmethod
    def get_discovery_url(submission: Submission, registration: Registration) -> str:
        """Get discovery URL for the submission.

        :param submission: The submission
        :param registration: The registration
        :returns: The discovery URL
        """
        _id = workflow_profile(submission.workflow).discovery_id(submission, registration)
        return discovery_config().DISCOVERY_URL.format(id=_id)

    async def _register_draft_doi(self) -> str:
        """Register a draft DOI through Datacite directly or through CSC PID.

        :returns: The created DOI
        """
        with external_service_call("Failed to register DOI."):
            if self._handlers.datacite is not None:
                return await self._handlers.datacite.create_draft_doi()
            elif self._handlers.pid is not None:
                return await self._handlers.pid.create_draft_doi()

            raise SystemException("Failed to register DOI. No service configured.")

    async def _register_metax_id(self, submission_id: str, registration: Registration) -> None:
        with external_service_call(f"Failed to register Metax ID in submission '{submission_id}'."):
            metax_id = await self._handlers.metax.create_draft_dataset(
                registration.doi, registration.title, registration.description
            )
            registration.metaxId = metax_id

    async def _publish_datacite(
        self, submission: Submission, registration: Registration, datacite: DataCiteMetadata
    ) -> None:
        """Publish to DataCite or CSC PID.

        A retry sends the metadata again even if the DOI was already published, since the
        submission can have been changed after the failed publish. Publishing also prepares the
        DataCite metadata that is later sent to Metax.

        :param submission: The submission
        :param registration: The registration
        :param datacite: The DataCite metadata
        """
        with external_service_call("Failed to publish submission in DataCite."):
            discovery_url = self.get_discovery_url(submission, registration)

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
                    registration,
                    datacite,
                    discovery_url,
                    require_field_of_science=require_field_of_science,
                    # A stored DataCite URL means a failed publish already made the DOI findable.
                    # The retry then updates only the metadata.
                    make_findable=not registration.dataciteUrl,
                )

            if not registration.dataciteUrl:
                await self._services.registration.update_datacite_url(registration.submissionId, discovery_url)

    async def _update_metax(self, registration: Registration, metadata: SubmissionMetadata) -> None:
        """Update information in Metax.

        :param registration: The registration
        :param metadata: The submission metadata
        """
        with external_service_call(f"Failed to update submission '{registration.submissionId}' in Metax."):
            await self._handlers.metax.update_dataset_metadata(metadata, registration.metaxId, self._handlers.ror)

    async def _validate_metax(self, submission: Submission) -> None:
        """Check that the submission metadata can be mapped to Metax.

        :param submission: The submission
        :raises UserException: If the metadata can't be mapped to Metax.
        """
        with external_service_call(f"Failed to validate submission '{submission.submissionId}' for Metax."):
            await self._handlers.metax.validate_dataset_metadata(submission.metadata, self._handlers.ror)

    async def _is_published_to_rems(self, submission: Submission) -> bool:
        """Whether the submission is published to REMS.

        :param submission: The submission.
        :return: True if the submission is published to REMS.
        """
        return await workflow_profile(submission.workflow).is_published_to_rems(self._services, submission)

    async def _check_rems_license(self, submission: Submission, rems: Rems) -> None:
        """Check that the REMS license can be created.

        :param submission: The submission.
        :param rems: The REMS metadata.
        :raises UserException: if the REMS license cannot be created.
        """

        if not await self._is_published_to_rems(submission):
            return

        if not rems.licenses and self._services.license_provider is not None:
            await self._services.license_provider.get_license(submission)

    async def _publish_rems(self, submission: Submission, rems: Rems, registration: Registration) -> None:
        """Prepare dictionary with values to be published to REMS. Adds the metax id if available.

        :param submission: The submission metadata
        :param rems: The rems metadata
        :param registration: The registration
        """

        if not await self._is_published_to_rems(submission):
            LOG.info("Submission %s is not published to REMS.", registration.submissionId)
            return

        # Check that the workflow exists and get the organisation id.
        rems_workflow = await self._handlers.rems.get_workflow(rems.organizationId, rems.workflowId)
        organization_id = rems_workflow.organization.id

        # External REMS identifier assigned by us.
        resid = workflow_profile(submission.workflow).rems_resource_id(submission, registration)

        with external_service_call(f"Failed to publish submission '{registration.submissionId}' to REMS."):
            # Create REMS resource, or reuse the existing one.
            if not registration.remsResourceId:
                resource = await find_rems_resource(self._handlers.rems, resid, organization_id)
                if resource is not None:
                    # Internal REMS identifier assigned by REMS.
                    resource_id = resource.id
                    # Existing licenses are kept by design. The REMS API cannot modify licenses
                    # on an existing resource, so the kept licenses are logged rather than rejected.
                    LOG.warning(
                        "Reusing REMS resource %s for submission %s, keeping its licenses %s.",
                        resid,
                        registration.submissionId,
                        [rems_license.id for rems_license in resource.licenses],
                    )
                else:
                    # No active resource was found, so an active catalogue item for this resid belongs to a
                    # disabled or archived resource, and the check below would reject it for the created one.
                    # Checked first, since the created resource stays in REMS after the rollback and every
                    # retry would reuse it and fail the same way.
                    await find_rems_catalogue_item(self._handlers.rems, resid, organization_id, rems.workflowId, None)
                    license_ids = await resolve_rems_license_ids(
                        self._handlers.rems,
                        self._services.license_provider,
                        rems,
                        submission,
                        organization_id,
                    )

                    resource_id = await self._handlers.rems.create_resource(organization_id, license_ids, resid)
                await self._services.registration.update_rems_resource_id(registration.submissionId, str(resource_id))
                registration.remsResourceId = str(resource_id)
            else:
                resource_id = int(registration.remsResourceId)

            # Create REMS catalogue item, or reuse the existing one.
            catalogue_id = registration.remsCatalogueId
            catalogue_item: RemsCatalogueItem | None = None
            if not catalogue_id:
                catalogue_item = await find_rems_catalogue_item(
                    self._handlers.rems, resid, organization_id, rems.workflowId, resource_id
                )
                if catalogue_item is not None:
                    LOG.info(
                        "Reusing REMS catalogue item %s for submission %s.",
                        catalogue_item.id,
                        registration.submissionId,
                    )
                    catalogue_id = str(catalogue_item.id)
                else:
                    catalogue_id = str(
                        await self._handlers.rems.create_catalogue_item(
                            organization_id,
                            rems.workflowId,
                            resource_id,
                            registration.title,
                            self.get_discovery_url(submission, registration),
                        )
                    )
                await self._services.registration.update_rems_catalogue_id(registration.submissionId, catalogue_id)
                registration.remsCatalogueId = catalogue_id
            elif not submission.imported:
                catalogue_item = await self._handlers.rems.get_catalogue_item(int(catalogue_id))

            # An imported dataset's catalogue item may have been created outside this service, and is
            # reused unchanged. Otherwise an existing catalogue item was created by a failed publish, and
            # its title may have changed since. The discovery URL is built from identifiers that don't change.
            if catalogue_item is not None and not submission.imported:
                localization = catalogue_item.localizations.get("en")
                if localization is None or localization.title != registration.title:
                    await self._handlers.rems.edit_catalogue_item(
                        int(catalogue_id), registration.title, self.get_discovery_url(submission, registration)
                    )

            if not registration.remsUrl:
                registration.remsUrl = self._handlers.rems.get_application_url(catalogue_id)

                # Add rems URL to Metax description.
                if registration.metaxId:
                    await self._handlers.metax.update_dataset_description(
                        registration.metaxId, self._metax_description(registration)
                    )

                await self._services.registration.update_rems_url(registration.submissionId, registration.remsUrl)

    @staticmethod
    def _metax_description(registration: Registration) -> str:
        """Get the Metax dataset description, with the REMS application link once it is known.

        :param registration: The registration
        :returns: The Metax dataset description
        """
        if registration.remsUrl:
            return registration.description + f"\n\nSD Apply Application link: {registration.remsUrl}"
        return registration.description

    async def _update_registration_title_and_description(
        self, submission: Submission, rems: Rems, registration: Registration
    ) -> None:
        """Update the registration title and description, and the Metax dataset, if the submission has changed.

        The submission can be changed after a failed publish, before the publish is retried.
        DataCite and the REMS catalogue item are updated when they are published again.

        :param submission: The submission
        :param rems: The rems metadata
        :param registration: The registration
        """
        title = workflow_profile(submission.workflow).registration_title(submission, rems)
        if registration.title == title and registration.description == submission.description:
            return

        registration.title = title
        registration.description = submission.description

        # Metax is updated before the registration, so that a retry updates it again if this fails.
        if self._handlers.metax is not None and registration.metaxId:
            with external_service_call(f"Failed to update submission '{registration.submissionId}' in Metax."):
                await self._handlers.metax.update_dataset_title_and_description(
                    registration.metaxId, registration.title, self._metax_description(registration)
                )

        await self._services.registration.update_title_and_description(
            registration.submissionId, registration.title, registration.description
        )

    async def _publish_metax(
        self,
        registration: Registration,
    ) -> None:
        """Publish to Metax.

        :param registration: The registration
        """
        with external_service_call(f"Failed to publish submission '{registration.submissionId}' to Metax."):
            await self._handlers.metax.publish_dataset(registration.metaxId, registration.doi)

    @staticmethod
    def _require_datacite(submission: Submission, datacite: DataCiteMetadata | None) -> None:
        if workflow_profile(submission.workflow).requires_datacite and datacite is None:
            raise UserException(f"Submission '{submission.submissionId}' does not have required DataCite information.")

    async def publish_submission(
        self,
        req: Request,
        user: UserDependency,
        workflow: WorkflowDependency,
        submission_id: SubmissionIdPathParam,
    ) -> SubmissionId:
        """Publish submission, ingest data files and register submission in discovery services."""

        # Hidden parameter to allow submission to be published without files.
        no_files = req.query_params.get("no_files", "").lower() == "true"

        submission_service = self._services.submission
        project_service = self._services.project

        # Check that the user can modify this submission.
        await SubmissionAPIHandler.check_submission_modifiable(
            user.user_id, submission_id, submission_service, project_service, workflow=workflow
        )

        # Lock the submission so that a concurrent publish fails at once, rather than waiting for
        # this one or registering the same external identifiers again.
        await submission_service.lock_submission(submission_id)

        # A concurrent publish may have finished after the check above.
        await submission_service.check_not_published(submission_id)

        submission = await submission_service.get_submission_by_id(submission_id)

        jwt = self._services.auth._get_bearer_token(req.headers)
        if not no_files:
            await workflow_profile(submission.workflow).prepare_publish(
                self._services, submission_id, user.user_id, jwt
            )

        # Get DataCite metadata.
        datacite = None
        if submission.metadata:
            datacite = submission.metadata.to_datacite()
            # Set DataCite publication year.
            datacite.publicationYear = datetime.now().year

        self._require_datacite(submission, datacite)

        # Get REMS metadata.
        rems = submission.rems

        # Check that the submission contains REMS information.
        if not rems:
            raise UserException(f"Submission '{submission_id}' does not have required REMS information.")

        # Each registration step is committed in its own transaction, so that when a later step fails
        # and the request transaction is rolled back, a retry resumes from the stored registration
        # rather than registering another DOI, Metax dataset or REMS resource.

        if deployment_config().ALLOW_REGISTRATION:
            # Check REMS license creation before the DOI is registered.
            await self._check_rems_license(submission, rems)
            await self._register_submission(submission, datacite, rems)

        # Finish publishing after registrations.
        if not no_files:
            await workflow_profile(submission.workflow).finish_publish(self._services, submission_id, user.user_id, jwt)

        # Update submission status to published.
        await submission_service.publish(submission_id)

        LOG.info("Publishing submission with ID %r was successful.", submission_id)
        return SubmissionId(submissionId=submission_id)

    async def _register_submission(self, submission: Submission, datacite: DataCiteMetadata | None, rems: Rems) -> None:
        """Register submission with external discovery services.

        :param submission: The submission
        :param datacite: The datacite metadata
        :param rems: The rems metadata
        """

        registration_service = self._services.registration

        submission_id = submission.submissionId

        # Check the metadata for Metax before anything is registered, so that a user error
        # is reported before the DOI is published rather than after.
        if self._handlers.metax is not None:
            await self._validate_metax(submission)

        # Registrations are external identifiers assigned to the submission, e.g. a DOI or Metax ID.
        # We provide title, description and other descriptive information to register external
        # identifiers. Only some of the metadata objects are assigned external identifiers. These
        # are configured in the workflow. Registrations are created only if they have not been created
        # during a previous failed publish attempt.

        registration: Registration = await registration_service.get_registration(submission_id)

        self._require_datacite(submission, datacite)

        # Create registration.
        if registration is None:
            doi = None
            if datacite is not None:
                # Create DOI if DataCite metadata is available.
                doi = await self._register_draft_doi()

            # The registration title is later used as the DataCite, Metax and REMS catalogue item title.
            title = workflow_profile(submission.workflow).registration_title(submission, rems)

            registration = self._create_registration(submission_id, title, submission.description, doi)
            await registration_service.add_registration(registration)
        else:
            await self._update_registration_title_and_description(submission, rems, registration)

        # Register Metax ID. Requires DOI.
        if self._handlers.metax is not None:
            if registration.metaxId is None:
                await self._register_metax_id(submission_id, registration)
                await registration_service.update_metax_id(submission_id, registration.metaxId)

        # Publish to DataCite. Modifies the datacite information.
        if datacite:
            await self._publish_datacite(submission, registration, datacite)

        # Update Metax with DOI information.
        if self._handlers.metax is not None:
            # Update datacite metadata changed during DataCite publish.
            metadata = submission.metadata
            metadata.update_datacite(datacite)
            await self._update_metax(registration, metadata)

        # Publish to REMS and add REMS URL to Metax draft description.
        await self._publish_rems(submission, rems, registration)

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
