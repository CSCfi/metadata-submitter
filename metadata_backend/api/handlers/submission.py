"""Handle HTTP methods for server."""
from datetime import date, datetime
from distutils.util import strtobool
from math import ceil
from typing import Dict, List, Tuple, Union

import aiohttp_session
import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...conf.conf import DATACITE_SCHEMAS, METAX_SCHEMAS, doi_config
from ...helpers.logger import LOG
from ...helpers.validator import JSONValidator
from ..operators import Operator, ProjectOperator, SubmissionOperator, UserOperator
from .restapi import RESTAPIIntegrationHandler


class SubmissionAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for submissions."""

    def _make_discovery_url(self, obj_data: Dict) -> str:
        """Make an url that points to a discovery service."""
        # TODO: Proper URL creation when metax is disabled
        if self.metax_handler.enabled and "metaxIdentifier" in obj_data:
            url = f"{doi_config['discovery_url']}{obj_data['metaxIdentifier']}"
        else:
            url = f"{doi_config['discovery_url']}{obj_data['doi']}"
        return url

    def _prepare_datacite_study(self, study_data: Dict, general_info: Dict) -> Dict:
        """Prepare Study object for publishing.

        :param study_data: Study Object read from the database
        :param general_info: General information that is captured in front-end and set in ``doiInfo`` key
        :returns: Study Object ready to publish to Datacite
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
                    "url": self._make_discovery_url(study_data),
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

        study["data"]["attributes"].update(general_info)
        LOG.debug(f"prepared study info: {study}")

        return study

    def _prepare_datacite_dataset(self, study_doi: str, dataset_data: Dict, general_info: Dict) -> Dict:
        """Prepare Dataset object for publishing.

        :param study_doi: Study DOI to link dataset to study at Datacite
        :param dataset_data: Dataset Object read from the database
        :param general_info: General information that is captured in front-end and set in `doiInfo` key
        :returns: Dataset Object ready to publish to Datacite
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
                    "url": self._make_discovery_url(dataset_data),
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

        dataset["data"]["attributes"].update(general_info)
        LOG.debug(f"prepared dataset info: {dataset}")

        return dataset

    async def _prepare_for_publishing(
        self, req: Request, obj_op: Operator, submission: Dict
    ) -> Tuple[dict, list, list, list]:
        """Prepare dictionary with values for the Datacite DOI update.

        We need to prepare data for Study and Datasets, publish doi for each,
        and create links (relatedIdentifiers) between Study and Datasets.
        All the required information should be in the submission ``doiInfo``,
        as well as ``extraInfo`` which contains the draft DOIs created for the Study
        and each Dataset.

        :param obj_op: Operator for reading objects from database.
        :param submission: Submission data
        :returns: Tuple with the Study and list of Datasets and list of identifiers for publishing to Metax
        """
        metax_ids: List[dict] = []
        datacite_study = {}
        datacite_datasets: List[dict] = []
        datacite_bpdatasets: List[dict] = []
        rems_datasets: List[dict] = []

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

            for _obj in submission["metadataObjects"]:
                accession_id = _obj["accessionId"]
                schema = _obj["schema"]
                object_data, _ = await obj_op.read_metadata_object(schema, accession_id)

                if not isinstance(object_data, dict):
                    continue
                if schema in DATACITE_SCHEMAS:
                    if "doi" not in object_data:
                        # in case object is not added to datacite due to server error
                        object_data["doi"] = await self.create_draft_doi(schema)

                    doi = object_data["doi"]
                    # in case object is not added to metax due to server error
                    if self.metax_handler.enabled and schema in METAX_SCHEMAS:
                        if not object_data["metaxIdentifier"]:
                            object_data["metaxIdentifier"] = await self.create_metax_dataset(req, schema, object_data)

                        metax_ids.append(
                            {
                                "schema": schema,
                                "doi": doi,
                                "metaxIdentifier": object_data["metaxIdentifier"],
                            }
                        )
                else:
                    continue

                if schema == "study":
                    _study_doi = doi

                    datacite_study = self._prepare_datacite_study(object_data, _info)

                    # there are cases where datasets are added first
                    datasets = [*datacite_datasets, *datacite_bpdatasets]
                    LOG.info(f"datacite datasets: {datacite_datasets}")
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

                elif schema in {"dataset", "bpdataset"}:
                    if self.rems_handler.enabled:
                        rems_ds = {
                            "accession_id": accession_id,
                            "schema": schema,
                            "doi": doi,
                            "description": object_data["description"],
                            "localizations": {
                                "en": {
                                    "title": object_data["title"],
                                    "infourl": self._make_discovery_url(object_data),
                                }
                            },
                        }
                        if self.metax_handler.enabled and "metaxIdentifier" in object_data:
                            rems_ds["metaxIdentifier"] = object_data["metaxIdentifier"]
                        rems_datasets.append(rems_ds)

                    dataset = self._prepare_datacite_dataset(_study_doi, object_data, _info)
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
        # we catch all errors, if we missed even a key, that means some information is not
        # properly recorded
        except Exception as e:
            reason = f"Could not construct DOI data, reason: {e}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason)

        return datacite_study, datacite_datasets, metax_ids, rems_datasets

    async def get_submissions(self, req: Request) -> Response:
        """Get a set of submissions owned by the project with pagination values.

        :param req: GET Request
        :returns: JSON list of submissions available for the user
        """
        session = await aiohttp_session.get_session(req)

        page = self._get_page_param(req, "page", 1)
        per_page = self._get_page_param(req, "per_page", 5)
        project_id = self._get_param(req, "projectId")
        sort = {"date": True, "score": False, "modified": False}
        db_client = req.app["db_client"]

        user_operator = UserOperator(db_client)

        current_user = session["user_info"]
        user = await user_operator.read_user(current_user)
        user_has_project = await user_operator.check_user_has_project(project_id, user["userId"])
        if not user_has_project:
            reason = f"user {user['userId']} is not affiliated with project {project_id}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        submission_query: Dict[str, Union[str, Dict[str, Union[str, bool, float]]]] = {"projectId": project_id}
        # Check if only published or draft submissions are requestsed
        if "published" in req.query:
            pub_param = req.query.get("published", "").title()
            if pub_param in {"True", "False"}:
                submission_query["published"] = {"$eq": bool(strtobool(pub_param))}
            else:
                reason = "'published' parameter must be either 'true' or 'false'"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

        if "name" in req.query:
            name_param = req.query.get("name", "")
            if name_param:
                submission_query["$text"] = {"$search": name_param}
            sort["score"] = True
            sort["date"] = False

        format_incoming = "%Y-%m-%d"
        format_query = "%Y-%m-%d %H:%M:%S"
        if "date_created_start" in req.query or "date_created_end" in req.query:
            date_param_start = req.query.get("date_created_start", "")
            date_param_end = req.query.get("date_created_end", "")

            if datetime.strptime(date_param_start, format_incoming) and datetime.strptime(
                date_param_end, format_incoming
            ):
                query_start = datetime.strptime(date_param_start + " 00:00:00", format_query).timestamp()
                query_end = datetime.strptime(date_param_end + " 23:59:59", format_query).timestamp()
                submission_query["dateCreated"] = {"$gte": query_start, "$lte": query_end}
            else:
                reason = f"'date_created_start' and 'date_created_end' parameters must be formated as {format_incoming}"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

        if "date_modified_start" in req.query or "date_modified_end" in req.query:
            date_param_start = req.query.get("date_modified_start", "")
            date_param_end = req.query.get("date_modified_end", "")

            if datetime.strptime(date_param_start, format_incoming) and datetime.strptime(
                date_param_end, format_incoming
            ):
                query_start = datetime.strptime(date_param_start + " 00:00:00", format_query).timestamp()
                query_end = datetime.strptime(date_param_end + " 23:59:59", format_query).timestamp()
                submission_query["lastModified"] = {"$gte": query_start, "$lte": query_end}
            else:
                reason = (
                    f"'date_modified_start' and 'date_modified_end' parameters must be formated as {format_incoming}"
                )
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

        if "name" in req.query and "date_created_start" in req.query:
            sort["score"] = True
            sort["date"] = True

        if "name" in req.query and "date_modified_start" in req.query and "date_created_start" not in req.query:
            sort["score"] = True
            sort["modified"] = True
            sort["date"] = False

        submission_operator = SubmissionOperator(db_client)
        submissions, total_submissions = await submission_operator.query_submissions(
            submission_query, page, per_page, sort
        )

        result = ujson.dumps(
            {
                "page": {
                    "page": page,
                    "size": per_page,
                    "totalPages": ceil(total_submissions / per_page),
                    "totalSubmissions": total_submissions,
                },
                "submissions": submissions,
            },
            escape_forward_slashes=False,
        )

        url = f"{req.scheme}://{req.host}{req.path}"
        link_headers = self._header_links(url, page, per_page, total_submissions)
        LOG.debug(f"Pagination header links: {link_headers}")
        LOG.info(f"Querying for project={project_id} submissions resulted in {total_submissions} submissions")
        return web.Response(
            body=result,
            status=200,
            headers=link_headers,
            content_type="application/json",
        )

    async def post_submission(self, req: Request) -> Response:
        """Save object submission to database.

        :param req: POST request
        :returns: JSON response containing submission ID for submitted submission
        """
        session = await aiohttp_session.get_session(req)

        db_client = req.app["db_client"]
        content = await self._get_data(req)

        JSONValidator(content, "submission").validate

        # Check that project exists
        project_op = ProjectOperator(db_client)
        await project_op.check_project_exists(content["projectId"])

        # Check that user is affiliated with project
        user_op = UserOperator(db_client)
        current_user = session["user_info"]
        user = await user_op.read_user(current_user)
        user_has_project = await user_op.check_user_has_project(content["projectId"], user["userId"])
        if not user_has_project:
            reason = f"user {user['userId']} is not affiliated with project {content['projectId']}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        operator = SubmissionOperator(db_client)
        submission = await operator.create_submission(content)

        body = ujson.dumps({"submissionId": submission}, escape_forward_slashes=False)

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{submission}")
        LOG.info(f"POST new submission with ID {submission} was successful.")
        return web.Response(body=body, status=201, headers=location_headers, content_type="application/json")

    async def get_submission(self, req: Request) -> Response:
        """Get one object submission by its submission id.

        :param req: GET request
        :raises: HTTPNotFound if submission not owned by user
        :returns: JSON response containing object submission
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)

        await operator.check_submission_exists(submission_id)

        await self._handle_check_ownership(req, "submission", submission_id)

        submission = await operator.read_submission(submission_id)

        LOG.info(f"GET submission with ID {submission_id} was successful.")
        return web.Response(
            body=ujson.dumps(submission, escape_forward_slashes=False), status=200, content_type="application/json"
        )

    async def patch_submission(self, req: Request) -> Response:
        """Update object submission with a specific submission id.

        Submission only allows the 'name' and 'description' values to be patched.

        :param req: PATCH request
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]

        operator = SubmissionOperator(db_client)

        await operator.check_submission_exists(submission_id)

        # Check patch operations in request are valid
        data = await self._get_data(req)
        if not isinstance(data, dict):
            reason = "Patch submission operation should be provided as a JSON object"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        patch_ops = []
        for key, value in data.items():
            if key not in {"name", "description"}:
                reason = f"Patch submission operation only accept the fields 'name', or 'description'. Provided '{key}'"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            patch_ops.append({"op": "replace", "path": f"/{key}", "value": value})
        # we update the submission last modified date
        _now = int(datetime.now().timestamp())
        patch_ops.append({"op": "replace", "path": "/lastModified", "value": _now})

        await self._handle_check_ownership(req, "submission", submission_id)

        upd_submission = await operator.update_submission(submission_id, patch_ops)

        body = ujson.dumps({"submissionId": upd_submission}, escape_forward_slashes=False)
        LOG.info(f"PATCH submission with ID {upd_submission} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def publish_submission(self, req: Request) -> Response:
        """Update object submission specifically into published state.

        :param req: PATCH request
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)
        obj_op = Operator(db_client)

        await operator.check_submission_exists(submission_id)

        await self._handle_check_ownership(req, "submission", submission_id)
        if self.metax_handler.enabled:
            await self.metax_handler.check_connection()

        submission = await operator.read_submission(submission_id)
        # Validate that submission seems to have required data for publishing
        if "doiInfo" not in submission:
            raise web.HTTPBadRequest(reason=f"Submission '{submission_id}' must have the required DOI metadata.")
        has_study = False
        for _obj in submission["metadataObjects"]:
            accession_id = _obj["accessionId"]
            schema = _obj["schema"]
            object_data, _ = await obj_op.read_metadata_object(schema, accession_id)  # pylint: disable=unused-variable
            if schema == "study":
                has_study = True
            if self.rems_handler.enabled and "dac" not in submission:
                raise web.HTTPBadRequest(reason=f"Submission '{accession_id}' must have DAC.")
        if not has_study:
            raise web.HTTPBadRequest(reason=f"Submission '{submission_id}' must have a study.")

        # we first try to publish the DOI before actually publishing the submission
        obj_ops = Operator(db_client)
        datacite_study, datacite_datasets, metax_ids, rems_datasets = await self._prepare_for_publishing(
            req, obj_ops, submission
        )
        extra_info_patch = []
        await self.datacite_handler.publish(datacite_study)
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
        datasets_patch = []

        for ds in datacite_datasets:
            await self.datacite_handler.publish(ds)
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
            datasets_patch.append(patch_ds)
        extra_info_patch.extend(datasets_patch)
        extra_info_submission = await operator.update_submission(submission_id, extra_info_patch)

        if self.rems_handler.enabled:
            org_id = submission["dac"]["organizationId"]
            licenses = submission["dac"]["licenses"]
            workflow_id = submission["dac"]["workflowId"]
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
                if self.metax_handler.enabled and "metaxIdentifier" in ds:
                    new_description = ds["description"] + f"\n\nDAC: {rems_url}"
                    await self.metax_handler.update_draft_dataset_description(ds["metaxIdentifier"], new_description)
                await obj_op.update_metadata_object(
                    ds["schema"],
                    ds["accession_id"],
                    {
                        "dac": {
                            "url": rems_url,
                            "workflowId": workflow_id,
                            "organizationId": org_id,
                            "resourceId": resource_id,
                            "catalogueId": catalogue_id,
                        },
                    },
                )

        # we next try to publish to Metax before actually publishing the submission
        if self.metax_handler.enabled:
            await self.metax_handler.update_dataset_with_doi_info(
                await operator.read_submission(extra_info_submission), metax_ids
            )
            await self.metax_handler.publish_dataset(metax_ids)

        # Delete draft objects from the submission
        for obj in submission["drafts"]:
            await obj_ops.delete_metadata_object(obj["schema"], obj["accessionId"])

        # Patch the submission into a published state
        _now = int(datetime.now().timestamp())
        patch = [
            {"op": "replace", "path": "/published", "value": True},
            {"op": "replace", "path": "/drafts", "value": []},
            {"op": "add", "path": "/datePublished", "value": _now},
            # when we publish the last modified date corresponds to the published date
            {"op": "replace", "path": "/lastModified", "value": _now},
            {"op": "add", "path": "/extraInfo/publisher", "value": doi_config["publisher"]},
            {"op": "add", "path": "/extraInfo/publicationYear", "value": date.today().year},
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
            },
        ]
        new_submission = await operator.update_submission(submission_id, patch)

        body = ujson.dumps({"submissionId": new_submission}, escape_forward_slashes=False)
        LOG.info(f"Patching submission with ID {new_submission} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_submission(self, req: Request) -> web.HTTPNoContent:
        """Delete object submission from database.

        :param req: DELETE request
        :returns: HTTP No Content response
        """
        await aiohttp_session.get_session(req)

        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)

        await operator.check_submission_exists(submission_id)
        await operator.check_submission_published(submission_id)

        await self._handle_check_ownership(req, "submission", submission_id)

        obj_ops = Operator(db_client)

        submission = await operator.read_submission(submission_id)

        for obj in submission["drafts"] + submission["metadataObjects"]:
            await obj_ops.delete_metadata_object(obj["schema"], obj["accessionId"])

        _submission_id = await operator.delete_submission(submission_id)

        LOG.info(f"DELETE submission with ID {_submission_id} was successful.")
        return web.HTTPNoContent()

    async def put_submission_path(self, req: Request) -> Response:
        """Put or replace metadata to a submission.

        :param req: PUT request with metadata schema in the body
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)

        await operator.check_submission_exists(submission_id)
        await self._handle_check_ownership(req, "submission", submission_id)

        submission = await operator.read_submission(submission_id)

        data = await self._get_data(req)

        if req.path.endswith("doi"):
            schema = "doiInfo"
        elif req.path.endswith("dac"):
            # TODO: create an EGA DAC object from REMS contact information
            schema = "dac"
            if self.rems_handler.enabled:
                await self.check_dac_ok({"dac": data})
            else:
                raise web.HTTPBadRequest(reason="Attempted to update REMS DAC, but REMS is not enabled.")
        else:
            raise web.HTTPNotFound(reason=f"'{req.path}' does not exist")

        submission[schema] = data
        JSONValidator(submission, "submission").validate  # pylint: disable=expression-not-assigned

        op = "add"
        if schema in submission:
            op = "replace"
        patch = [
            {"op": op, "path": f"/{schema}", "value": data},
        ]
        upd_submission = await operator.update_submission(submission_id, patch)

        body = ujson.dumps({"submissionId": upd_submission}, escape_forward_slashes=False)
        LOG.info(f"PUT '{schema}' in submission with ID {submission_id} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")
