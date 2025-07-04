"""Handle HTTP methods for server."""

from collections import Counter
from typing import Any

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from xmlschema import XMLSchemaException

from ...conf.conf import API_PREFIX
from ...helpers.logger import LOG
from ...helpers.parser import XMLToJSONParser
from ...helpers.schema_loader import SchemaNotFoundException, XMLSchemaLoader
from ...helpers.validator import XMLValidator
from ..operators.object import ObjectOperator
from ..operators.object_xml import XMLObjectOperator
from ..operators.submission import SubmissionOperator
from .common import multipart_content
from .object import ObjectAPIHandler


class XMLSubmissionAPIHandler(ObjectAPIHandler):
    """Handler for non-rest API methods."""

    async def submit(self, req: Request) -> Response:
        """Handle submission.xml containing submissions to server.

        First submission info is parsed and then for every action in submission
        (add/modify/validate) corresponding operation is performed.
        Finally submission info itself is added.

        :param req: Multipart POST request with submission.xml and files
        :raises: HTTPBadRequest if request is missing some parameters or cannot be processed
        :returns: XML-based receipt from submission
        """
        files, _ = await multipart_content(req, expect_xml=True)
        schema_types = Counter(file[1] for file in files)
        if "submission" not in schema_types:
            reason = "There must be a submission.xml file in submission."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        if schema_types["submission"] > 1:
            reason = "You should submit only one submission.xml file."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        submission_xml = files[0][0]
        submission_json, _ = XMLToJSONParser().parse("submission", submission_xml)

        workflow_name = req.match_info.get("workflow") or submission_json.get("workflow")
        if not workflow_name:
            reason = "Submission must have a workflow."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        workflow = self.get_workflow(workflow_name)

        # Check what actions should be performed, collect them to dictionary
        actions: dict[str, list[Any]] = {}
        for action_set in submission_json["actions"]["action"]:
            for action, attr in action_set.items():
                if not attr:
                    reason = f"""You also need to provide necessary
                                  information for submission action.
                                  Now {action} was provided without any
                                  extra information."""
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                LOG.debug("Submission has action %r", action)
                if attr["schema"] in actions:
                    _set = []
                    _set.append(actions[attr["schema"]])
                    _set.append(action)
                    actions[attr["schema"]] = _set
                else:
                    actions[attr["schema"]] = action

        # Go through parsed files and do the actual action
        results: list[dict[str, Any]] = []
        for file in files:
            content_xml = file[0]
            schema_type = file[1]
            filename = file[2]
            if schema_type == "submission":
                LOG.debug("file has schema of submission type, continuing ...")
                continue  # No need to use submission xml
            if schema_type not in workflow.schemas:
                reason = f"Submission of type '{workflow.name}' cannot have '{schema_type}' objects."
                LOG.info(reason)
                raise web.HTTPBadRequest(reason=reason)
            action = actions[schema_type]
            if isinstance(action, list):
                for item in action:
                    result = await self._execute_action(req, schema_type, content_xml, item, filename)
                    results.append(result)
            else:
                result = await self._execute_action(req, schema_type, content_xml, action, filename)
                results.append(result)

        body = ujson.dumps(results, escape_forward_slashes=False)
        LOG.info("Processed a submission of %d actions.", len(results))
        return web.Response(body=body, status=200, content_type="application/json")

    async def validate(self, req: Request) -> Response:
        """Handle validating an XML file sent to endpoint.

        :param req: Multipart POST request with submission.xml and files
        :returns: JSON response indicating if validation was successful or not
        """
        files, _ = await multipart_content(req, extract_one=True, expect_xml=True)
        xml_content, schema_type, _ = files[0]
        validator = await self._perform_validation(schema_type, xml_content)
        return web.Response(
            status=ujson.loads(validator.resp_body)["status"],
            body=validator.resp_body,
            content_type="application/json",
        )

    async def _perform_validation(self, schema_type: str, xml_content: str) -> XMLValidator:
        """Validate an xml.

        :param schema_type: Schema type of the object to validate.
        :param xml_content: Metadata object
        :raises: HTTPBadRequest if schema load fails
        :returns: JSON response indicating if validation was successful or not
        """
        try:
            schema = XMLSchemaLoader().get_schema(schema_type)
            LOG.info("%r XML schema loaded for XML validation.", schema_type)
            return XMLValidator(schema, xml_content)

        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} ({schema_type})"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def _execute_action(
        self, req: Request, schema: str, content: str, action: str, filename: str
    ) -> dict[str, Any]:
        """Complete the command in the action set of the submission file.

        Only "add/modify/validate" actions are supported.

        :param req: Multipart POST request
        :param schema: Schema type of the object in question
        :param content: Metadata object referred to in submission
        :param action: Type of action to be done
        :param filename: Name of file being processed
        :raises: HTTPBadRequest if an incorrect or non-supported action is called
        :returns: Dict containing specific action that was completed
        """
        if action == "add":
            return await self._execute_action_add(req, schema, content, filename)

        if action == "modify":
            return await self._execute_action_modify(req, schema, content, filename)

        if action == "validate":
            validator = await self._perform_validation(schema, content)
            completed_action: dict[str, Any] = ujson.loads(validator.resp_body)
            return completed_action

        reason = f"Action {action} in XML is not supported."
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)

    async def _execute_action_add(self, req: Request, schema: str, content: str, filename: str) -> dict[str, Any]:
        """Complete the add action.

        :param req: Multipart POST request
        :param schema: Schema type of the object in question
        :param content: Metadata object referred to in submission
        :param filename: Name of file being processed
        :raises: HTTPBadRequest if an incorrect or non-supported action is called
        :returns: Dict containing specific action that was completed
        """
        db_client = req.app["db_client"]
        submission_op = SubmissionOperator(db_client)

        submission_id = req.query.get("submission", "")
        if not submission_id:
            reason = "Submission is required query parameter. Please provide submission id where object is added to."
            raise web.HTTPBadRequest(reason=reason)

        # we need to check if there is already a study in a submission
        # we only allow one study per submission
        # this is not enough to catch duplicate entries if updates happen in parallel
        # that is why we check in db_service.update_study
        if not req.path.startswith(f"{API_PREFIX}/drafts") and schema == "study":
            _ids = await submission_op.get_collection_objects(submission_id, schema)
            if len(_ids) == 1:
                reason = "Only one study is allowed per submission."
                raise web.HTTPBadRequest(reason=reason)

        json_list: list[dict[str, Any]] = await XMLObjectOperator(db_client).create_metadata_object(
            schema, content
        )  # type: ignore[assignment]
        json_data = json_list[0]
        result = {
            "accessionId": json_data["accessionId"],
            "schema": schema,
        }
        LOG.debug("Added some content in collection: %r ...", schema)

        # Gathering data for object to be added to submission
        patch = self._prepare_submission_patch_new_object(schema, [(json_data, filename)], "xml")
        await submission_op.update_submission(submission_id, patch)

        return result

    async def _execute_action_modify(self, req: Request, schema: str, content: str, filename: str) -> dict[str, Any]:
        """Complete the modify action.

        :param req: Multipart POST request
        :param schema: Schema type of the object in question
        :param content: Metadata object referred to in submission
        :param filename: Name of file being processed
        :raises: HTTPBadRequest if an incorrect or non-supported action is called
        :returns: Dict containing specific action that was completed
        """
        db_client = req.app["db_client"]
        submission_op = SubmissionOperator(db_client)
        operator = ObjectOperator(db_client)
        data_as_json, _ = XMLToJSONParser().parse(schema, content)
        if "accessionId" in data_as_json:
            accession_id = data_as_json["accessionId"]
        else:
            alias = data_as_json["alias"]
            objects = await operator.query_by_alias(schema, alias)
            if len(objects) == 0:
                reason = f"No metadata object found for alias {alias}."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            if len(objects) > 1:
                reason = f"More than one metadata object found for alias {alias}."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            accession_id = objects[0]["accessionId"]
        data_as_json.pop("accessionId", None)
        result = {
            # should here be replace_metadata_object ??
            "accessionId": await operator.update_metadata_object(schema, accession_id, data_as_json),
            "schema": schema,
        }

        submission_id, published = await submission_op.check_object_in_submission(schema, result["accessionId"])
        if published:
            reason = "Published objects cannot be updated."
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        # If there's changed title it will be updated to submission
        try:
            _ = data_as_json["descriptor"]["studyTitle"] if schema == "study" else data_as_json["title"]
            # should we overwrite filename as it is the name of file with partial update data
            patch = self._prepare_submission_patch_update_object(schema, data_as_json, filename)
            await submission_op.update_submission(submission_id, patch)
        except (TypeError, KeyError) as error:
            LOG.exception(error)

        LOG.debug("Modified some content in collection: %r ...", schema)
        return result
