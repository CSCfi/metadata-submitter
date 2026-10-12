"""Tests for the Bigpicture metadata version of a stored submission."""

import pytest

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import (
    BP_XML_OBJECT_CONFIG_2,
    BP_XML_OBJECT_CONFIG_3,
    BigpictureVersion,
)
from metadata_backend.api.services.submission.bigpicture_version import (
    get_bp_version_from_submission,
    get_bp_xml_object_config,
)


def _submission(metadata_version: str | None) -> Submission:
    return Submission(
        projectId="project",
        submissionId="submission",
        name="name",
        title="title",
        description="description",
        workflow=SubmissionWorkflow.BP,
        metadataVersion=metadata_version,
    )


@pytest.mark.parametrize(
    ("metadata_version", "version", "config"),
    [("2.0", BigpictureVersion.V2_0, BP_XML_OBJECT_CONFIG_2), ("3.0", BigpictureVersion.V3_0, BP_XML_OBJECT_CONFIG_3)],
)
def test_get_bp_version_from_submission(metadata_version, version, config):
    assert get_bp_version_from_submission(_submission(metadata_version)) == version
    assert get_bp_xml_object_config(_submission(metadata_version)) is config


def test_get_bp_version_from_submission_without_version():
    with pytest.raises(SystemException, match="Bigpicture submission 'submission' has no metadata version."):
        get_bp_version_from_submission(_submission(None))
