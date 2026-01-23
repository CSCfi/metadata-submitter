import json
import uuid

from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from tests.integration.conf import SD_SUBMISSION


async def test_datacite_service(client, secret_env):
    """Test publish DataCite metadata using test service."""

    from metadata_backend.services.datacite_service import DataciteServiceHandler
    from metadata_backend.services.metax_service import MetaxServiceHandler

    service = DataciteServiceHandler(MetaxServiceHandler())

    # Submission with DataCite metadata.
    project_id = f"test_{uuid.uuid4()}"
    submission_dict = json.loads(SD_SUBMISSION.read_text())
    submission_dict["projectId"] = project_id
    submission_dict["workflow"] = SubmissionWorkflow.SD.value
    submission = Submission(**submission_dict)

    # Register draft DOI.
    doi = await service.create_draft_doi()

    try:
        # Registration.
        submission_id = f"test_{uuid.uuid4()}"
        title = f"test_{uuid.uuid4()}"
        description = f"test_{uuid.uuid4()}"
        discovery_url = f"https://test.csc.fi/{uuid.uuid4()}"  # Domain registered in DataCite.

        registration = Registration(submissionId=submission_id, doi=doi, title=title, description=description)

        # Add DataCite metadata and publish DOI.
        data = await service.publish(
            registration, submission.metadata, discovery_url, require_field_of_science=False, publish=False
        )

        # Get published DataCite metadata.
        saved_data = await service.get(doi)

        assert saved_data["data"]["id"] == doi
        assert data["data"]["type"] == saved_data["data"]["type"] == "dois"

        # Delete extra keys before comparison.

        for k in list(saved_data["data"]["attributes"].keys()):
            if k not in data["data"]["attributes"]:
                del saved_data["data"]["attributes"][k]
        for k in ("bibtex", "citeproc", "ris", "schemaOrg"):
            saved_data["data"]["attributes"]["types"].pop(k, None)

        # Delete empty keys before comparison.

        def delete_empty_key(obj):
            if isinstance(obj, dict):
                for k in list(obj.keys()):
                    delete_empty_key(obj[k])
                    if not obj[k]:
                        del obj[k]
            elif isinstance(obj, list):
                for item in obj:
                    delete_empty_key(item)

        delete_empty_key(saved_data["data"]["attributes"])

        assert data["data"]["attributes"] == saved_data["data"]["attributes"]

    finally:
        await service.delete(doi)
