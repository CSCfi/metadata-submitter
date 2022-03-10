"""Handle HTTP methods for server."""
from math import ceil
from typing import Any, Dict, List, Tuple, Union

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...helpers.doi import DOIHandler
from ...helpers.logger import LOG
from ...helpers.metax_api_handler import MetaxServiceHandler
from ...helpers.validator import JSONValidator
from ..operators import FolderOperator, Operator, XMLOperator
from .common import multipart_content
from .restapi import RESTAPIHandler


class ObjectAPIHandler(RESTAPIHandler):
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

        filter_list: List = []  # DEPRECATED, users don't own folders anymore
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
        LOG.debug(f"Pagination header links: {link_headers}")
        LOG.info(f"Querying for objects in {collection} resulted in {total_objects} objects ")
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
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        req_format = req.query.get("format", "json").lower()
        db_client = req.app["db_client"]
        operator = XMLOperator(db_client) if req_format == "xml" else Operator(db_client)
        type_collection = f"xml-{collection}" if req_format == "xml" else collection

        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownership(req, collection, accession_id)

        data, content_type = await operator.read_metadata_object(type_collection, accession_id)

        data = data if req_format == "xml" else ujson.dumps(data, escape_forward_slashes=False)
        LOG.info(f"GET object with accesssion ID {accession_id} from schema {collection}.")
        return web.Response(body=data, status=200, content_type=content_type)

    async def post_object(self, req: Request) -> Response:
        """Save metadata object to database.

        For JSON request body we validate it is consistent with the associated JSON schema.
        For CSV upload we allow it for a select number objects, currently: ``sample``.

        :param req: POST request
        :returns: JSON response containing accessionId for submitted object
        """
        _allowed_csv = {"sample"}
        _allowed_doi = {"study", "dataset"}
        schema_type = req.match_info["schema"]
        filename = ""
        cont_type = ""

        folder_id = req.query.get("folder", "")
        if not folder_id:
            reason = "Folder is required query parameter. Please provide folder id where object is added to."
            raise web.HTTPBadRequest(reason=reason)

        await self._handle_check_ownership(req, "folders", folder_id)
        patch_params = {}

        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        db_client = req.app["db_client"]
        folder_op = FolderOperator(db_client)

        # we need to check if there is already a study in a folder
        # we only allow one study per folder
        # this is not enough to catch duplicate entries if updates happen in parallel
        # that is why we check in db_service.update_study
        if not req.path.startswith("/drafts") and schema_type == "study":
            _ids = await folder_op.get_collection_objects(folder_id, collection)
            if len(_ids) == 1:
                reason = "Only one study is allowed per submission."
                raise web.HTTPBadRequest(reason=reason)

        content: Union[Dict[str, Any], str, List[Tuple[Any, str, str]]]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            _only_xml = False if schema_type in _allowed_csv else True
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
            if not req.path.startswith("/drafts"):
                JSONValidator(content, schema_type).validate
            operator = Operator(db_client)

        # Add a new metadata object or multiple objects if multiple were extracted
        url = f"{req.scheme}://{req.host}{req.path}"
        data: Union[List[Dict[str, str]], Dict[str, str]]
        if isinstance(content, List):
            LOG.debug(f"Inserting multiple objects for {schema_type}.")
            objects: List[Tuple[Dict[str, Any], str]] = []
            for item in content:
                json_data = await operator.create_metadata_object(collection, item[0])
                filename = item[2]
                objects.append((json_data, filename))
                LOG.info(
                    f"POST object with accesssion ID {json_data['accessionId']} in schema {collection} was successful."
                )

            # we format like this to make it consistent with the response from /submit endpoint
            data = [dict({"accessionId": item["accessionId"]}, **{"schema": schema_type}) for item, _ in objects]
            # we take the first result if we get multiple
            location_headers = CIMultiDict(Location=f"{url}/{data[0]['accessionId']}")
        else:
            json_data = await operator.create_metadata_object(collection, content)
            data = {"accessionId": json_data["accessionId"]}
            location_headers = CIMultiDict(Location=f"{url}/{json_data['accessionId']}")
            LOG.info(
                f"POST object with accesssion ID {json_data['accessionId']} in schema {collection} was successful."
            )
            objects = [(json_data, filename)]

        # Gathering data for object to be added to folder
        patch = self._prepare_folder_patch_new_object(collection, objects, cont_type)
        await folder_op.update_folder(folder_id, patch)

        # Create draft dataset to Metax catalog
        if collection in _allowed_doi:
            [await self.create_metax_dataset(req, collection, item) for item, _ in objects]

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

    async def delete_object(self, req: Request) -> Response:
        """Delete metadata object from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if folder published
        :raises: HTTPUnprocessableEntity if object does not belong to current user
        :returns: HTTPNoContent response
        """
        _allowed_doi = {"study", "dataset"}

        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        accession_id = req.match_info["accessionId"]
        db_client = req.app["db_client"]

        operator = Operator(db_client)
        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownership(req, collection, accession_id)

        folder_op = FolderOperator(db_client)
        exists, folder_id, published = await folder_op.check_object_in_folder(collection, accession_id)
        if exists:
            if published:
                reason = "published objects cannot be deleted."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)
            await folder_op.remove_object(folder_id, collection, accession_id)
        else:
            reason = "This object does not seem to belong to any user."
            LOG.error(reason)
            raise web.HTTPUnprocessableEntity(reason=reason)

        metax_id: str = ""
        doi_id: str = ""
        if collection in _allowed_doi:
            try:
                object_data, _ = await operator.read_metadata_object(collection, accession_id)
                # MYPY related if statement, Operator (when not XMLOperator) always returns object_data as dict
                if isinstance(object_data, dict):
                    metax_id = object_data["metaxIdentifier"]
                    doi_id = object_data["doi"]
            except KeyError:
                LOG.warning(f"MetadataObject {collection} {accession_id} was never added to Metax service.")

        accession_id = await operator.delete_metadata_object(collection, accession_id)

        # Delete draft dataset from Metax catalog
        if collection in _allowed_doi:
            metax_service = MetaxServiceHandler(req)
            await metax_service.delete_draft_dataset(metax_id)
            doi_service = DOIHandler()
            await doi_service.delete(doi_id)

        LOG.info(f"DELETE object with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(status=204)

    async def put_object(self, req: Request) -> Response:
        """Replace metadata object in database.

        For JSON request we don't allow replacing in the DB.
        For CSV upload we don't allow replace, as it is problematic to identify fields.

        :param req: PUT request
        :raises: HTTPUnsupportedMediaType if JSON replace is attempted
        :returns: JSON response containing accessionId for submitted object
        """
        _allowed_doi = {"study", "dataset"}

        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

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
            if not req.path.startswith("/drafts"):
                reason = "Replacing objects only allowed for XML."
                LOG.error(reason)
                raise web.HTTPUnsupportedMediaType(reason=reason)
            operator = Operator(db_client)

        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownership(req, collection, accession_id)

        folder_op = FolderOperator(db_client)
        exists, folder_id, published = await folder_op.check_object_in_folder(collection, accession_id)
        if exists:
            if published:
                reason = "Published objects cannot be updated."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)

        data = await operator.replace_metadata_object(collection, accession_id, content)
        patch = self._prepare_folder_patch_update_object(collection, data, filename)
        await folder_op.update_folder(folder_id, patch)

        # Update draft dataset to Metax catalog
        if collection in _allowed_doi:
            metax_service = MetaxServiceHandler(req)
            await metax_service.update_draft_dataset(collection, data)

        body = ujson.dumps({"accessionId": accession_id}, escape_forward_slashes=False)
        LOG.info(f"PUT object with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def patch_object(self, req: Request) -> Response:
        """Update metadata object in database.

        We do not support patch for XML.

        :param req: PATCH request
        :raises: HTTPUnauthorized if object is in published folder
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        db_client = req.app["db_client"]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            reason = "XML patching is not possible."
            raise web.HTTPUnsupportedMediaType(reason=reason)
        else:
            content = await self._get_data(req)
            operator = Operator(db_client)

        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownership(req, collection, accession_id)

        folder_op = FolderOperator(db_client)
        exists, folder_id, published = await folder_op.check_object_in_folder(collection, accession_id)
        if exists:
            if published:
                reason = "Published objects cannot be updated."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)

        accession_id = await operator.update_metadata_object(collection, accession_id, content)

        # If there's changed title it will be updated to folder
        try:
            _ = content["descriptor"]["studyTitle"] if collection == "study" else content["title"]
            patch = self._prepare_folder_patch_update_object(collection, content)
            await folder_op.update_folder(folder_id, patch)
        except (TypeError, KeyError):
            pass

        # Update draft dataset to Metax catalog
        if collection in {"study", "dataset"}:
            object_data, _ = await operator.read_metadata_object(collection, accession_id)
            # MYPY related if statement, Operator (when not XMLOperator) always returns object_data as dict
            if isinstance(object_data, Dict):
                metax_service = MetaxServiceHandler(req)
                await metax_service.update_draft_dataset(collection, object_data)
            else:
                raise ValueError("Object's data must be dictionary")

        body = ujson.dumps({"accessionId": accession_id}, escape_forward_slashes=False)
        LOG.info(f"PATCH object with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    def _prepare_folder_patch_new_object(self, schema: str, objects: List, cont_type: str) -> List:
        """Prepare patch operations list for adding an object or objects to a folder.

        :param schema: schema of objects to be added to the folder
        :param objects: metadata objects
        :param params: addidtional data required for db entry
        :returns: list of patch operations
        """
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
        for object, filename in objects:
            try:
                title = object["descriptor"]["studyTitle"] if schema in ["study", "draft-study"] else object["title"]
            except (TypeError, KeyError):
                title = ""

            patch_ops = {
                "op": "add",
                "path": path,
                "value": {
                    "accessionId": object["accessionId"],
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
        return patch

    def _prepare_folder_patch_update_object(self, schema: str, data: Dict, filename: str = "") -> List:
        """Prepare patch operation for updating object's title in a folder.

        :param schema: schema of object to be updated
        :param accession_id: object ID
        :param title: title to be updated
        :returns: dict with patch operation
        """
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
        return [patch_op]

    async def create_metax_dataset(self, req: Request, collection: str, object: Dict) -> str:
        """Handle connection to Metax api handler for dataset creation.

        Dataset or Study object is assigned with DOI
        and it's data is sent to Metax api handler.
        Object database entry is updated with metax ID returned by Metax service.

        :param req: HTTP request
        :param collection: object's schema
        :param object: metadata object
        :param folder_id: folder ID where metadata object belongs to
        :returns: Metax ID
        """
        metax_service = MetaxServiceHandler(req)
        operator = Operator(req.app["db_client"])
        LOG.info("Creating draft dataset to Metax.")
        object["doi"] = await self._draft_doi(collection)
        metax_id = await metax_service.post_dataset_as_draft(collection, object)

        new_info = {"doi": object["doi"], "metaxIdentifier": metax_id}
        await operator.create_metax_info(collection, object["accessionId"], new_info)

        return metax_id

    async def _draft_doi(self, schema_type: str) -> str:
        """Create draft DOI for study and dataset.

        The Draft DOI will be created only on POST and the data added to the
        folder. Any update of this should not be possible.

        :param schema_type: schema can be either study or dataset
        :returns: Dict with DOI of the study or dataset as well as the types.
        """
        doi_ops = DOIHandler()
        _doi_data = await doi_ops.create_draft(prefix=schema_type)

        LOG.debug(f"doi created with doi: {_doi_data['fullDOI']}")

        return _doi_data["fullDOI"]
