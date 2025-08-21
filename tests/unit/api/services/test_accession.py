import os
import re
from unittest.mock import patch

import pytest

from metadata_backend.api.services.accession import generate_bp_accession, generate_default_accession


def test_generate_default_accession_format():
    accession = generate_default_accession()

    pattern = r"^[0-9A-HJKMNP-TV-Z]{26}$"
    assert re.match(pattern, accession), f"Generated accession '{accession}' is not a valid ULID"


def test_generate_bp_accession_format():
    with patch.dict(os.environ, {"BP_CENTER_ID": "TEST"}, clear=True):
        schema_type = "bpimage"
        accession = generate_bp_accession(schema_type)
        pattern = r"^TEST-image-[a-hjkmnp-z2-9]{6}-[a-hjkmnp-z2-9]{6}$"
        assert re.match(pattern, accession), f"Accession {accession} does not match expected format"


def test_generate_bp_accession_invalid_type():
    with patch.dict(os.environ, {"BP_CENTER_ID": "TEST"}, clear=True):
        with pytest.raises(SystemError, match="Invalid BP schema type prefix"):
            generate_bp_accession("invalid")
