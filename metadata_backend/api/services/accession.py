"""Service for creation accessions."""

import os
from secrets import choice
from string import ascii_lowercase, digits

import ulid

from ..models import SubmissionWorkflow
from ..processors.xml.configs import (
    BP_FILE_OBJECT_TYPE,
    BP_OBJECT_TYPES,
    BP_SAMPLE_OBJECT_TYPES,
    BP_SUBMISSION_OBJECT_TYPE,
)

BP_CENTER_ID_ENV = "BP_CENTER_ID"


def generate_accession(workflow: SubmissionWorkflow, object_type: str) -> str:
    """Generate accession id.

    :param workflow: the workflow name
    :param object_type: the object type
    :returns: The generated accession id
    """

    if workflow == SubmissionWorkflow.BP:
        return generate_bp_accession(object_type)
    # TODO(improve): accession generation not supported for FEGA
    # raise RuntimeError(f"Accession generation is not supported for workflow: {workflow.value}")
    return generate_default_accession()


def generate_submission_accession(workflow: SubmissionWorkflow) -> str:
    """Generate submission accession id.

    :param workflow: the workflow name
    :returns: The generated accession id
    """

    if workflow == SubmissionWorkflow.BP:
        return generate_bp_accession(BP_SUBMISSION_OBJECT_TYPE)
    # TODO(improve): accession generation not supported for FEGA
    # raise RuntimeError(f"Accession generation is not supported for workflow: {workflow.value}")
    return generate_default_accession()


def generate_file_accession(workflow: SubmissionWorkflow) -> str:
    """Generate file accession id.

    :param workflow: the workflow name
    :returns: The generated accession id
    """

    if workflow == SubmissionWorkflow.BP:
        return generate_bp_accession(BP_FILE_OBJECT_TYPE)
    # TODO(improve): accession generation not supported for FEGA
    # raise RuntimeError(f"Accession generation is not supported for workflow: {workflow.value}")
    return generate_default_accession()


def generate_default_accession() -> str:
    """Generate default accession id.

    The accession id format is uppercased ULID.

    :returns: The generated default accession id
    """
    return str(ulid.new())


def generate_bp_accession(object_type: str) -> str:
    """
    Generate BigPicture accession id.

    The accession id format is lowercased CENTER-TYPE-c{6}-c{6}.
    - CENTER is defined using the BP_CENTER_ID environmental variable.
    - TYPE is the metadata type.
    - c{N} is N cryptographically secure random alphanumeric characters excluding i, l, o, 0, 1

    :param object_type: the object type
    :returns: The generated BigPicture accession id
    """

    # https://docs.google.com/document/d/1SSu3wxiCL2-EEWgW77Ob7Kjv9EBmE9zDhUU6DB1gzIM
    allowed_chars = "".join(c for c in ascii_lowercase + digits if c not in "ilo01")
    sequence = "".join(choice(allowed_chars) for _ in range(12))

    return f"{generate_bp_accession_prefix(object_type)}-{sequence[0:6]}-{sequence[6:12]}"


def generate_bp_accession_prefix(object_type: str) -> str:
    """
    Generate the BigPicture accession prefix.

    The accession prefix format is lowercased CENTER-TYPE.
    - CENTER is defined using the BP_CENTER_ID environmental variable.
    - TYPE is the metadata type.

    :param object_type: the object type
    :returns: The BigPicture accession prefix
    """

    if object_type not in BP_OBJECT_TYPES:
        raise RuntimeError(f"Unsupported object type '{object_type}'.")

    if object_type in BP_SAMPLE_OBJECT_TYPES:
        accession_type = "sample"
    else:
        accession_type = object_type

    center_id = os.getenv(BP_CENTER_ID_ENV)
    if not center_id:
        raise RuntimeError(f"{BP_CENTER_ID_ENV} environment variable is undefined.")

    return f"{center_id}-{accession_type}"
