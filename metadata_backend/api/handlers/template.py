"""Handle HTTP methods for server."""
from typing import Union

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...helpers.logger import LOG
from ..middlewares import get_session
from ..operators import Operator, UserOperator, XMLOperator
from .restapi import RESTAPIHandler


class TemplatesAPIHandler(RESTAPIHandler):
    """API Handler for Templates."""

    async def get_template(self, req: Request) -> Response:
        """Get one metadata template by its accession id.

        Returns  JSON.

        :param req: GET request
        :returns: JSON response containing template
        """
        accession_id = req.match_info["accessionId"]
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"template-{schema_type}"

        db_client = req.app["db_client"]
        operator = Operator(db_client)

        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownedby_user(req, collection, accession_id)

        data, content_type = await operator.read_metadata_object(collection, accession_id)

        data = ujson.dumps(data, escape_forward_slashes=False)
        LOG.info(f"GET template with accesssion ID {accession_id} from schema {collection}.")
        return web.Response(body=data, status=200, content_type=content_type)

    async def post_template(self, req: Request) -> Response:
        """Save metadata template to database.

        For JSON request body we validate it is consistent with the
        associated JSON schema.

        :param req: POST request
        :returns: JSON response containing accessionId for submitted template
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"template-{schema_type}"

        db_client = req.app["db_client"]
        content = await self._get_data(req)

        user_op = UserOperator(db_client)
        current_user = get_session(req)["user_info"]

        operator = Operator(db_client)

        if isinstance(content, list):
            tmpl_list = []
            for num, tmpl in enumerate(content):
                if "template" not in tmpl:
                    reason = f"template key is missing from request body for element: {num}."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                accession_id = await operator.create_metadata_object(collection, tmpl["template"])
                data = [{"accessionId": accession_id, "schema": collection}]
                if "tags" in tmpl:
                    data[0]["tags"] = tmpl["tags"]
                await user_op.assign_objects(current_user, "templates", data)
                tmpl_list.append({"accessionId": accession_id})

            body = ujson.dumps(tmpl_list, escape_forward_slashes=False)
        else:
            if "template" not in content:
                reason = "template key is missing from request body."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            accession_id = await operator.create_metadata_object(collection, content["template"])
            data = [{"accessionId": accession_id, "schema": collection}]
            if "tags" in content:
                data[0]["tags"] = content["tags"]
            await user_op.assign_objects(current_user, "templates", data)

            body = ujson.dumps({"accessionId": accession_id}, escape_forward_slashes=False)

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{accession_id}")
        LOG.info(f"POST template with accesssion ID {accession_id} in schema {collection} was successful.")
        return web.Response(
            body=body,
            status=201,
            headers=location_headers,
            content_type="application/json",
        )

    async def patch_template(self, req: Request) -> Response:
        """Update metadata template in database.

        :param req: PATCH request
        :raises: HTTPUnauthorized if template is in published folder
        :returns: JSON response containing accessionId for submitted template
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        self._check_schema_exists(schema_type)
        collection = f"template-{schema_type}"

        db_client = req.app["db_client"]
        operator: Union[Operator, XMLOperator]

        content = await self._get_data(req)
        operator = Operator(db_client)

        await operator.check_exists(collection, accession_id)

        await self._handle_check_ownedby_user(req, collection, accession_id)

        accession_id = await operator.update_metadata_object(collection, accession_id, content)

        body = ujson.dumps({"accessionId": accession_id}, escape_forward_slashes=False)
        LOG.info(f"PATCH template with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_template(self, req: Request) -> Response:
        """Delete metadata template from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if folder published
        :raises: HTTPUnprocessableEntity if template does not belong to current user
        :returns: HTTPNoContent response
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"template-{schema_type}"

        accession_id = req.match_info["accessionId"]
        db_client = req.app["db_client"]

        await Operator(db_client).check_exists(collection, accession_id)

        await self._handle_check_ownedby_user(req, collection, accession_id)

        user_op = UserOperator(db_client)
        current_user = get_session(req)["user_info"]
        check_user = await user_op.check_user_has_doc(collection, current_user, accession_id)
        if check_user:
            await user_op.remove_objects(current_user, "templates", [accession_id])
        else:
            reason = "This template does not seem to belong to any user."
            LOG.error(reason)
            raise web.HTTPUnprocessableEntity(reason=reason)

        accession_id = await Operator(db_client).delete_metadata_object(collection, accession_id)

        LOG.info(f"DELETE template with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(status=204)
