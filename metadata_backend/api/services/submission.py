"""Services for metadata object submission."""

from ...database.postgres.repository import SessionFactory, transaction
from ...database.postgres.services.object import ObjectService
from ...database.postgres.services.submission import SubmissionService
from ..exceptions import SystemException, UserErrors, UserException
from ..models import Rems, Submission, SubmissionWorkflow
from ..processors.xml.configs import (
    BP_DATASET_PATH,
    BP_DATASET_SCHEMA,
    BP_FULL_SUBMISSION_XML_OBJECT_CONFIG,
    BP_REMS_PATH,
    BP_REMS_SCHEMA,
)
from ..processors.xml.processors import XmlStringDocumentsProcessor
from .accession import generate_accession, generate_submission_accession
from .project import ProjectService


class ObjectSubmissionService:
    """Service for processing submission with metadata objects."""

    def __init__(
        self,
        project_service: ProjectService,
        submission_service: SubmissionService,
        object_service: ObjectService,
        session_factory: SessionFactory,
    ) -> None:
        """
        Service for processing submission with metadata objects.

        :param project_service: The Postgres project service.
        :param submission_service: The Postgres submission service.
        :param object_service: The Postgres object service.
        :param session_factory: The SQLAlchemy session factory.
        """

        self._project_service = project_service
        self._submission_service = submission_service
        self._object_service = object_service
        self._session_factory = session_factory

    async def submit(
        self, user_id: str, project_id: str, workflow: SubmissionWorkflow, documents: list[str]
    ) -> Submission:
        """
        Process a submission with metadata objects.

        :param user_id: The user id.
        :param project_id: The project id.
        :param workflow: The submission workflow.
        :param documents: The metadata object documents.
        :returns: The submission document.
        :raises UserErrors: If case of any user errors.
        """

        errors: list[str] = []

        try:
            # Check that user is affiliated with the project.
            await self._project_service.verify_user_project(user_id, project_id)

            # Get the metadata object processor.
            if workflow == SubmissionWorkflow.BP:
                # A full non-incremental BP XML submission.
                processor = XmlStringDocumentsProcessor(BP_FULL_SUBMISSION_XML_OBJECT_CONFIG, documents)
            else:
                raise UserException(f"Unsupported workflow: {workflow.value}")

            # Check that no metadata objects are accessioned.
            object_identifiers = processor.get_xml_object_identifiers()
            for identifier in object_identifiers:
                if identifier.id is not None:
                    errors.append(
                        f"Update of previously submitted '{identifier.schema_type}' metadata object '{identifier.id}'"
                        "is not supported"
                    )

            # Check that no metadata object references are accessioned.
            for identifier in processor.get_xml_object_references():
                if identifier.id is not None:
                    errors.append(
                        f"Reference to previously submitted '{identifier.schema_type}' metadata object "
                        f"'{identifier.id}' is not supported"
                    )

            if errors:
                raise UserErrors(errors)

            # Assign submission accession.
            if workflow == SubmissionWorkflow.BP:
                submission_id = generate_submission_accession(workflow)
            else:
                raise UserException(f"Unsupported workflow: {workflow.value}")

            # Assign metadata object accessions.
            for identifier in object_identifiers:
                identifier.id = generate_accession(workflow, identifier.object_type)
                processor.set_xml_object_id(identifier)

            # Check that all metadata object references have accessions.
            for identifier in processor.get_xml_references_without_ids():
                errors.append(f"Unknown '{identifier.schema_type}' metadata object '{identifier.id}' reference")

            # Create and save submission and metadata objects within one transaction.
            async with transaction(self._session_factory):

                # The BP XML processor guarantees that we have one dataset and rems metadata object.
                dataset_identifiers = processor.get_xml_object_identifiers(BP_DATASET_SCHEMA)
                rems_identifiers = processor.get_xml_object_identifiers(BP_REMS_SCHEMA)

                # Get dataset and rems metadata object processor.
                dataset_processor = processor.get_xml_object_processor(
                    BP_DATASET_SCHEMA, BP_DATASET_PATH, dataset_identifiers[0].name
                )
                rems_processor = processor.get_xml_object_processor(
                    BP_REMS_SCHEMA, BP_REMS_PATH, rems_identifiers[0].name
                )

                # Get submission name.
                name = dataset_processor.get_xml_node_value("./SHORT_NAME")

                # Get REMS.
                workflow_id = rems_processor.get_xml_node_value("./WORKFLOW_ID")
                organization_id = rems_processor.get_xml_node_value("./ORGANISATION_ID")

                submission = Submission(
                    project_id=project_id,
                    submission_id=submission_id,
                    name=name,
                    title=dataset_processor.get_xml_object_title(),
                    description=dataset_processor.get_xml_object_description(),
                    workflow=workflow.value,
                    rems=Rems(
                        workflow_id=workflow_id,
                        organization_id=organization_id,
                        # TODO(improve): assign license (CSC uses the license ID 17)
                        licenses=[],
                    ),
                    # TODO(improve): datacite=
                )

                # Save submission.
                saved_submission_id = await self._submission_service.add_submission(
                    submission.to_json_dict(), submission_id=submission_id
                )
                if saved_submission_id != submission_id:
                    raise SystemException("Failed to save generated submission id")

                # Return saved submission.
                submission = Submission.model_validate(
                    await self._submission_service.get_submission_by_id(submission_id)
                )

                # Save metadata objects.
                for identifier in processor.get_xml_object_identifiers():
                    object_processor = processor.get_xml_object_processor(
                        identifier.schema_type, identifier.root_path, identifier.name
                    )

                    saved_object_id = await self._object_service.add_object(
                        submission_id,
                        identifier.object_type,
                        workflow,
                        name=identifier.name,
                        object_id=identifier.id,
                        title=object_processor.get_xml_object_title(),
                        description=object_processor.get_xml_object_description(),
                        xml_document=object_processor.write_xml(object_processor.xml),
                    )

                    if saved_object_id != identifier.id:
                        raise SystemException("Failed to save generated object id")

        except Exception as e:
            errors.append(str(e))
            raise UserErrors(errors) from e

        return submission
