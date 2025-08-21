"""Test Metax metadata mapping methods."""

import json
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock

from metadata_backend.services.metax_mapper import MetaDataMapper, SubjectNotFoundException


class MetaDataMapperTestCase(IsolatedAsyncioTestCase):
    """MetaDataMapper Test Cases."""

    TESTFILES_ROOT = Path(__file__).parent.parent / "test_files"

    def setUp(self):
        """Configure variables for tests."""
        self.client = MagicMock()
        self.bytes = 1024
        doi_file = self.TESTFILES_ROOT / "doi" / "test_doi.json"
        self.doi_info = json.loads(doi_file.read_text())

    async def test_map_metadata(self):
        """Test that Metax metadata receives new data from DOI of a submission."""

        mapper = MetaDataMapper({}, self.doi_info, self.bytes)
        research_dataset = await mapper.map_metadata()
        new_keys = [
            "creator",
            "keyword",
            "contributor",
            "temporal",
            "spatial",
            "other_identifier",
            "language",
            "field_of_science",
            "total_remote_resources_byte_size",
        ]
        for key in new_keys:
            self.assertIn(key, research_dataset)

    def test_map_creators(self):
        """Test that creators are mapped correctly from DOI."""
        mapper = MetaDataMapper({}, {}, self.bytes)
        creators = self.doi_info["creators"]
        mapper._map_creators(creators)
        self.assertEqual(
            self.doi_info["creators"][0]["affiliation"][0]["affiliationIdentifier"],
            mapper.research_dataset["creator"][0]["member_of"]["identifier"],
        )
        self.assertEqual("Organization", mapper.research_dataset["creator"][0]["member_of"]["@type"])

    def test_map_field_of_science(self):
        """Test that field of science is mapped correctly from DOI subjects."""
        mapper = MetaDataMapper({}, {}, self.bytes)
        subjects = self.doi_info["subjects"]
        mapper._map_field_of_science(subjects)
        self.assertEqual(
            "http://www.yso.fi/onto/okm-tieteenala/ta999",
            mapper.research_dataset["field_of_science"][0]["identifier"],
        )
        self.assertEqual("Other", mapper.research_dataset["field_of_science"][0]["pref_label"]["en"])

    def test_map_field_of_science_with_error(self):
        """Test that field of science mapping method raises error response with a faulty subject title."""
        mapper = MetaDataMapper({}, {}, self.bytes)
        bad_subjects = [
            {"subject": "this subject is not part of the submission schema"},
            {"subject": "0 - neither is this"},
        ]
        with self.assertRaises(SubjectNotFoundException):
            mapper._map_field_of_science(bad_subjects)
