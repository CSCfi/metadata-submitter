"""Handle HTTP methods for server."""

from datetime import date, datetime
from typing import Any

import ujson
from aiohttp import web
from aiohttp.web import Request, Response

from metadata_backend.api.operators.file import FileOperator

from ...conf.conf import DATACITE_SCHEMAS, METAX_SCHEMAS, WORKFLOWS, discovery_config, doi_config
from ...helpers.logger import LOG
from ..operators.object import ObjectOperator
from ..operators.object_xml import XMLObjectOperator
from ..operators.submission import SubmissionOperator
from .restapi import RESTAPIIntegrationHandler


class PublishSubmissionAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for publishing submissions."""

    @staticmethod
    def _make_discovery_url(obj_data: dict[str, Any], workflow_name: str) -> str:
        """Make an url that points to a discovery service.

        :param obj_data: data of object to make URL for
        :param workflow_name: submission workflow used to determine discovery service
        :returns: URL pointing to a  discovery service
        """
        url = ""
        discovery_service = WORKFLOWS[workflow_name].get_workflow_discovery_service()

        if discovery_service == "metax":
            url = f"{discovery_config['metax_discovery_url']}{obj_data['metaxIdentifier']}"
        else:
            url = f"{discovery_config['beacon_discovery_url']}{obj_data['doi']}"

        return url

    @staticmethod
    def _prepare_datacite_study(
        study_data: dict[str, Any], general_info: dict[str, Any], discovery_url: str
    ) -> dict[str, Any]:
        """Prepare Study object for publishing.

        :param study_data: Study Object read from the database
        :param general_info: General information that is captured in front-end and set in ``doiInfo`` key
        :param discovery_url: URL pointing to a  discovery service
        :returns: Study Object ready to publish to Datacite directly or through CSC PID ms
        """
        study = {
            "id": study_data["doi"],
            "type": "dois",
            "data": {
                "attributes": {
                    "publisher": doi_config["publisher"],
                    "publicationYear": date.today().year,
                    "event": "publish",
                    "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                    "doi": study_data["doi"],
                    "prefix": study_data["doi"].split("/")[0],
                    "suffix": study_data["doi"].split("/")[1],
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
                            "doi": study_data["doi"],
                        }
                    ],
                    "descriptions": [],
                    "titles": [],
                },
            },
        }
        study["data"]["attributes"]["titles"].append(
            {"lang": None, "title": study_data["descriptor"]["studyTitle"], "titleType": None},
        )

        study["data"]["attributes"]["descriptions"].append(
            {
                "lang": None,
                "description": study_data["descriptor"]["studyAbstract"],
                "descriptionType": "Abstract",
            }
        )

        if "studyDescription" in study_data:
            study["data"]["attributes"]["descriptions"].append(
                {"lang": None, "description": study_data["studyDescription"], "descriptionType": "Other"}
            )

        # Add subject info related to the subject name
        for i in range(len(general_info["subjects"])):
            subject_code = general_info["subjects"][i]["subject"].split(" - ")[0]
            subject_info = {
                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                "valueUri": f"http://www.yso.fi/onto/okm-tieteenala/ta{subject_code}",
                "classificationCode": subject_code,
            }
            general_info["subjects"][i].update(subject_info)

        study["data"]["attributes"].update(general_info)
        LOG.debug("prepared study info: %r", study)

        return study

    def _prepare_datacite_dataset(
        self,
        study_doi: str,
        dataset_data: dict[str, Any],
        general_info: dict[str, Any],
        discovery_url: str,
    ) -> dict[str, Any]:
        """Prepare Dataset object for publishing.

        :param study_doi: Study DOI to link dataset to study at Datacite
        :param dataset_data: Dataset Object read from the database
        :param general_info: General information that is captured in front-end and set in `doiInfo` key
        :param discovery_url: URL pointing to a  discovery service
        :returns: Dataset Object ready to publish to Datacite directly or through CSC PID ms
        """
        dataset = {
            "id": dataset_data["doi"],
            "type": "dois",
            "data": {
                "attributes": {
                    "publisher": doi_config["publisher"],
                    "publicationYear": date.today().year,
                    "event": "publish",
                    "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                    "doi": dataset_data["doi"],
                    "prefix": dataset_data["doi"].split("/")[0],
                    "suffix": dataset_data["doi"].split("/")[1],
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
                            "doi": dataset_data["doi"],
                        }
                    ],
                    "descriptions": [],
                    "titles": [],
                },
            },
        }

        dataset["data"]["attributes"]["titles"].append(
            {"lang": None, "title": dataset_data["title"], "titleType": None},
        )

        dataset["data"]["attributes"]["descriptions"].append(
            {
                "lang": None,
                "description": dataset_data["description"],
                "descriptionType": "Other",
            }
        )

        # A Dataset is described by a Study
        if "relatedIdentifiers" not in dataset["data"]["attributes"]:
            dataset["data"]["attributes"]["relatedIdentifiers"] = []

        if study_doi:
            dataset["data"]["attributes"]["relatedIdentifiers"].append(
                {
                    "relationType": "IsDescribedBy",
                    "relatedIdentifier": study_doi,
                    "resourceTypeGeneral": "Collection",
                    "relatedIdentifierType": "DOI",
                }
            )

        # Add subject info related to the subject name
        for i in range(len(general_info["subjects"])):
            subject_code = general_info["subjects"][i]["subject"].split(" - ")[0]
            subject_info = {
                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                "valueUri": f"http://www.yso.fi/onto/okm-tieteenala/ta{subject_code}",
                "classificationCode": subject_code,
            }
            general_info["subjects"][i].update(subject_info)

        dataset["data"]["attributes"].update(general_info)
        LOG.debug("prepared dataset info: %r", dataset)

        return dataset

    async def create_draft_doi(self, workflow: str, schema: str) -> str:
        """Get a draft DOI through Datacite directly or from CSC PID depending on workflow.

        :param workflow: Workflow of submission
        :param schema: Schema to be included in DOI
        :returns: DOI
        """
        datacite_service = WORKFLOWS[workflow].get_endpoint_conf("datacite", "service")
        doi = (
            await self.datacite_handler.create_draft_doi_datacite(schema)
            if datacite_service == "datacite"
            else await self.pid_handler.create_draft_doi_pid()
        )

        return doi

    async def publish(self, workflow: str, data: dict[str, Any]) -> None:
        """Publish through Datacite directly or through CSC PID depending on workflow.

        :param workflow: Workflow of submission
        :param data: Data to publish
        """
        datacite_service = WORKFLOWS[workflow].get_endpoint_conf("datacite", "service")
        (
            await self.datacite_handler.publish(data)
            if datacite_service == "datacite"
            else await self.pid_handler.publish(data)
        )

    async def _prepare_datacite_publication(
        self, obj_op: ObjectOperator, submission: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Prepare dictionary with values for the Datacite DOI update.

        We need to prepare data for Study and Datasets, publish doi for each,
        and create links (relatedIdentifiers) between Study and Datasets.
        All the required information should be in the submission ``doiInfo``,
        as well as ``extraInfo`` which contains the draft DOIs created for the Study
        and each Dataset.

        :param obj_op: ObjectOperator for reading objects from database.
        :param submission: Submission data
        :returns: Tuple with the Study and list of Datasets and list of identifiers for publishing to Metax
        """
        datacite_study: dict[str, Any] = {}
        datacite_datasets: list[dict[str, Any]] = []

        # we need to re-format these for Datacite, as in the JSON schemas
        # we split the words so that front-end will display them nicely
        _info = submission["doiInfo"]
        if "relatedIdentifiers" in _info:
            for d in _info["relatedIdentifiers"]:
                d.update((k, "".join(v.split())) for k, v in d.items() if k in {"resourceTypeGeneral", "relationType"})

        if "contributors" in _info:
            for d in _info["contributors"]:
                d.update((k, "".join(v.split())) for k, v in d.items() if k == "contributorType")

        if "descriptions" in _info:
            for d in _info["descriptions"]:
                d.update((k, "".join(v.split())) for k, v in d.items() if k == "descriptionType")

        if "fundingReferences" in _info:
            for d in _info["fundingReferences"]:
                d.update((k, "".join(v.split())) for k, v in d.items() if k == "funderIdentifierType")

        try:
            # keywords are only required for Metax integration
            # thus we remove them
            _info.pop("keywords", None)

            _study_doi = ""

            async for _, schema, object_data in self.iter_submission_objects_data(submission, obj_op):
                if schema not in DATACITE_SCHEMAS:
                    continue
                if "doi" not in object_data:
                    object_data["doi"] = await self.create_draft_doi(submission["workflow"], schema)

                doi = object_data["doi"]
                discovery_url = self._make_discovery_url(object_data, submission["workflow"])

                if schema == "study":
                    _study_doi = doi
                    datacite_study = self._prepare_datacite_study(object_data, _info, discovery_url)

                    # there are cases where datasets are added first
                    datasets = [*datacite_datasets]
                    LOG.info("datacite datasets: %r", datacite_datasets)
                    for ds in datasets:
                        ds["data"]["attributes"]["relatedIdentifiers"].append(
                            {
                                "relationType": "IsDescribedBy",
                                "relatedIdentifier": _study_doi,
                                "resourceTypeGeneral": "Dataset",
                                "relatedIdentifierType": "DOI",
                            }
                        )
                        if "relatedIdentifiers" not in datacite_study["data"]["attributes"]:
                            datacite_study["data"]["attributes"]["relatedIdentifiers"] = []

                        datacite_study["data"]["attributes"]["relatedIdentifiers"].append(
                            {
                                "relationType": "Describes",
                                "relatedIdentifier": ds["data"]["attributes"]["doi"],
                                "resourceTypeGeneral": "Dataset",
                                "relatedIdentifierType": "DOI",
                            }
                        )

                else:
                    dataset = self._prepare_datacite_dataset(_study_doi, object_data, _info, discovery_url)
                    datacite_datasets.append(dataset)

                    # A Study describes a Dataset
                    # there are cases where datasets are added first
                    if "attributes" in datacite_study:
                        if "relatedIdentifiers" not in datacite_study["data"]["attributes"]:
                            datacite_study["data"]["attributes"]["relatedIdentifiers"] = []

                        datacite_study["data"]["attributes"]["relatedIdentifiers"].append(
                            {
                                "relationType": "Describes",
                                "relatedIdentifier": doi,
                                "resourceTypeGeneral": "Dataset",
                                "relatedIdentifierType": "DOI",
                            }
                        )
        # we catch all errors, if we missed even a key, that means some information has not
        # been properly recorded
        except KeyError as e:
            reason = f"Could not construct DOI data, reason: {e}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason)

        return datacite_study, datacite_datasets

    async def _publish_datacite(
        self, submission: dict[str, Any], obj_op: ObjectOperator, submission_op: SubmissionOperator
    ) -> dict[str, Any]:
        """Prepare dictionary with values to be published to Datacite.

        :param submission: Submission data
        :param obj_op: ObjectOperator for reading objects from database.
        :param submission_op: SubmissionOperator for updating submissions in the database
        :returns: Whether publishing to Datacite succeeded
        """
        datacite_study, datacite_datasets = await self._prepare_datacite_publication(obj_op, submission)
        extra_info_patch = []

        if datacite_study:
            # Study is optional for some workflows
            await self.publish(submission["workflow"], datacite_study)
            study_patch = {
                "op": "add",
                "path": "/extraInfo/studyIdentifier",
                "value": {
                    "identifier": {
                        "identifierType": "DOI",
                        "doi": datacite_study["id"],
                    },
                    "url": datacite_study["data"]["attributes"]["url"],
                    "types": datacite_study["data"]["attributes"]["types"],
                },
            }
            extra_info_patch.append(study_patch)

        for ds in datacite_datasets:
            await self.publish(submission["workflow"], ds)
            patch_ds = {
                "op": "add",
                "path": "/extraInfo/datasetIdentifiers/-",
                "value": {
                    "identifier": {
                        "identifierType": "DOI",
                        "doi": ds["id"],
                    },
                    "url": ds["data"]["attributes"]["url"],
                    "types": ds["data"]["attributes"]["types"],
                },
            }
            extra_info_patch.append(patch_ds)

        await submission_op.update_submission(submission["submissionId"], extra_info_patch)

        return datacite_study

    async def _pre_publish_metax(
        self,
        submission: dict[str, Any],
        operators: dict[str, Any],
        external_user_id: str,
    ) -> list[dict[str, Any]]:
        """Prepare dictionary with values to be published to Metax.

        :param submission: Submission data
        :param operators: instances of ObjectOperator, SubmissionOperator and FileOperator
        :param external_user_id: user_id
        :returns: Whether publishing to Metax succeeded
        """
        metax_datasets: list[dict[str, Any]] = []
        async for _, schema, object_data in self.iter_submission_objects_data(submission, operators["object"]):
            if schema in DATACITE_SCHEMAS:
                doi = object_data["doi"]
                # in case object is not added to metax due to server error
                if schema in METAX_SCHEMAS:
                    if not object_data["metaxIdentifier"]:
                        object_data["metaxIdentifier"] = await self.create_metax_dataset(
                            operators["object"],
                            schema,
                            object_data,
                            external_user_id,
                        )

                    metax_datasets.append(
                        {
                            "schema": schema,
                            "doi": doi,
                            "metaxIdentifier": object_data["metaxIdentifier"],
                        }
                    )

        await self.metax_handler.update_dataset_with_doi_info(
            await operators["submission"].read_submission(submission["submissionId"]), metax_datasets, operators["file"]
        )
        return metax_datasets

    async def _publish_rems(self, submission: dict[str, Any], obj_op: ObjectOperator) -> None:
        """Prepare dictionary with values to be published to REMS.

        :param submission: Submission data
        :param obj_op: ObjectOperator for reading objects from database.
        :returns: Whether publishing to REMS succeeded
        """
        rems_datasets: list[dict[str, Any]] = []
        async for accession_id, schema, object_data in self.iter_submission_objects_data(submission, obj_op):
            if schema in {"dataset", "bpdataset"}:
                rems_ds = {
                    "accession_id": accession_id,
                    "schema": schema,
                    "doi": object_data["doi"],
                    "description": object_data["description"],
                    "localizations": {
                        "en": {
                            "title": object_data["title"],
                            "infourl": self._make_discovery_url(object_data, submission["workflow"]),
                        }
                    },
                }
                if schema == "dataset":
                    rems_ds.update({"metaxIdentifier": object_data.get("metaxIdentifier", "")})
                rems_datasets.append(rems_ds)

        org_id = submission["rems"]["organizationId"]
        licenses = submission["rems"]["licenses"]
        workflow_id = submission["rems"]["workflowId"]
        for ds in rems_datasets:
            resource_id = await self.rems_handler.create_resource(
                doi=ds["doi"], organization_id=org_id, licenses=licenses
            )
            catalogue_id = await self.rems_handler.create_catalogue_item(
                resource_id=resource_id,
                workflow_id=workflow_id,
                organization_id=org_id,
                localizations=ds["localizations"],
            )

            # Add rems URL to metax dataset description
            rems_url = self.rems_handler.application_url(catalogue_id)
            if "metaxIdentifier" in ds:
                new_description = ds["description"] + f"\n\nSD Apply's Application link: {rems_url}"
                await self.metax_handler.update_draft_dataset_description(ds["metaxIdentifier"], new_description)

            # Update metadata object with preserved rems info that might need later
            await obj_op.update_metadata_object(
                ds["schema"],
                ds["accession_id"],
                {
                    "internal_rems": {
                        "url": rems_url,
                        "resourceId": resource_id,
                        "catalogueId": catalogue_id,
                    },
                },
            )

    async def publish_submission(self, req: Request) -> Response:
        """Update object submission specifically into published state.

        :param req: PATCH request
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        submission_op = SubmissionOperator(db_client)
        obj_op = ObjectOperator(db_client)
        xml_ops = XMLObjectOperator(db_client)
        file_op = FileOperator(db_client)

        # Check submission exists and is not already published
        await submission_op.check_submission_exists(submission_id)
        await submission_op.check_submission_published(submission_id, req.method)

        await self._handle_check_ownership(req, "submission", submission_id)

        submission = await submission_op.read_submission(submission_id)
        workflow = self.get_workflow(submission["workflow"])

        # Validate that submission has required data for publishing
        if "datacite" in workflow.required_schemas and "doiInfo" not in submission:
            raise web.HTTPBadRequest(reason=f"Submission '{submission_id}' must have the required DOI metadata.")

        if "dac" in workflow.required_schemas or "bprems" in workflow.required_schemas:
            if "rems" not in submission:
                raise web.HTTPBadRequest(reason=f"Submission '{submission_id}' must have rems information.")

        schemas_in_submission = set()
        has_study = False
        for _, schema in self.iter_submission_objects(submission):
            if schema == "study":
                has_study = True
            if schema not in workflow.schemas:
                reason = f"Submission of type {workflow.name} cannot have a '{schema}' but it does."
                raise web.HTTPBadRequest(reason=reason)
            if schema in workflow.single_instance_schemas and schema in schemas_in_submission:
                reason = f"Submission of type {workflow.name} has more than one '{schema}', and it can have only one"
                raise web.HTTPBadRequest(reason=reason)
            schemas_in_submission.add(schema)

        if workflow.name not in {"BigPicture", "SDSX"} and not has_study:
            raise web.HTTPBadRequest(reason=f"Submission '{submission_id}' must have a study.")

        for _, schema in self.iter_submission_objects(submission):
            schema_dict = workflow.schemas_dict[schema]
            if requires_or := schema_dict.get("requires_or", []):
                for item in requires_or:
                    if item in schemas_in_submission:
                        break
                else:
                    reason = (
                        f"'{schema}' object doesn't fulfill the submission's type {workflow.name} 'requires_or' "
                        f"field. It should include at least one of '{requires_or}'"
                    )
                    raise web.HTTPBadRequest(reason=reason)

        missing_schemas = set()
        for required_schema in workflow.required_schemas:
            # Exceptional schemas only require to be added to submission for publishing, their checks are added above.
            exceptional_schemas = {"dac", "bprems", "datacite", "file", "bpfile"}
            if required_schema not in schemas_in_submission and required_schema not in exceptional_schemas:
                missing_schemas.add(required_schema)
        if missing_schemas:
            required = ", ".join(missing_schemas)
            raise web.HTTPBadRequest(
                reason=f"{workflow.name} submission '{submission_id}' is missing '{required}' schema(s)."
            )

        # Create draft DOI and Metax records if not existing
        external_user_id = await self.get_user_external_id(req)
        async for accession_id, schema, object_data in self.iter_submission_objects_data(submission, obj_op):
            doi = object_data.get("doi", "")
            if schema in DATACITE_SCHEMAS and not doi:
                doi = await self.create_draft_doi(submission["workflow"], schema)
                object_data["doi"] = doi
                await obj_op.update_identifiers(schema, accession_id, {"doi": doi})

            if schema in METAX_SCHEMAS and "metaxIdentifier" not in object_data:
                await self.create_metax_dataset(obj_op, schema, object_data, external_user_id)

        # Publish to external services - must already have DOI and Metax ID
        publish_status = {}
        datacite_study = {}
        # check first if all the files are ready, if not raise HTTPBadRequest
        await file_op.check_submission_files_ready(submission_id)
        if "datacite" in workflow.endpoints:
            try:
                datacite_study = await self._publish_datacite(submission, obj_op, submission_op)
                publish_status["datacite"] = "published"
            except Exception as error:
                LOG.exception(error)
                publish_status["datacite"] = "failed"

        metax_datasets = []
        if "metax" in workflow.endpoints:
            try:
                operators = {"object": obj_op, "submission": submission_op, "file": file_op}
                metax_datasets = await self._pre_publish_metax(submission, operators, external_user_id)
                publish_status["metax"] = "published"
            except Exception as error:
                LOG.exception(error)
                publish_status["metax"] = "failed"

        if "rems" in workflow.endpoints:
            try:
                await self._publish_rems(submission, obj_op)
                publish_status["rems"] = "published"
            except Exception as error:
                LOG.exception(error)
                publish_status["rems"] = "failed"

        # REMS needs to update metax drafts' description, so we publish to Metax after publishing to REMS
        if "metax" in workflow.endpoints and metax_datasets:
            await self.metax_handler.publish_dataset(metax_datasets)

        # Delete draft objects from the submission
        for obj in submission["drafts"]:
            obj_schema = obj["schema"]
            obj_accession_id = obj["accessionId"]
            await obj_op.delete_metadata_object(obj_schema, obj_accession_id)
            await xml_ops.delete_metadata_object(f"xml-{obj_schema}", obj_accession_id)

        # Patch the submission into a published state
        _now = int(datetime.now().timestamp())
        patch: list[dict[str, Any]] = [
            {"op": "replace", "path": "/published", "value": True},
            {"op": "replace", "path": "/drafts", "value": []},
            {"op": "add", "path": "/datePublished", "value": _now},
            # when we publish the last modified date corresponds to the published date
            {"op": "replace", "path": "/lastModified", "value": _now},
            {"op": "add", "path": "/extraInfo/publisher", "value": doi_config["publisher"]},
            {"op": "add", "path": "/extraInfo/publicationYear", "value": date.today().year},
        ]
        if "datacite" in workflow.endpoints and datacite_study:
            patch.append(
                {
                    "op": "add",
                    "path": "/extraInfo/studyIdentifier",
                    "value": {
                        "identifier": {
                            "identifierType": "DOI",
                            "doi": datacite_study["id"],
                        },
                        "url": datacite_study["data"]["attributes"]["url"],
                        "types": datacite_study["data"]["attributes"]["types"],
                    },
                }
            )

        await submission_op.update_submission(submission_id, patch)

        result = {"submissionId": submission_id, "published": publish_status}
        body = ujson.dumps(result, escape_forward_slashes=False)
        LOG.info("Patching submission with ID %r was successful.", submission_id)
        return web.Response(body=body, status=200, content_type="application/json")
