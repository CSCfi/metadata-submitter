import json
import uuid
from pathlib import Path

from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from metadata_backend.services.metax_service import MetaxServiceHandler

SD_SUBMISSION = Path(__file__).parent.parent.parent / "test_files" / "submission" / "submission.json"


async def test_publish_csd_pid(client, secret_env):
    """Test publish DataCite metadata using test service."""

    from metadata_backend.services.pid_service import PIDServiceHandler

    service = PIDServiceHandler(MetaxServiceHandler())

    # Submission with DataCite metadata.
    project_id = f"test_{uuid.uuid4()}"
    submission_dict = json.loads(SD_SUBMISSION.read_text())
    submission_dict["projectId"] = project_id
    submission_dict["workflow"] = SubmissionWorkflow.SD.value
    submission = Submission(**submission_dict)

    # Register draft DOI.
    doi = await service.create_draft_doi()

    # Registration.
    submission_id = f"test_{uuid.uuid4()}"
    title = f"test_{uuid.uuid4()}"
    description = f"test_{uuid.uuid4()}"
    discovery_url = f"https://test.csc.fi/{uuid.uuid4()}"  # Domain registered in DataCite.

    registration = Registration(submissionId=submission_id, doi=doi, title=title, description=description)

    # Add DataCite metadata and publish DOI.
    await service.publish(
        registration, submission.metadata, discovery_url, require_field_of_science=False, publish=False
    )

    # Get published DataCite metadata.
    saved_data = await service.get(doi)

    assert saved_data == discovery_url
