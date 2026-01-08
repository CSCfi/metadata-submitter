import os
import re
from unittest.mock import patch

import pytest

from metadata_backend.api.processors.xml.bigpicture import (
    BP_ANNOTATION_OBJECT_TYPE,
    BP_DATASET_OBJECT_TYPE,
    BP_IMAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVER_OBJECT_TYPE,
    BP_ORGANISATION_OBJECT_TYPE,
    BP_POLICY_OBJECT_TYPE,
    BP_REMS_OBJECT_TYPE,
    BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE,
    BP_SAMPLE_BLOCK_OBJECT_TYPE,
    BP_SAMPLE_CASE_OBJECT_TYPE,
    BP_SAMPLE_SLIDE_OBJECT_TYPE,
    BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
    BP_STAINING_OBJECT_TYPE,
)
from metadata_backend.api.services.accession import generate_bp_accession, generate_default_accession
from metadata_backend.conf.bigpicture import bp_config


def test_generate_default_accession_format():
    accession = generate_default_accession()

    pattern = r"^[0-9A-HJKMNP-TV-Z]{26}$"
    assert re.match(pattern, accession), f"Generated accession '{accession}' is not a valid ULID"


def assert_bp_accession_format(center_id: str, accession_type: str, object_type: str):
    accession = generate_bp_accession(object_type)
    pattern = rf"^{center_id}-{accession_type}-[a-hjkmnp-z2-9]{{6}}-[a-hjkmnp-z2-9]{{6}}$"
    assert re.match(pattern, accession), f"Accession '{accession}' does not match the expected pattern '{pattern}'"


def test_generate_bp_accession_format():
    center_id = bp_config().BP_CENTER_ID
    assert_bp_accession_format(center_id, "annotation", BP_ANNOTATION_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "dataset", BP_DATASET_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "image", BP_IMAGE_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "landingpage", BP_LANDING_PAGE_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "observation", BP_OBSERVATION_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "observer", BP_OBSERVER_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "organisation", BP_ORGANISATION_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "policy", BP_POLICY_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "rems", BP_REMS_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "sample", BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "sample", BP_SAMPLE_SLIDE_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "sample", BP_SAMPLE_SPECIMEN_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "sample", BP_SAMPLE_BLOCK_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "sample", BP_SAMPLE_CASE_OBJECT_TYPE)
    assert_bp_accession_format(center_id, "staining", BP_STAINING_OBJECT_TYPE)


def test_generate_bp_accession_invalid_type():
    with patch.dict(os.environ, {"BP_CENTER_ID": "TEST"}, clear=True):
        with pytest.raises(RuntimeError, match="Unsupported object type 'invalid'."):
            generate_bp_accession("invalid")
