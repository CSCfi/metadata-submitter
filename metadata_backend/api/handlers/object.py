"""Handle HTTP methods for server."""
from math import ceil
from typing import Dict, Union, List, Any, Tuple

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...helpers.logger import LOG
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

        filter_list = await self._handle_user_objects_collection(req, collection)
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
        link_headers = await self._header_links(url, page_num, per_page, total_objects)
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
        _allowed_csv = ["sample"]
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        db_client = req.app["db_client"]
        content: Union[Dict[str, Any], str, List[Tuple[Any, str]]]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            _only_xml = False if schema_type in _allowed_csv else True
            files, cont_type = await multipart_content(req, extract_one=True, expect_xml=_only_xml)
            if cont_type == "xml":
                # from this tuple we only care about the content
                # files should be of form (content, schema)
                content, _ = files[0]
            else:
                # for CSV files we need to tread this as a list of tuples (content, schema)
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
            ids: List[Dict[str, str]] = []
            for item in content:
                accession_id = await operator.create_metadata_object(collection, item[0])
                ids.append({"accessionId": accession_id})
                LOG.info(f"POST object with accesssion ID {accession_id} in schema {collection} was successful.")
            # we format like this to make it consistent with the response from /submit endpoint
            data = [dict(item, **{"schema": schema_type}) for item in ids]
            # we take the first result if we get multiple
            location_headers = CIMultiDict(Location=f"{url}/{data[0]['accessionId']}")
        else:
            accession_id = await operator.create_metadata_object(collection, content)
            data = {"accessionId": accession_id}

            location_headers = CIMultiDict(Location=f"{url}/{accession_id}")
            LOG.info(f"POST object with accesssion ID {accession_id} in schema {collection} was successful.")

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
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        accession_id = req.match_info["accessionId"]
        db_client = req.app["db_client"]

        await Operator(db_client).check_exists(collection, accession_id)

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

        accession_id = await Operator(db_client).delete_metadata_object(collection, accession_id)

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
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        self._check_schema_exists(schema_type)
        collection = f"draft-{schema_type}" if req.path.startswith("/drafts") else schema_type

        db_client = req.app["db_client"]
        content: Union[Dict, str]
        operator: Union[Operator, XMLOperator]
        if req.content_type == "multipart/form-data":
            files, _ = await multipart_content(req, extract_one=True, expect_xml=True)
            content, _ = files[0]
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

        accession_id = await operator.replace_metadata_object(collection, accession_id, content)

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
        exists, _, published = await folder_op.check_object_in_folder(collection, accession_id)
        if exists:
            if published:
                reason = "Published objects cannot be updated."
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)

        accession_id = await operator.update_metadata_object(collection, accession_id, content)

        body = ujson.dumps({"accessionId": accession_id}, escape_forward_slashes=False)
        LOG.info(f"PATCH object with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")
