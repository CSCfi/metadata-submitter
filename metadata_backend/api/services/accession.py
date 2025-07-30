"""Service for creation accessions."""

import os
from secrets import choice
from string import ascii_lowercase, digits

import ulid

from ..models import SubmissionWorkflow

BP_CENTER_ID_ENV = "BP_CENTER_ID"


def generate_accession(workflow: SubmissionWorkflow, schema_type: str) -> str:
    """Generate accession id.

    :param workflow: the workflow name
    :param schema_type: the schema type
    :returns: The generated accession id
    """

    if workflow == SubmissionWorkflow.BP:
        return generate_bp_accession(schema_type)
    # TODO(improve): implement FEGA accession generation
    return generate_default_accession()


def generate_default_accession() -> str:
    """Generate default accession id.

    The accession id format is uppercased ULID.

    :returns: The generated default accession id
    """
    return str(ulid.new())


def generate_bp_accession(schema_type: str) -> str:
    """
    Generate BigPicture accession id.

    The accession id format is lowercased CENTER-TYPE-c{6}-c{6}.
    - CENTER is defined using the BP_CENTER_ID environmental variable.
    - TYPE is the metadata type.
    - c{N} is N cryptographically secure random alphanumeric characters excluding i, l, o, 0, 1

    :param schema_type: the schema type
    :returns: The generated BigPicture accession id
    """

    center_id = os.getenv(BP_CENTER_ID_ENV)
    if not center_id:
        raise RuntimeError(f"{BP_CENTER_ID_ENV} environment variable is undefined.")

    # https://docs.google.com/document/d/1SSu3wxiCL2-EEWgW77Ob7Kjv9EBmE9zDhUU6DB1gzIM
    allowed_chars = "".join(c for c in ascii_lowercase + digits if c not in "ilo01")
    sequence = "".join(choice(allowed_chars) for _ in range(12))

    if not schema_type.startswith("bp"):
        raise SystemError(f"Invalid BP schema type prefix: {schema_type}")

    return f"{center_id}-{schema_type[2:]}-{sequence[0:6]}-{sequence[6:12]}"
