"""Bigpicture metadata version of a stored submission."""

from ...exceptions import SystemException
from ...models.submission import Submission
from ...processors.xml.bigpicture import BP_XML_OBJECT_CONFIGS, BigpictureVersion
from ...processors.xml.models import XmlObjectConfig


def get_bp_version_from_submission(submission: Submission) -> BigpictureVersion:
    """
    Return the Bigpicture metadata version of a stored submission.

    The version is stored when the submission is created.

    :param submission: The submission.
    :returns: The Bigpicture metadata version.
    :raises SystemException: If the submission has no metadata version.
    """
    if submission.metadataVersion is None:
        raise SystemException(f"Bigpicture submission '{submission.submissionId}' has no metadata version.")
    return BigpictureVersion(submission.metadataVersion)


def get_bp_xml_object_config(submission: Submission) -> XmlObjectConfig:
    """
    Return the XML processing configuration of a stored Bigpicture submission.

    :param submission: The submission.
    :returns: The XML processing configuration of the submission's Bigpicture metadata version.
    """
    return BP_XML_OBJECT_CONFIGS[get_bp_version_from_submission(submission)]
