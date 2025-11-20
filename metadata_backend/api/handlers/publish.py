"""Handle HTTP methods for server."""

import os
import traceback
from datetime import datetime
from typing import Any, Callable, Iterator

from aiohttp import web
from aiohttp.web import Request, Response

from ...database.postgres.services.registration import RegistrationService
from ...helpers.logger import LOG
from ..auth import get_authorized_user_id
from ..exceptions import SystemException, UserException
from ..json import to_json, to_json_dict
from ..models.datacite import DataCiteMetadata
from ..models.models import File, Registration
from ..models.submission import Rems, SubmissionMetadata, SubmissionWorkflow
from ..resources import (
    get_file_provider_service,
    get_file_service,
    get_object_service,
    get_registration_service,
    get_submission_service,
)
from ..services.publish import PublishConfig, PublishSource, format_subject_okm_field_of_science, get_publish_config
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

    @staticmethod
    def _prepare_datacite_study(
        doi: str,
        title: str,
        description: str,
        discovery_url: str,
        datacite: DataCiteMetadata,
        publish_config: PublishConfig,
        *,
        related_dataset_doi: str | None = None,
    ) -> dict[str, Any]:
        """Prepare study object for DataCite publishing.

        :param doi: The DOI
        :param title: the title
        :param description: the description
        :param discovery_url: URL pointing to a  discovery service
        :param datacite: the DataCite metadata
        :param related_dataset_doi: Related dataset DOI.
        :returns: Data for DataCite publishing.
        """
        try:
            data: dict[str, Any] = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi.split("/")[0],
                        "suffix": doi.split("/")[1],
                        "types": {
                            "bibtex": "misc",
                            "citeproc": "collection",
                            "schemaOrg": "Collection",
                        },
                        "url": discovery_url,
                        "identifiers": [
                            {
                                "identifierType": "DOI",
                                "doi": doi,
                            }
                        ],
                    },
                },
            }
            data["data"]["attributes"]["titles"] = [{"lang": None, "title": title, "titleType": None}]

            # The study description may have been extracted from study abstract or description.
            # There is no practical difference between them.
            data["data"]["attributes"]["descriptions"] = [
                {
                    "lang": None,
                    "description": description,
                    "descriptionType": "Other",
                }
            ]

            if related_dataset_doi:
                data["data"]["attributes"]["relatedIdentifiers"] = [
                    {
                        "relationType": "Describes",
                        "relatedIdentifier": related_dataset_doi,
                        "resourceTypeGeneral": "Dataset",
                        "relatedIdentifierType": "DOI",
                    }
                ]

            if publish_config.require_okm_field_of_science:
                format_subject_okm_field_of_science(datacite.subjects)

            data["data"]["attributes"].update(to_json_dict(datacite))

            # Override resource type
            data["data"]["attributes"]["resourceType"] = {
                "resourceTypeGeneral": "Collection",
                "resourceType": "Study",
            }

            LOG.debug("prepared study info: %r", data)
        except KeyError as e:
            raise SystemException(f"Could not prepare DOI data for DataCite: {str(e)}") from e

        return data

    @staticmethod
    def _prepare_datacite_dataset(
        doi: str,
        title: str,
        description: str,
        discovery_url: str,
        datacite: DataCiteMetadata,
        publish_config: PublishConfig,
        *,
        related_study_doi: str | None = None,
    ) -> dict[str, Any]:
        """Prepare dataset for DataCite publishing.

        :param doi: The DOI
        :param title: the title
        :param description: the description
        :param discovery_url: URL pointing to a  discovery service
        :param datacite: the DataCite metadata
        :param related_study_doi: Related study DOI.
        :returns: Data for DataCite publishing.
        """
        try:
            data: dict[str, Any] = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi.split("/")[0],
                        "suffix": doi.split("/")[1],
                        "types": {
                            "ris": "DATA",
                            "bibtex": "misc",
                            "citeproc": "dataset",
                            "schemaOrg": "Dataset",
                        },
                        "url": discovery_url,
                        "identifiers": [
                            {
                                "identifierType": "DOI",
                                "doi": doi,
                            }
                        ],
                    },
                },
            }

            data["data"]["attributes"]["titles"] = [{"lang": None, "title": title, "titleType": None}]

            data["data"]["attributes"]["descriptions"] = [
                {
                    "lang": None,
                    "description": description,
                    "descriptionType": "Other",
                }
            ]

            if related_study_doi:
                data["data"]["attributes"]["relatedIdentifiers"] = [
                    {
                        "relationType": "IsDescribedBy",
                        "relatedIdentifier": related_study_doi,
                        "resourceTypeGeneral": "Collection",
                        "relatedIdentifierType": "DOI",
                    }
                ]

            if publish_config.require_okm_field_of_science:
                format_subject_okm_field_of_science(datacite.subjects)

            data["data"]["attributes"].update(to_json_dict(datacite))
            LOG.debug("prepared dataset info: %r", data)
        except KeyError as e:
            raise SystemException(f"Could not prepare DOI data for DataCite: {str(e)}") from e

        return data

    async def _register_draft_doi(self, publish_config: PublishConfig, draft_doi_prefix: str) -> str:
        """Register a draft DOI through Datacite directly or through CSC PID.

        :param publish_config: publish configuration.
        :param draft_doi_prefix: The draft DOI prefix.
        :returns: The created DOI
        """
        try:
            if publish_config.use_datacite_service:
                return await self.datacite_handler.create_draft_doi_datacite(draft_doi_prefix)
            if publish_config.use_pid_service:
                return await self.pid_handler.create_draft_doi_pid()
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

    async def _prepare_datacite_publication(
        self, registrations: list[Registration], datacite: DataCiteMetadata, publish_config: PublishConfig
    ) -> list[dict[str, Any]]:
        """Prepare list of data to publish in DataCite.

        :param registrations: The registrations.
        :param datacite: The DataCite metadata
        :param publish_config: The publish configuration
        :returns: List of DataCite requests
        """
        datacite_requests: list[dict[str, Any]] = []

        try:
            # Get dataset and study DOI.
            study_doi = None
            dataset_doi = None
            for registration in registrations:
                if registration.objectType == "study":
                    study_doi = registration.doi
                else:
                    dataset_doi = registration.doi

            # Create DataCite data for study.
            for registration in registrations:
                discovery_url = self._make_discovery_url(registration, publish_config)
                if registration.objectType == "study":
                    data = self._prepare_datacite_study(
                        registration.doi,
                        registration.title,
                        registration.description,
                        discovery_url,
                        datacite,
                        publish_config,
                        related_dataset_doi=dataset_doi,
                    )
                else:
                    data = self._prepare_datacite_dataset(
                        registration.doi,
                        registration.title,
                        registration.description,
                        discovery_url,
                        datacite,
                        publish_config,
                        related_study_doi=study_doi,
                    )
                datacite_requests.append(data)

        except KeyError as e:
            raise SystemException(f"Could not prepare data for DataCite: {str(e)}") from e

        return datacite_requests

    async def _publish_datacite(
        self,
        registrations: list[Registration],
        datacite: DataCiteMetadata,
        registration_service: RegistrationService,
        publish_config: PublishConfig,
    ) -> None:
        """Publish to DataCite.

        :param registrations: The registrations
        :param datacite: The DataCite metadata
        :param registration_service: The registration service
        :param publish_config: The publish configuration
        """
        try:
            datacite_data = await self._prepare_datacite_publication(registrations, datacite, publish_config)

            def _get_registration_by_doi(doi_: str) -> Registration:
                for registration_ in registrations:
                    if registration_.doi == doi_:
                        return registration_
                raise SystemException(f"Could not find registration with DOI: {doi_}")

            for data in datacite_data:
                doi = data["id"]
                datacite_url = data["data"]["attributes"]["url"]
                registration = _get_registration_by_doi(doi)
                if not registration.dataciteUrl:
                    if publish_config.use_datacite_service:
                        await self.datacite_handler.publish(data)
                    elif publish_config.use_pid_service:
                        await self.pid_handler.publish(data)
                    else:
                        raise SystemException(f"Invalid publish configuration: {to_json(publish_config)}")

                    await registration_service.update_datacite_url(
                        registration.submissionId, datacite_url, object_id=registration.objectId
                    )
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
                await registration_service.update_rems_resource_id(
                    registration.submissionId, str(resource_id), object_id=registration.objectId
                )
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
                await registration_service.update_rems_catalogue_id(
                    registration.submissionId, catalogue_id, object_id=registration.objectId
                )
                registration.remsCatalogueId = catalogue_id
            else:
                catalogue_id = registration.remsCatalogueId

            if not registration.remsUrl:
                rems_url = self.rems_handler.application_url(catalogue_id)

                # Add rems URL to Metax description.
                if registration.metaxId:
                    new_description = registration.description + f"\n\nSD Apply's Application link: {rems_url}"
                    await self.metax_handler.update_draft_dataset_description(registration.metaxId, new_description)

                await registration_service.update_rems_url(
                    registration.submissionId, rems_url, object_id=registration.objectId
                )
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
                project_íd = await submission_service.get_project_id(submission_id)
                files = await file_provider_service.list_files_in_bucket(bucket, project_íd)
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

        # Registrations are external identifiers assigned to the submission, e.g. a DOI or Metax ID.
        # We provide title, description and other descriptive information to register external
        # identifiers. Only some of the metadata objects are assigned external identifiers. These
        # are configured in the workflow. Registrations are created only if they have not been created
        # during a previous failed publish attempt.

        submission_registration: Registration | None = None
        object_registrations: list[Registration] = []

        # Register DOI for submission.

        if publish_config.source == PublishSource.SUBMISSION:
            submission_registration = await registration_service.get_registration_by_submission_id(submission_id)
            if submission_registration is None:
                doi = await self._register_draft_doi(publish_config, "submission")
                submission_registration = self._create_submission_registration(
                    submission_id, submission.title, submission.description, doi
                )
                await registration_service.add_registration(submission_registration)

        # Register DOI for metadata objects.

        async for obj in object_service.repository.get_objects(submission_id):
            if publish_config.source == PublishSource.OBJECT and publish_config.object_type == obj.object_type:
                registration = await registration_service.get_registration_by_object_id(obj.object_id)
                if registration is None:
                    doi = await self._register_draft_doi(publish_config, obj.object_type)
                    registration = self._create_object_registration(
                        submission_id, obj.object_id, obj.object_type, obj.title, obj.description, doi
                    )
                object_registrations.append(registration)
                await registration_service.add_registration(registration)

        # All existing and new registration now exist. Create a function
        # to return submission and metadata object registrations that are
        # supported by a publish configuration and optionally filtered by
        # a registration predicate.

        def _filtered_registrations(
            publish_config_: PublishConfig,
            predicate_: Callable[[Registration], bool] | None = None,
        ) -> Iterator[Registration]:
            # Yield submission registration.
            if publish_config_.source == PublishSource.SUBMISSION:
                if submission_registration and (predicate_ is None or predicate_(submission_registration)):
                    yield submission_registration
            # Yield metadata object registrations.
            for registration_ in object_registrations:
                if (
                    publish_config_.source == PublishSource.OBJECT
                    and publish_config.object_type == registration_.objectType
                    and (predicate_ is None or predicate_(registration_))
                ):
                    yield registration_

        # Register Metax IDs. Required DOI.

        # Register Metax ID for submission.
        if publish_config.use_metax_service:
            for registration in _filtered_registrations(publish_config, lambda r: r.metaxId is None):
                await self._register_metax_id(submission_id, user_id, registration)
                await registration_service.update_metax_id(
                    submission_id, registration.metaxId, object_id=registration.objectId
                )

        # Publish to DataCite. Requires DOIs. Modifies the datacite information.
        if publish_config.use_pid_service or publish_config.use_datacite_service:
            await self._publish_datacite(
                list(_filtered_registrations(publish_config)),
                datacite,
                registration_service,
                publish_config,
            )

        file_bytes = await file_service.count_bytes(submission_id)

        # Update Metax with DOI information and file bytes.
        if publish_config.use_metax_service:

            for registration in _filtered_registrations(publish_config):
                # Update datacite metadata changed during DataCite publish.
                metadata = submission.metadata
                metadata.update_datacite(datacite)
                await self._update_metax(registration, metadata, file_bytes)

        # Publish to REMS and add REMS URL to Metax draft description.
        if publish_config.use_rems_service:
            for registration in _filtered_registrations(publish_config):
                await self._publish_rems(rems, registration, publish_config, registration_service)

        # Publish to Metax.
        if publish_config.use_metax_service:
            for registration in _filtered_registrations(publish_config):
                await self._publish_metax(registration)

        # Update submission status to published.
        await submission_service.publish(submission_id)

        LOG.info("Publishing submission with ID %r was successful.", submission_id)
        return web.Response(body=to_json({"submissionId": submission_id}), status=200, content_type="application/json")

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
