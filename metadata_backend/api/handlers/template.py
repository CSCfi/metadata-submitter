"""Handle HTTP methods for server."""
from typing import Union

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...helpers.logger import LOG
from ..middlewares import get_session
from ..operators import Operator, ProjectOperator, UserOperator, XMLOperator
from .restapi import RESTAPIHandler


class TemplatesAPIHandler(RESTAPIHandler):
    """API Handler for Templates."""

    async def get_templates(self, req: Request) -> Response:
        """Get a set of templates owned by the project.

        :param req: GET Request
        :returns: JSON list of templates available for the user
        """
        project_id = self._get_param(req, "projectId")
        db_client = req.app["db_client"]

        user_operator = UserOperator(db_client)
        current_user = get_session(req)["user_info"]
        user = await user_operator.read_user(current_user)
        user_has_project = await user_operator.check_user_has_project(project_id, user["userId"])
        if not user_has_project:
            reason = f"user {user['userId']} is not affiliated with project {project_id}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        operator = Operator(db_client)
        templates = await operator.query_templates_by_project(project_id)

        result = ujson.dumps(
            templates,
            escape_forward_slashes=False,
        )

        LOG.info(f"Querying for project={project_id} templates resulted in {len(templates)} templates")
        return web.Response(
            body=result,
            status=200,
            content_type="application/json",
        )

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

        await self._handle_check_ownership(req, collection, accession_id)

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

        # Operators
        project_op = ProjectOperator(db_client)
        user_op = UserOperator(db_client)
        operator = Operator(db_client)

        if isinstance(content, list):
            tmpl_list = []
            for num, tmpl in enumerate(content):
                if "template" not in tmpl:
                    reason = f"template key is missing from request body for element: {num}."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)

                # No schema validation, so must check that project is set
                if "projectId" not in tmpl:
                    reason = "projectId is a mandatory POST key"
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)

                # Check that project exists and user is affiliated with it
                await project_op._check_project_exists(tmpl["projectId"])
                current_user = get_session(req)["user_info"]
                user = await user_op.read_user(current_user)
                user_has_project = await user_op.check_user_has_project(tmpl["projectId"], user["userId"])
                if not user_has_project:
                    reason = f"user {user['userId']} is not affiliated with project {tmpl['projectId']}"
                    LOG.error(reason)
                    raise web.HTTPUnauthorized(reason=reason)

                # Process template
                # Move projectId to template structure, so that it is saved in mongo
                tmpl["template"]["projectId"] = tmpl["projectId"]
                json_data = await operator.create_metadata_object(collection, tmpl["template"])
                data = [{"accessionId": json_data["accessionId"], "schema": collection}]
                if "tags" in tmpl:
                    data[0]["tags"] = tmpl["tags"]
                await project_op.assign_templates(tmpl["projectId"], data)
                tmpl_list.append({"accessionId": json_data["accessionId"]})

            body = ujson.dumps(tmpl_list, escape_forward_slashes=False)
        else:
            if "template" not in content:
                reason = "template key is missing from request body."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

            # No schema validation, so must check that project is set
            if "projectId" not in content:
                reason = "projectId is a mandatory POST key"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

            # Check that project exists and user is affiliated with it
            await project_op._check_project_exists(content["projectId"])
            current_user = get_session(req)["user_info"]
            user = await user_op.read_user(current_user)
            user_has_project = await user_op.check_user_has_project(content["projectId"], user["userId"])
            if not user_has_project:
                reason = f"user {user['userId']} is not affiliated with project {content['projectId']}"
                LOG.error(reason)
                raise web.HTTPUnauthorized(reason=reason)

            # Process template
            # Move projectId to template structure, so that it is saved in mongo
            content["template"]["projectId"] = content["projectId"]
            json_data = await operator.create_metadata_object(collection, content["template"])
            data = [{"accessionId": json_data["accessionId"], "schema": collection}]
            if "tags" in content:
                data[0]["tags"] = content["tags"]
            await project_op.assign_templates(content["projectId"], data)

            body = ujson.dumps({"accessionId": json_data["accessionId"]}, escape_forward_slashes=False)

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{json_data['accessionId']}")
        LOG.info(f"POST template with accesssion ID {json_data['accessionId']} in schema {collection} was successful.")
        return web.Response(
            body=body,
            status=201,
            headers=location_headers,
            content_type="application/json",
        )

    async def patch_template(self, req: Request) -> Response:
        """Update metadata template in database.

        :param req: PATCH request
        :raises: HTTPUnauthorized if template is in published submission
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

        _, project_id = await self._handle_check_ownership(req, collection, accession_id)

        # Update the templates-list in project-collection
        if "index" in content and "tags" in content:
            LOG.debug("update template-list tags")
            index = content.pop("index")
            tags = content.pop("tags")
            update_operation = [
                {
                    "op": "replace",
                    "path": f"/templates/{index}/tags",
                    "value": tags,
                }
            ]
            project_operator = ProjectOperator(db_client)
            await project_operator.update_project(project_id, update_operation)

        # Update the actual template data in template-collection
        accession_id = await operator.update_metadata_object(collection, accession_id, content)

        body = ujson.dumps({"accessionId": accession_id}, escape_forward_slashes=False)
        LOG.info(f"PATCH template with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_template(self, req: Request) -> Response:
        """Delete metadata template from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if submission published
        :raises: HTTPUnprocessableEntity if template does not belong to current user
        :returns: HTTPNoContent response
        """
        schema_type = req.match_info["schema"]
        self._check_schema_exists(schema_type)
        collection = f"template-{schema_type}"
        accession_id = req.match_info["accessionId"]
        db_client = req.app["db_client"]

        await Operator(db_client).check_exists(collection, accession_id)
        project_operator = ProjectOperator(db_client)

        project_ok, project_id = await self._handle_check_ownership(req, collection, accession_id)
        if project_ok:
            await project_operator.remove_templates(project_id, [accession_id])
        else:
            reason = "This template does not belong to this project."
            LOG.error(reason)
            raise web.HTTPUnprocessableEntity(reason=reason)

        accession_id = await Operator(db_client).delete_metadata_object(collection, accession_id)

        LOG.info(f"DELETE template with accession ID {accession_id} in schema {collection} was successful.")
        return web.Response(status=204)
