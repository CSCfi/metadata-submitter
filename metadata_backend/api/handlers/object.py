"""Handle HTTP methods for server."""
from datetime import datetime
from math import ceil
from typing import Any, Dict, List, Tuple, Union

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...conf.conf import API_PREFIX, DATACITE_SCHEMAS, METAX_SCHEMAS
from ...helpers.logger import LOG
from ...helpers.validator import JSONValidator
from ..operators import Operator, SubmissionOperator, XMLOperator
from .common import multipart_content
from .restapi import RESTAPIIntegrationHandler


class ObjectAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for Objects."""

    async def _handle_query(self, req: Request) -> Response:
        """Handle query results.

        :param req: GET request with query parameters
        :returns: JSON with query results
        """
        collection = req.match_info["schema"]
        req_format = req.query.get("format", "json").lower()
        if req_format == "xml":
            reason = "xml-formatted query results are not supported"
            raise web.HTTPBadRequest(reason=reason)

        page = self._get_page_param(req, "page", 1)
        per_page = self._get_page_param(req, "per_page", 10)
        db_client = req.app["db_client"]

        filter_list: List = []  # DEPRECATED, users don't own submissions anymore
        data, page_num, page_size, total_objects = await Operator(db_client).query_metadata_database(
            collection, req.query, page, per_page, filter_list
        )

        result = ujson.dumps(
            {
                "page": {
                    "page": page_num,
                    "size": page_size,
                    "totalPages": ceil(total_objects / per_page),
                    "totalObjects": total_objects,
                },
                "objects": data,
            },
            escape_forward_slashes=False,
        )
        url = f"{req.scheme}://{req.host}{req.path}"
        link_headers = self._header_links(url, page_num, per_page, total_objects)
        LOG.debug("Pagination header links: %r", link_headers)
        LOG.info("Querying for objects in collection: %r resulted in %d objects.", collection, total_objects)
        return web.Response(
            body=result,
            status=200,
            headers=link_headers,
            content_type="application/json",
        )

    async def get_object(self, req: Request) -> Response:
        """Get one metadata object by its accession id.

        Returns original XML object from backup if format query parameter is
        set, otherwise JSON.

        :param req: GET request
        :returns: JSON or XML response containing metadata object
        """
        accession_id = req.match_info["accessionId"]
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith(f"{API_PREFIX}/drafts") else schema_type

        req_format = req.query.get("format", "json").lower()
        db_client = req.app["db_client"]
        operator = XMLOperator(db_client) if req_format == "xml" else Operator(db_client)
        type_collection = f"xml-{collection}" if req_format == "xml" else collection

        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownership(req, collection, accession_id)

        data, content_type = await operator.read_metadata_object(type_collection, accession_id)

        data = data if req_format == "xml" else ujson.dumps(data, escape_forward_slashes=False)
        LOG.info("GET object with accesssion ID: %r from collection: %r.", accession_id, collection)
        return web.Response(body=data, status=200, content_type=content_type)

    async def post_object(self, req: Request) -> Response:
        """Save metadata object to database.

        For JSON request body we validate it is consistent with the associated JSON schema.
        For CSV upload we allow it for a select number objects, currently: ``sample``.

        :param req: POST request
        :returns: JSON response containing accessionId for submitted object
        """
        _allowed_csv = {"sample"}
        schema_type = req.match_info["schema"]
        LOG.debug("Creating in collection: %s an object", schema_type)
        filename = ""
        cont_type = ""

        submission_id = req.query.get("submission", "")
        if not submission_id:
            reason = (
                "Submission ID is a required query parameter. Please provide submission ID where object is added to."
            )
            raise web.HTTPBadRequest(reason=reason)

        await self._handle_check_ownership(req, "submission", submission_id)

        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith(f"{API_PREFIX}/drafts") else schema_type

        db_client = req.app["db_client"]
        submission_op = SubmissionOperator(db_client)

        # check if submission is already published
        # objects shouldn't be added to published submissions
        await submission_op.check_submission_published(submission_id)

        # we need to check if there is already a study in a submission
        # we only allow one study per submission
        # this is not enough to catch duplicate entries if updates happen in parallel
        # that is why we check in db_service.update_study
        if not req.path.startswith(f"{API_PREFIX}/drafts") and schema_type == "study":
            _ids = await submission_op.get_collection_objects(submission_id, collection)
            if len(_ids) == 1:
                reason = "Only one study is allowed per submission."
                raise web.HTTPBadRequest(reason=reason)

        content: Union[Dict[str, Any], str, List[Tuple[Any, str, str]]]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            _only_xml = schema_type not in _allowed_csv
            files, cont_type = await multipart_content(req, extract_one=True, expect_xml=_only_xml)
            if cont_type == "xml":
                # from this tuple we only care about the content
                # files should be of form (content, schema)
                content, _, filename = files[0]
            else:
                # for CSV files we need to treat this as a list of tuples (content, schema)
                content = files
            # If multipart request contains XML, XML operator is used.
            # Else the multipart request is expected to contain CSV file(s) which are converted into JSON.
            operator = XMLOperator(db_client) if cont_type == "xml" else Operator(db_client)
        else:
            content = await self._get_data(req)
            if not req.path.startswith(f"{API_PREFIX}/drafts"):
                JSONValidator(content, schema_type).validate
            operator = Operator(db_client)

        # Add a new metadata object or multiple objects if multiple were extracted
        url = f"{req.scheme}://{req.host}{req.path}"
        data: Union[List[Dict[str, str]], Dict[str, str]]
        objects: List[Tuple[Dict[str, Any], str]] = []
        if isinstance(content, List):
            LOG.debug("Inserting multiple objects for collection: %r.", schema_type)
            for item in content:
                json_data = await operator.create_metadata_object(collection, item[0])
                filename = item[2]
                listed_json = json_data if isinstance(json_data, list) else [json_data]
                for obj_from_json in listed_json:
                    objects.append((obj_from_json, filename))
                    LOG.info(
                        "POST object with accesssion ID: %r in collection: %r was successful.",
                        obj_from_json["accessionId"],
                        collection,
                    )
        else:
            json_data = await operator.create_metadata_object(collection, content)
            listed_json = json_data if isinstance(json_data, list) else [json_data]
            for listed_obj in listed_json:
                objects.append((listed_obj, filename))
                LOG.info(
                    "POST object with accesssion ID: %r in collection: %r was successful.",
                    listed_obj["accessionId"],
                    collection,
                )

        # Format like this to make it consistent with the response from /submit endpoint
        data = [dict({"accessionId": item["accessionId"]}, **{"schema": schema_type}) for item, _ in objects]
        # Take the first result if we get multiple
        location_headers = CIMultiDict(Location=f"{url}/{data[0]['accessionId']}")
        # Return data as single object if only one was extracted
        data = data[0] if len(data) == 1 else data

        # Gathering data for object to be added to submission
        patch = self._prepare_submission_patch_new_object(collection, objects, cont_type)
        await submission_op.update_submission(submission_id, patch)

        # Add DOI to object
        if collection in DATACITE_SCHEMAS:
            obj: Dict[str, Any]
            for obj, _ in objects:
                obj["doi"] = await self.create_draft_doi(collection)
                await Operator(db_client).update_identifiers(collection, obj["accessionId"], {"doi": obj["doi"]})

                # Create draft dataset to Metax catalog
                if self.metax_handler.enabled and collection in METAX_SCHEMAS:
                    try:
                        await self.create_metax_dataset(req, collection, obj)
                    except Exception as e:
                        # We don't care if it fails here
                        LOG.exception("create_metax_dataset failed: %r for collection: %r.", e, collection)

        body = ujson.dumps(data, escape_forward_slashes=False)

        return web.Response(
            body=body,
            status=201,
            headers=location_headers,
            content_type="application/json",
        )

    async def query_objects(self, req: Request) -> Response:
        """Query metadata objects from database.

        :param req: GET request with query parameters (can be empty).
        :returns: Query results as JSON
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        return await self._handle_query(req)

    async def delete_object(self, req: Request) -> web.HTTPNoContent:
        """Delete metadata object from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if submission published
        :raises: HTTPUnprocessableEntity if object does not belong to current user
        :returns: HTTPNoContent response
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        LOG.debug("Deleting object in collection: %r with accession ID: %r.", schema_type, accession_id)

        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith(f"{API_PREFIX}/drafts") else schema_type
        db_client = req.app["db_client"]

        operator = Operator(db_client)
        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownership(req, collection, accession_id)

        submission_op = SubmissionOperator(db_client)
        exists, submission_id, published = await submission_op.check_object_in_submission(collection, accession_id)
        if exists:
            if published:
                reason = "published objects cannot be deleted."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)
            await submission_op.remove_object(submission_id, collection, accession_id)
            _now = int(datetime.now().timestamp())
            lastModified = {"op": "replace", "path": "/lastModified", "value": _now}
            await submission_op.update_submission(submission_id, [lastModified])
        else:
            reason = "This object does not seem to belong to any user."
            LOG.error(reason)
            raise web.HTTPUnprocessableEntity(reason=reason)

        metax_id: str = ""
        doi_id: str = ""
        if collection in DATACITE_SCHEMAS:
            try:
                object_data, _ = await operator.read_metadata_object(collection, accession_id)
                # MYPY related if statement, Operator (when not XMLOperator) always returns object_data as dict
                if isinstance(object_data, dict):
                    doi_id = object_data["doi"]
                    if self.metax_handler.enabled and collection in METAX_SCHEMAS:
                        metax_id = object_data["metaxIdentifier"]
            except KeyError:
                LOG.exception(
                    "MetadataObject in collection: %r with accession ID: %r was not to Metax or Datacite.",
                    collection,
                    accession_id,
                )

        accession_id = await operator.delete_metadata_object(collection, accession_id)
        # we try to delete the object from the xml-{schema_type} collection
        xml_operator = XMLOperator(db_client)
        await xml_operator.delete_metadata_object(f"xml-{collection}", accession_id)

        # Delete draft dataset from Metax catalog
        if self.metax_handler.enabled and collection in METAX_SCHEMAS:
            try:
                await self.metax_handler.delete_draft_dataset(metax_id)
            except Exception as e:
                # We don't care if it fails here
                LOG.exception("delete_draft_dataset failed: %r for collection: %r", e, collection)
        if collection in DATACITE_SCHEMAS:
            await self.datacite_handler.delete(doi_id)

        LOG.info(
            "DELETE object with accession ID: %s in collection: %s was successful.",
            accession_id,
            collection,
        )
        return web.HTTPNoContent()

    async def put_object(self, req: Request) -> Response:
        """Replace metadata object in database.

        For JSON request we don't allow replacing in the DB.
        For CSV upload we don't allow replace, as it is problematic to identify fields.

        :param req: PUT request
        :raises: HTTPUnsupportedMediaType if JSON replace is attempted
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        LOG.debug("Replacing object in collection: %r with accession ID: %r.", schema_type, accession_id)

        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith(f"{API_PREFIX}/drafts") else schema_type

        db_client = req.app["db_client"]
        content: Union[Dict, str]
        operator: Union[Operator, XMLOperator]
        filename = ""
        if req.content_type == "multipart/form-data":
            files, _ = await multipart_content(req, extract_one=True, expect_xml=True)
            content, _, _ = files[0]
            operator = XMLOperator(db_client)
        else:
            content = await self._get_data(req)
            if not req.path.startswith(f"{API_PREFIX}/drafts"):
                reason = "Replacing objects only allowed for XML."
                LOG.error(reason)
                raise web.HTTPUnsupportedMediaType(reason=reason)
            operator = Operator(db_client)

        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownership(req, collection, accession_id)

        submission_op = SubmissionOperator(db_client)
        exists, submission_id, published = await submission_op.check_object_in_submission(collection, accession_id)
        if exists and published:
            reason = "Published objects cannot be updated."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        data = await operator.replace_metadata_object(collection, accession_id, content)
        patch = self._prepare_submission_patch_update_object(collection, data, filename)
        await submission_op.update_submission(submission_id, patch)

        # Update draft dataset to Metax catalog
        try:
            if self.metax_handler.enabled and collection in METAX_SCHEMAS:
                if data.get("metaxIdentifier", None):
                    external_id = await self.get_user_external_id(req)
                    await self.metax_handler.update_draft_dataset(external_id, collection, data)
                else:
                    await self.create_metax_dataset(req, collection, data)
        except Exception as e:
            # We don't care if it fails here
            LOG.exception("update_draft_dataset or create_metax_dataset failed: %r for collection %r.", e, collection)

        body = ujson.dumps({"accessionId": accession_id}, escape_forward_slashes=False)
        LOG.info("PUT object with accession ID: %r in collection: %r was successful.", accession_id, collection)
        return web.Response(body=body, status=200, content_type="application/json")

    async def patch_object(self, req: Request) -> Response:
        """Update metadata object in database.

        We do not support patch for XML.

        :param req: PATCH request
        :raises: HTTPUnauthorized if object is in published submission
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        LOG.debug("Patching object in collection: %r with accession ID: %r.", schema_type, accession_id)

        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith(f"{API_PREFIX}/drafts") else schema_type

        db_client = req.app["db_client"]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            reason = "XML patching is not possible."
            raise web.HTTPUnsupportedMediaType(reason=reason)

        content = await self._get_data(req)
        operator = Operator(db_client)

        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownership(req, collection, accession_id)

        submission_op = SubmissionOperator(db_client)
        exists, submission_id, published = await submission_op.check_object_in_submission(collection, accession_id)
        if exists and published:
            reason = "Published objects cannot be updated."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        accession_id = await operator.update_metadata_object(collection, accession_id, content)

        # If there's changed title it will be updated to submission
        try:
            _ = content["descriptor"]["studyTitle"] if collection == "study" else content["title"]
            patch = self._prepare_submission_patch_update_object(collection, content)
            await submission_op.update_submission(submission_id, patch)
        except (TypeError, KeyError):
            pass

        # Update draft dataset to Metax catalog
        try:
            if self.metax_handler.enabled and collection in METAX_SCHEMAS:
                object_data, _ = await operator.read_metadata_object(collection, accession_id)
                # MYPY related if statement, Operator (when not XMLOperator) always returns object_data as dict
                if isinstance(object_data, Dict):
                    external_id = await self.get_user_external_id(req)
                    if object_data.get("metaxIdentifier", None):
                        await self.metax_handler.update_draft_dataset(external_id, collection, object_data)
                    else:
                        await self.create_metax_dataset(req, collection, object_data)
                else:
                    raise ValueError("Object's data must be dictionary")
        except Exception as e:
            # We don't care if it fails here
            LOG.exception("update_draft_dataset or create_metax_dataset failed: %r for collection %s", e, collection)
            raise

        body = ujson.dumps({"accessionId": accession_id}, escape_forward_slashes=False)
        LOG.info("PATCH object with accession ID: %r in collection: %r was successful.", accession_id, collection)
        return web.Response(body=body, status=200, content_type="application/json")

    def _prepare_submission_patch_new_object(self, schema: str, objects: List, cont_type: str) -> List:
        """Prepare patch operations list for adding an object or objects to a submission.

        :param schema: schema of objects to be added to the submission
        :param objects: metadata objects
        :param cont_type: content type
        :returns: list of patch operations
        """
        LOG.info("Preparing submission patch for new objects")
        if not cont_type:
            submission_type = "Form"
        else:
            submission_type = cont_type.upper()

        if schema.startswith("draft"):
            path = "/drafts/-"
        else:
            path = "/metadataObjects/-"

        patch = []
        patch_ops: Dict[str, Any] = {}
        for obj, filename in objects:
            try:
                title = obj["descriptor"]["studyTitle"] if schema in ["study", "draft-study"] else obj["title"]
            except (TypeError, KeyError):
                title = ""

            patch_ops = {
                "op": "add",
                "path": path,
                "value": {
                    "accessionId": obj["accessionId"],
                    "schema": schema,
                    "tags": {
                        "submissionType": submission_type,
                        "displayTitle": title,
                    },
                },
            }
            if submission_type != "Form":
                patch_ops["value"]["tags"]["fileName"] = filename
            patch.append(patch_ops)

        _now = int(datetime.now().timestamp())
        lastModified = {"op": "replace", "path": "/lastModified", "value": _now}
        patch.append(lastModified)

        return patch

    def _prepare_submission_patch_update_object(self, schema: str, data: Dict, filename: str = "") -> List:
        """Prepare patch operation for updating object's title in a submission.

        :param schema: schema of object to be updated
        :param accession_id: object ID
        :param title: title to be updated
        :returns: dict with patch operation
        """
        LOG.info("Preparing submission patch for existing objects")
        if schema.startswith("draft"):
            path = "/drafts"
        else:
            path = "/metadataObjects"

        patch_op = {
            "op": "replace",
            "match": {path.replace("/", ""): {"$elemMatch": {"schema": schema, "accessionId": data["accessionId"]}}},
        }
        try:
            title = data["descriptor"]["studyTitle"] if schema in ["study", "draft-study"] else data["title"]
        except (TypeError, KeyError):
            title = ""

        if not filename:
            patch_op.update(
                {
                    "path": f"{path}/$/tags/displayTitle",
                    "value": title,
                }
            )
        else:
            patch_op.update(
                {
                    "path": f"{path}/$/tags",
                    "value": {"submissionType": "XML", "fileName": filename, "displayTitle": title},
                }
            )
        _now = int(datetime.now().timestamp())
        lastModified = {"op": "replace", "path": "/lastModified", "value": _now}

        return [patch_op, lastModified]
