"""Handle HTTP methods for server."""
from collections import Counter
from typing import Dict, List

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from multidict import MultiDict, MultiDictProxy
from xmlschema import XMLSchemaException

from ...helpers.logger import LOG
from ...helpers.parser import XMLToJSONParser
from ...helpers.schema_loader import SchemaNotFoundException, XMLSchemaLoader
from ...helpers.validator import XMLValidator
from ..operators import Operator, XMLOperator
from .common import multipart_content


class SubmissionAPIHandler:
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
        submission_json = XMLToJSONParser().parse("submission", submission_xml)

        # Check what actions should be performed, collect them to dictionary
        actions: Dict[str, List] = {}
        for action_set in submission_json["actions"]["action"]:
            for action, attr in action_set.items():
                if not attr:
                    reason = f"""You also need to provide necessary
                                  information for submission action.
                                  Now {action} was provided without any
                                  extra information."""
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                LOG.debug(f"submission has action {action}")
                if attr["schema"] in actions:
                    set = []
                    set.append(actions[attr["schema"]])
                    set.append(action)
                    actions[attr["schema"]] = set
                else:
                    actions[attr["schema"]] = action

        # Go through parsed files and do the actual action
        results: List[Dict] = []
        db_client = req.app["db_client"]
        for file in files:
            content_xml = file[0]
            schema_type = file[1]
            if schema_type == "submission":
                LOG.debug("file has schema of submission type, continuing ...")
                continue  # No need to use submission xml
            action = actions[schema_type]
            if isinstance(action, List):
                for item in action:
                    result = await self._execute_action(schema_type, content_xml, db_client, item)
                    results.append(result)
            else:
                result = await self._execute_action(schema_type, content_xml, db_client, action)
                results.append(result)

        body = ujson.dumps(results, escape_forward_slashes=False)
        LOG.info(f"Processed a submission of {len(results)} actions.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def validate(self, req: Request) -> Response:
        """Handle validating an XML file sent to endpoint.

        :param req: Multipart POST request with submission.xml and files
        :returns: JSON response indicating if validation was successful or not
        """
        files, _ = await multipart_content(req, extract_one=True, expect_xml=True)
        xml_content, schema_type = files[0]
        validator = await self._perform_validation(schema_type, xml_content)
        return web.Response(body=validator.resp_body, content_type="application/json")

    async def _perform_validation(self, schema_type: str, xml_content: str) -> XMLValidator:
        """Validate an xml.

        :param schema_type: Schema type of the object to validate.
        :param xml_content: Metadata object
        :raises: HTTPBadRequest if schema load fails
        :returns: JSON response indicating if validation was successful or not
        """
        try:
            schema = XMLSchemaLoader().get_schema(schema_type)
            LOG.info(f"{schema_type} schema loaded.")
            return XMLValidator(schema, xml_content)

        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} ({schema_type})"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def _execute_action(self, schema: str, content: str, db_client: AsyncIOMotorClient, action: str) -> Dict:
        """Complete the command in the action set of the submission file.

        Only "add/modify/validate" actions are supported.

        :param schema: Schema type of the object in question
        :param content: Metadata object referred to in submission
        :param db_client: Database client for database operations
        :param action: Type of action to be done
        :raises: HTTPBadRequest if an incorrect or non-supported action is called
        :returns: Dict containing specific action that was completed
        """
        if action == "add":
            result = {
                "accessionId": await XMLOperator(db_client).create_metadata_object(schema, content),
                "schema": schema,
            }
            LOG.debug(f"added some content in {schema} ...")
            return result

        elif action == "modify":
            data_as_json = XMLToJSONParser().parse(schema, content)
            if "accessionId" in data_as_json:
                accession_id = data_as_json["accessionId"]
            else:
                alias = data_as_json["alias"]
                query = MultiDictProxy(MultiDict([("alias", alias)]))
                data, _, _, _ = await Operator(db_client).query_metadata_database(schema, query, 1, 1, [])
                if len(data) > 1:
                    reason = "Alias in provided XML file corresponds with more than one existing metadata object."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                accession_id = data[0]["accessionId"]
            data_as_json.pop("accessionId", None)
            result = {
                "accessionId": await Operator(db_client).update_metadata_object(schema, accession_id, data_as_json),
                "schema": schema,
            }
            LOG.debug(f"modified some content in {schema} ...")
            return result

        elif action == "validate":
            validator = await self._perform_validation(schema, content)
            return ujson.loads(validator.resp_body)

        else:
            reason = f"Action {action} in XML is not supported."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
