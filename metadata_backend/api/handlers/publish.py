"""Handle HTTP methods for server."""

import os
from datetime import date
from typing import Any, Callable, Iterator

from aiohttp import web
from aiohttp.web import Request, Response

from ...conf.conf import doi_config, get_workflow
from ...database.postgres.repositories.submission import (
    SUB_FIELD_DESCRIPTION,
    SUB_FIELD_DOI,
    SUB_FIELD_REMS,
    SUB_FIELD_TITLE,
)
from ...database.postgres.services.registration import RegistrationService
from ...helpers.logger import LOG
from ...helpers.workflow import PublishServiceConfig
from ..auth import get_authorized_user_id
from ..exceptions import SystemException, UserException
from ..models import File, Registration, SubmissionWorkflow
from ..resources import (
    get_file_provider_service,
    get_file_service,
    get_object_service,
    get_registration_service,
    get_submission_service,
)
from ..services.object import JsonObjectService
from .common import to_json
from .restapi import RESTAPIIntegrationHandler
from .submission import SubmissionAPIHandler

DISCOVERY_SERVICE_METAX = "metax"
DISCOVERY_SERVICE_BEACON = "beacon"
DATACITE_SERVICE_DATACITE = "datacite"
DATACITE_SERVICE_CSC = "csc"
REMS_SERVICE_CSC = "csc"


class PublishSubmissionAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for publishing submissions."""

    @staticmethod
    def _make_discovery_url(registration: Registration, discovery_config: PublishServiceConfig) -> str:
        """Make a discovery url.

        :param registration: The registration
        :param discovery_config: The discovery service configuration
        :returns: The discovery URL
        """
        if discovery_config.service == DISCOVERY_SERVICE_METAX:
            return PublishSubmissionAPIHandler._make_metax_discovery_url(registration.metax_id)
        if discovery_config.service == DISCOVERY_SERVICE_BEACON:
            return PublishSubmissionAPIHandler._make_beacon_discovery_url(registration.doi)

        raise SystemException(f"Unsupported discovery service: {discovery_config.service}")

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
        doi_info: dict[str, Any],
        *,
        related_dataset_doi: str | None = None,
    ) -> dict[str, Any]:
        """Prepare study object for DataCite publishing.

        :param doi: The DOI
        :param title: the title
        :param description: the description
        :param discovery_url: URL pointing to a  discovery service
        :param doi_info: the DOI info
        :param related_dataset_doi: Related dataset DOI.
        :returns: Data for DataCite publishing.
        """
        try:
            data: dict[str, Any] = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": doi_config["publisher"],
                        "publicationYear": date.today().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi.split("/")[0],
                        "suffix": doi.split("/")[1],
                        "types": {
                            "bibtex": "misc",
                            "citeproc": "collection",
                            "schemaOrg": "Collection",
                            "resourceTypeGeneral": "Collection",
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

            # Add subject info related to the subject name
            for i in range(len(doi_info["subjects"])):
                subject_code = doi_info["subjects"][i]["subject"].split(" - ")[0]
                subject_info = {
                    "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                    "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                    "valueUri": f"http://www.yso.fi/onto/okm-tieteenala/ta{subject_code}",
                    "classificationCode": subject_code,
                }
                doi_info["subjects"][i].update(subject_info)

            data["data"]["attributes"].update(doi_info)
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
        doi_info: dict[str, Any],
        *,
        related_study_doi: str | None = None,
    ) -> dict[str, Any]:
        """Prepare dataset for DataCite publishing.

        :param doi: The DOI
        :param title: the title
        :param description: the description
        :param discovery_url: URL pointing to a  discovery service
        :param doi_info: the DOI info
        :param related_study_doi: Related study DOI.
        :returns: Data for DataCite publishing.
        """
        try:
            data: dict[str, Any] = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": doi_config["publisher"],
                        "publicationYear": date.today().year,
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
                            "resourceTypeGeneral": "Dataset",
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

            # Add subject info related to the subject name
            for i in range(len(doi_info["subjects"])):
                subject_code = doi_info["subjects"][i]["subject"].split(" - ")[0]
                subject_info = {
                    "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                    "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                    "valueUri": f"http://www.yso.fi/onto/okm-tieteenala/ta{subject_code}",
                    "classificationCode": subject_code,
                }
                doi_info["subjects"][i].update(subject_info)

            data["data"]["attributes"].update(doi_info)
            LOG.debug("prepared dataset info: %r", data)
        except KeyError as e:
            raise SystemException(f"Could not prepare DOI data for DataCite: {str(e)}") from e

        return data

    async def _register_draft_doi(self, datacite_config: PublishServiceConfig, draft_doi_prefix: str) -> str:
        """Register a draft DOI through Datacite directly or through CSC PID.

        :param datacite_config: DataCite publish service configuration.
        :param draft_doi_prefix: The draft DOI prefix.
        :returns: The created DOI
        """
        try:
            if datacite_config.service == DATACITE_SERVICE_DATACITE:
                return await self.datacite_handler.create_draft_doi_datacite(draft_doi_prefix)
            if datacite_config.service == DATACITE_SERVICE_CSC:
                return await self.pid_handler.create_draft_doi_pid()
        except Exception as ex:
            raise SystemException("Failed to register DOI using DataCite. Please try again later.") from ex

        raise SystemException(f"Invalid DataCite service: '{datacite_config.service}'")

    async def _register_metax_id(self, submission_id: str, user_id: str, registration: Registration) -> None:
        try:
            metax_id = await self.metax_handler.post_dataset_as_draft(
                user_id, registration.doi, registration.title, registration.description
            )
            registration.metax_id = metax_id

        except Exception as ex:
            raise SystemException(
                f"Failed to register Metax ID in submission '{submission_id}'. Please try again later."
            ) from ex

    async def _prepare_datacite_publication(
        self, registrations: list[Registration], doi_info: dict[str, Any], discovery_config: PublishServiceConfig
    ) -> list[dict[str, Any]]:
        """Prepare list of data to publish in DataCite.

        All the required information is in the submission ``doiInfo`` and
        in the registrations that contain assigned DOIs, titles and descriptions.

        :param registrations: The registrations.
        :param doi_info: The DOI info
        :param discovery_config: The discovery service configuration
        :returns: List of data to publish in DataCite
        """
        datacite_data: list[dict[str, Any]] = []

        try:
            # we need to re-format these for Datacite, as in the JSON schemas
            # we split the words so that front-end will display them nicely
            if "relatedIdentifiers" in doi_info:
                for d in doi_info["relatedIdentifiers"]:
                    d.update(
                        (k, "".join(v.split())) for k, v in d.items() if k in {"resourceTypeGeneral", "relationType"}
                    )

            if "descriptions" in doi_info:
                for d in doi_info["descriptions"]:
                    d.update((k, "".join(v.split())) for k, v in d.items() if k == "descriptionType")

            if "fundingReferences" in doi_info:
                for d in doi_info["fundingReferences"]:
                    d.update((k, "".join(v.split())) for k, v in d.items() if k == "funderIdentifierType")

            # Keywords are only required for Metax integration.
            doi_info.pop("keywords", None)

            # Get dataset and study DOI.
            study_doi = None
            dataset_doi = None
            for registration in registrations:
                if registration.schema_type == "study":
                    study_doi = registration.doi
                else:
                    dataset_doi = registration.doi

            # Create DataCite data for study.
            for registration in registrations:
                discovery_url = self._make_discovery_url(registration, discovery_config)
                if registration.schema_type == "study":
                    data = self._prepare_datacite_study(
                        registration.doi,
                        registration.title,
                        registration.description,
                        discovery_url,
                        doi_info,
                        related_dataset_doi=dataset_doi,
                    )
                else:
                    data = self._prepare_datacite_dataset(
                        registration.doi,
                        registration.title,
                        registration.description,
                        discovery_url,
                        doi_info,
                        related_study_doi=study_doi,
                    )
                datacite_data.append(data)

        except KeyError as e:
            raise SystemException(f"Could not prepare data for DataCite: {str(e)}") from e

        return datacite_data

    async def _publish_datacite(
        self,
        registrations: list[Registration],
        doi_info: dict[str, Any],
        registration_service: RegistrationService,
        datacite_config: PublishServiceConfig,
        discovery_config: PublishServiceConfig,
    ) -> None:
        """Publish to DataCite.

        :param registrations: The registrations
        :param doi_info: The DOI Info
        :param registration_service: The registration service
        :param datacite_config: The datacite service configuration
        :param discovery_config: The discovery service configuration
        """
        try:
            datacite_data = await self._prepare_datacite_publication(registrations, doi_info, discovery_config)

            def _get_registration_by_doi(doi_: str) -> Registration:
                for registration_ in registrations:
                    if registration_.doi == doi_:
                        return registration_
                raise SystemException(f"Could not find registration with DOI: {doi_}")

            for data in datacite_data:
                doi = data["id"]
                datacite_url = data["data"]["attributes"]["url"]
                registration = _get_registration_by_doi(doi)
                if not registration.datacite_url:
                    if datacite_config.service == DATACITE_SERVICE_DATACITE:
                        await self.datacite_handler.publish(data)
                    elif datacite_config.service == DATACITE_SERVICE_CSC:
                        await self.pid_handler.publish(data)
                    else:
                        raise SystemException(f"Unsupported datacite service: {datacite_config.service}")

                    await registration_service.update_datacite_url(
                        registration.submission_id, datacite_url, object_id=registration.object_id
                    )
        except Exception as ex:
            raise SystemException(
                f"Failed to publish submission in DataCite. Please try again later: {str(ex)}"
            ) from ex

    async def _update_metax(
        self,
        registration: Registration,
        doi_info: dict[str, Any],
        file_bytes: int,
        *,
        related_dataset: Registration | None = None,
        related_study: Registration | None = None,
    ) -> None:
        """Update information in Metax.

        :param registration: The registration
        :param doi_info: The DOI info
        :param file_bytes: The number of file bytes
        :param related_dataset: A related dataset registration
        :param related_study: A related study registration
        """
        try:
            await self.metax_handler.update_dataset_with_doi_info(
                doi_info,
                registration.metax_id,
                file_bytes,
                related_dataset=related_dataset,
                related_study=related_study,
            )
        except Exception as ex:
            raise SystemException(
                f"Failed to update submission '{registration.submission_id}' in Metax. Please try again later."
            ) from ex

    async def _publish_rems(
        self,
        rems: dict[str, Any],
        registration: Registration,
        discovery_config: PublishServiceConfig,
        registration_service: RegistrationService,
    ) -> None:
        """Prepare dictionary with values to be published to REMS. Adds the metax id if available.

        :param submission_id: The submission id
        :param rems: The rems data
        :param registration: The registration
        :param discovery_config: The discovery configuration
        :param registration_service: The registration service.
        """
        try:
            data: dict[str, Any] = {
                "accession_id": registration.object_id,
                "schema": registration.schema_type,
                "doi": registration.doi,
                "description": registration.description,
                "localizations": {
                    "en": {
                        "title": registration.title,
                        "infourl": self._make_discovery_url(registration, discovery_config),
                    }
                },
            }
            if registration.metax_id:
                data.update({"metaxIdentifier": registration.metax_id})

            workflow_id = rems["workflowId"]
            organization_id = rems["organizationId"]
            licenses = rems["licenses"]

            if not registration.rems_resource_id:
                resource_id = await self.rems_handler.create_resource(
                    doi=registration.doi, organization_id=organization_id, licenses=licenses
                )
                await registration_service.update_rems_resource_id(
                    registration.submission_id, str(resource_id), object_id=registration.object_id
                )
                registration.rems_resource_id = str(resource_id)
            else:
                resource_id = int(registration.rems_resource_id)

            if not registration.rems_catalogue_id:
                catalogue_id = await self.rems_handler.create_catalogue_item(
                    resource_id=resource_id,
                    workflow_id=workflow_id,
                    organization_id=organization_id,
                    localizations=data["localizations"],
                )
                await registration_service.update_rems_catalogue_id(
                    registration.submission_id, catalogue_id, object_id=registration.object_id
                )
                registration.rems_catalogue_id = catalogue_id
            else:
                catalogue_id = registration.rems_catalogue_id

            if not registration.rems_url:
                rems_url = self.rems_handler.application_url(catalogue_id)

                # Add rems URL to Metax description.
                if registration.metax_id:
                    new_description = registration.description + f"\n\nSD Apply's Application link: {rems_url}"
                    await self.metax_handler.update_draft_dataset_description(registration.metax_id, new_description)

                await registration_service.update_rems_url(
                    registration.submission_id, rems_url, object_id=registration.object_id
                )
                registration.rems_url = rems_url
        except Exception as ex:
            raise SystemException(
                f"Failed to publish submission '{registration.submission_id}' to REMS. Please try again later."
            ) from ex

    async def _publish_metax(
        self,
        registration: Registration,
    ) -> None:
        """Publish to Metax.

        :param submission_id: The submission id
        :param registration: The registration
        """
        try:
            await self.metax_handler.publish_dataset(registration.metax_id, registration.doi)
        except Exception as ex:
            raise SystemException(
                f"Failed to publish submission '{registration.submission_id}' to Metax. Please try again later."
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
        no_files = (
            req.rel_url.query.get("no_files") == "true"
        )  # Hidden parameter to allow submission to be published without files.

        submission_service = get_submission_service(req)
        object_service = get_object_service(req)
        file_service = get_file_service(req)
        registration_service = get_registration_service(req)
        file_provider_service = get_file_provider_service(req)

        # Check that the user can modify this submission.
        await SubmissionAPIHandler.check_submission_modifiable(req, submission_id)

        workflow = await submission_service.get_workflow(submission_id)

        workflow_config = get_workflow(workflow.value)
        workflow_config.validate()

        # TODO(improve): validate links between metadata objects.
        # TODO(improve): inject accession numbers to metadata references.

        # Check single instance schemas.
        for schema in workflow_config.single_instance_schemas:
            if (await object_service.count_objects(submission_id, schema)) > 1:
                raise UserException(f"Submission '{submission_id}' contains more than one '{schema}' object.")

        # Check required schemas.
        for schema in workflow_config.required_schemas:
            if (await object_service.count_objects(submission_id, schema)) == 0:
                raise UserException(f"Submission '{submission_id}' does not contain any '{schema}' objects.")

        if not no_files:
            # Add all files in linked folder to the submission.
            folder = await submission_service.get_folder(submission_id)
            if workflow == SubmissionWorkflow.SDS:
                files = await file_provider_service.list_files_in_folder(folder)
                for file in files.root:
                    # Check that we have not added the file already.
                    # For now, accept that file bytes might have changed and some files
                    # might have been removed if a call to this endpoint has failed before.
                    if not await file_service.is_file_by_path(submission_id, file.path):
                        await file_service.add_file(
                            File(
                                submission_id=submission_id,
                                path=file.path,
                                bytes=file.bytes,
                            )
                        )

            # Check that the submission has at least one file.
            if await file_service.count_files(submission_id) == 0:
                raise UserException(f"Submission '{submission_id}' does not have any data files.")

        submission = await submission_service.get_submission_by_id(submission_id)
        doi_info = submission.get(SUB_FIELD_DOI)
        rems_info = submission.get(SUB_FIELD_REMS)

        datacite_config = workflow_config.publish_config.datacite_config
        rems_config = workflow_config.publish_config.rems_config
        discovery_config = workflow_config.publish_config.discovery_config

        # Check that the submission contains DOI information.
        if datacite_config and not doi_info:
            raise UserException(f"Submission '{submission_id}' does not have required DOI information.")

        # Check that the submission contains REMS information.
        if rems_config and not rems_info:
            raise UserException(f"Submission '{submission_id}' does not have required REMS information.")

        # Registrations are external identifiers assigned to the submission, e.g. a DOI or Metax ID.
        # We provide title, description and other descriptive information to register external
        # identifiers. Only some of the metadata objects are assigned external identifiers. These
        # are configured in the workflow. Registrations are created only if they have not been created
        # during a previous failed publish attempt.

        submission_registration: Registration | None = None
        object_registrations: list[Registration] = []

        # Register DOI for submission.

        if datacite_config.submission:
            submission_registration = await registration_service.get_registration_by_submission_id(submission_id)
            if submission_registration is None:
                doi = await self._register_draft_doi(datacite_config, "submission")
                submission_registration = self._create_submission_registration(
                    submission_id, submission[SUB_FIELD_TITLE], submission[SUB_FIELD_DESCRIPTION], doi
                )
                await registration_service.add_registration(submission_registration)

        # Register DOI for metadata objects.

        async for obj in object_service.repository.get_objects(submission_id):
            if obj.schema in datacite_config.schemas:
                registration = await registration_service.get_registration_by_object_id(obj.object_id)
                if registration is None:
                    doi = await self._register_draft_doi(datacite_config, obj.schema)
                    registration = self._create_object_registration(
                        submission_id, obj.object_id, obj.schema, obj.document, doi
                    )
                object_registrations.append(registration)
                await registration_service.add_registration(registration)

        # All existing and new registration now exist. Create a function
        # to return submission and metadata object registrations that are
        # supported by a configuration and optionally filtered by
        # the service name and a registration predicate.

        def _filtered_registrations(
            config_: PublishServiceConfig,
            service_: str | None = None,
            predicate_: Callable[[Registration], bool] | None = None,
        ) -> Iterator[Registration]:
            # Check that the configuration supports the requested service.
            if service_ and config_.service != service_:
                return
            # Yield submission registration.
            if config_.submission:
                if submission_registration and (predicate_ is None or predicate_(submission_registration)):
                    yield submission_registration
            # Yield metadata object registrations.
            for registration_ in object_registrations:
                if registration_.schema_type in config_.schemas and (predicate_ is None or predicate_(registration_)):
                    yield registration_

        # Register Metax IDs. Required DOI.

        # Register Metax ID for submission.
        for registration in _filtered_registrations(
            discovery_config, DISCOVERY_SERVICE_METAX, lambda r: r.metax_id is None
        ):
            await self._register_metax_id(submission_id, user_id, registration)
            await registration_service.update_metax_id(
                submission_id, registration.metax_id, object_id=registration.object_id
            )

        # Publish to DataCite. Requires DOIs.

        await self._publish_datacite(
            list(_filtered_registrations(datacite_config)),
            doi_info,
            registration_service,
            datacite_config,
            discovery_config,
        )

        file_bytes = await file_service.count_bytes(submission_id)

        # Update Metax with DOI information and file bytes.

        def _get_related_object_registration(schema_: str) -> tuple[Registration | None, Registration | None]:
            # Assumes that only a single study and dataset registration is allowed.
            for registration_ in object_registrations:
                if schema_ != registration_.schema_type:
                    if registration_.schema_type == "study":
                        return None, registration_  # Related study registration.
                    return registration_, None  # Related dataset registration.
            return None, None

        for registration in _filtered_registrations(discovery_config, DISCOVERY_SERVICE_METAX):
            related_dataset, related_study = None, None
            if registration.schema_type is not None:
                related_dataset, related_study = _get_related_object_registration(registration.schema_type)
            await self._update_metax(
                registration, doi_info, file_bytes, related_dataset=related_dataset, related_study=related_study
            )

        # Publish to REMS and add REMS URL to Metax draft description.

        for registration in _filtered_registrations(rems_config, REMS_SERVICE_CSC):
            await self._publish_rems(rems_info, registration, discovery_config, registration_service)

        # Publish to Metax.

        for registration in _filtered_registrations(discovery_config, DISCOVERY_SERVICE_METAX):
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
            submission_id=submission_id,
            title=title,
            description=description,
            doi=doi,
        )

    @staticmethod
    def _create_object_registration(
        submission_id: str, object_id: str, schema: str, document: dict[str, Any], doi: str
    ) -> Registration:
        """Create a registration for a metadata object with a title, description and DOI.

        :param submission_id: the submission id
        :param object_id: the object id
        :param schema: the metadata object schema
        :param document: the metadata object JSON document
        :param doi: the generated DOI
        :returns: The registration information
        """
        title, description = JsonObjectService.get_metadata_title_and_description(schema, document)
        return Registration(
            submission_id=submission_id,
            object_id=object_id,
            schema=schema,
            title=title,
            description=description,
            doi=doi,
        )
