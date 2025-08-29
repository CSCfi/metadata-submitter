"""Services for JSON and XML metadata objects."""

from typing import Any

from ...conf.conf import BP_REMS_SCHEMA_TYPE, get_workflow
from ...database.postgres.services.object import ObjectService
from ...database.postgres.services.submission import SubmissionService
from ...helpers.parser import XMLToJSONParser
from ...helpers.validator import JSONValidator
from ..exceptions import SystemException, UserException
from ..models import Rems, SubmissionWorkflow
from .accession import generate_accession


class JsonObjectService:
    """Service for JSON metadata objects."""

    def __init__(self, submission_service: SubmissionService, object_service: ObjectService) -> None:
        """Service for JSON metadata objects.

        :param submission_service: The Postgres submission service.
        :param object_service: The Postgres object service.
        """

        self._submission_service = submission_service
        self._object_service = object_service

    async def add_metadata_objects(
        self,
        submission_id: str,
        schema: str,
        data: dict[str, Any] | list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Add one or more metadata JSON objects to database.

        Adds necessary additional information to the metadata document.

        :param submission_id: The submission id.
        :param schema: The metadata schema.
        :param data: The metadata document.
        :returns: Formatted metadata JSON documents.
        """

        if isinstance(data, dict):
            documents = [data]
        elif isinstance(data, list):
            documents = data
        else:
            raise SystemException("Invalid metadata object format.")

        # Validate documents
        for document in documents:
            JSONValidator(document, schema).validate()

        workflow = await self._submission_service.get_workflow(submission_id)
        workflow_config = get_workflow(workflow.value)

        for document in documents:
            if schema == BP_REMS_SCHEMA_TYPE:
                # BP REMS JSON is not stored.
                await self._process_bp_rems_metadata_object(submission_id, document)
            else:
                is_single_instance = schema in workflow_config.single_instance_schemas
                if is_single_instance:
                    # ensure only one object with the same schema exists in the submission
                    if await self._object_service.count_objects(submission_id, schema) > 0:
                        raise UserException(f"Only one metadata object of type '{schema}' is allowed in a submission.")

                # Create accession.
                accession_id = generate_accession(workflow, schema)

                document["accessionId"] = accession_id
                await self._object_service.add_object(submission_id, schema, object_id=accession_id, document=document)

        return documents

    async def update_metadata_object(
        self,
        submission_id: str,
        accession_id: str,
        schema: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update metadata JSON documents in database.

        Preserves necessary additional information to metadata object.

        :param submission_id: The submission id.
        :param accession_id: The accession id.
        :param schema: The metadata schema.
        :param data: The metadata document.
        :returns: Formatted metadata JSON documents.
        """

        if not isinstance(data, dict):
            raise SystemException("Invalid metadata object format.")

        # TODO(improve): support metadata object update by name

        if schema == BP_REMS_SCHEMA_TYPE:
            # BP REMS JSON is not stored.
            await self._process_bp_rems_metadata_object(submission_id, data)

        # Validate document.
        JSONValidator(data, schema).validate()

        data["accessionId"] = accession_id

        await self._object_service.check_object(accession_id, submission_id=submission_id)

        if (await self._object_service.get_schema(accession_id)) != schema:
            raise UserException("Changing the type of a metadata object is not supported.")

        await self._object_service.update_document(accession_id, data)
        return data

    async def _process_bp_rems_metadata_object(self, submission_id: str, document: dict[str, Any]) -> None:
        """Process BP REMS metadata object.

        :param submission_id: ID of the submission
        :param document: BP REMS JSON document
        """
        await self._submission_service.update_rems(
            submission_id,
            Rems(
                workflow_id=int(document["workflowId"].strip()), organization_id=document["organisationId"], licenses=[]
            ),
        )

    @staticmethod
    def get_metadata_title_and_description(schema: str, data: dict[str, Any]) -> tuple[str, str]:
        """Get the metadata title and description. Raises an error if they don't exist.

        :param schema: The metadata schema.
        :param data: The metadata document.
        :returns: The metadata title and description.
        """

        def _field(keys: list[str]) -> str:
            _current = data
            for _key in keys:
                if isinstance(_current, dict) and _key in _current:
                    _current = _current[_key]
                else:
                    raise UserException(f"Missing required metadata field: {'.'.join(keys)}")

            if not isinstance(_current, str):
                raise UserException(f"Expected string for required metadata field: {'.'.join(keys)}")

            return _current

        if schema in ("dataset", "bpdataset"):
            return _field(["title"]), _field(["description"])

        if schema == "study":
            return _field(["descriptor", "studyTitle"]), _field(["descriptor", "studyAbstract"])

        raise SystemException(f"Unsupported metadata type: {schema}")


class XmlObjectService:
    """Service for XML metadata objects."""

    def __init__(
        self,
        submission_service: SubmissionService,
        object_service: ObjectService,
        json_object_service: JsonObjectService,
    ) -> None:
        """Service for XML metadata objects.

        :param submission_service: The Postgres submission service.
        :param object_service: The Postgres object service.
        """

        self._xml_parser = XMLToJSONParser()
        self._submission_service = submission_service
        self._object_service = object_service
        self._json_object_service = json_object_service

    async def add_metadata_objects(
        self,
        submission_id: str,
        schema: str,
        data: str,
    ) -> list[dict[str, Any]]:
        """Add one or more XML metadata documents to database. Creates an equivalent XML document.

        Adds necessary additional information to the metadata document.

        :param submission_id: The submission id.
        :param schema: The metadata schema.
        :param data: The metadata document.
        :returns: Formatted metadata JSON documents.
        """

        if not isinstance(data, str):
            raise SystemException("Invalid metadata object format.")

        workflow = await self._submission_service.get_workflow(submission_id)
        documents, xml_documents = self._parse_xml_documents(schema, data)

        added_documents = []
        for i, document in enumerate(documents):
            added_document = (await self._json_object_service.add_metadata_objects(submission_id, schema, document))[0]

            if schema == BP_REMS_SCHEMA_TYPE:
                # BP REMS XML is not stored.
                continue

            accession_id = added_document["accessionId"]
            added_documents.append(added_document)

            # TODO(improve): generalize accession injection into XML
            if workflow == SubmissionWorkflow.BP:
                xml_documents[i] = self._xml_parser.assign_accession_to_bp_xml(schema, xml_documents[i], accession_id)

            await self._object_service.update_xml_document(accession_id, xml_documents[i])

        return added_documents

    async def update_metadata_object(
        self,
        submission_id: str,
        accession_id: str,
        schema: str,
        data: str,
    ) -> dict[str, Any]:
        """Update XML metadata document in database. Updates an equivalent JSON document.

        Preserves necessary additional information to metadata object.

        :param submission_id: The submission id.
        :param accession_id: The accession id.
        :param schema: The metadata schema.
        :param data: The metadata documents.
        :returns: Formatted metadata JSON documents.
        """

        if not isinstance(data, str):
            raise SystemException("Invalid metadata object format.")

        # TODO(improve): support metadata object update by name

        workflow = await self._submission_service.get_workflow(submission_id)
        document, xml_document = self._parse_xml_document(schema, data)

        if schema == BP_REMS_SCHEMA_TYPE:
            # BP REMS XML is not stored.
            return document

        # TODO(improve): generalize accession extraction from XML
        if workflow == SubmissionWorkflow.BP:
            accession_ids_in_xml = self._xml_parser.get_accessions_from_bp_xml(schema, xml_document)
            if accession_ids_in_xml:
                accession_id_in_xml = accession_ids_in_xml[0]
                if not accession_id_in_xml == accession_id:
                    raise UserException(
                        f"Accession in XML {accession_id_in_xml} doesn't match the id in request: {accession_id}."
                    )

        # Update JSON document.
        added_document = await self._json_object_service.update_metadata_object(
            submission_id, accession_id, schema, document
        )

        # Update XML document.
        accession_id = added_document["accessionId"]
        # TODO(improve): generalize accession injection into XML
        if workflow == SubmissionWorkflow.BP:
            xml_document = self._xml_parser.assign_accession_to_bp_xml(schema, xml_document, accession_id)

        await self._object_service.update_xml_document(accession_id, xml_document)
        return added_document

    def _parse_xml_documents(self, schema: str, data: str) -> tuple[list[dict[str, Any]], list[str]]:
        documents, xml_documents = self._xml_parser.parse(schema, data)
        return documents if isinstance(documents, list) else [documents], xml_documents

    def _parse_xml_document(self, schema: str, data: str) -> tuple[dict[str, Any], str]:
        documents, xml_documents = self._xml_parser.parse(schema, data)
        if not isinstance(documents, dict) or len(xml_documents) > 1:
            raise UserException("Only one XML metadata object can be updated at a time.")
        return documents, xml_documents[0]
