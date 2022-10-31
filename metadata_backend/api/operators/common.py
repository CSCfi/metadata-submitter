"""Functions shared between operators."""
from uuid import uuid4

from ...helpers.logger import LOG


def _generate_accession_id() -> str:
    """Generate random accession id.

    :returns: accession id as str
    """
    sequence = uuid4().hex
    LOG.debug("Generated project ID.")
    return sequence
