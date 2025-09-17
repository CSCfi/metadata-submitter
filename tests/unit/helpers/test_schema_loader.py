"""Tests for helper classes."""

import pytest

from metadata_backend.helpers.schema_loader import (
    SchemaLoader,
    JSONSchemaLoader,
    XMLSchemaLoader,
    SchemaFileNotFoundException)


def test_schema_loader_error():
    loader = SchemaLoader(".invalid")
    with pytest.raises(SchemaFileNotFoundException):
        loader.get_schema_file("invalid")


def test_json_schema_loader_submission_json():
    loader = JSONSchemaLoader()
    file = loader.get_schema_file("submission")
    assert file.name == "submission.json"
    assert loader.get_schema("submission") is not None


def test_xml_schema_loader_submission_xml():
    loader = XMLSchemaLoader()
    file = loader.get_schema_file("BP.bpdataset")
    assert file.name == "BP.bpdataset.xsd"
