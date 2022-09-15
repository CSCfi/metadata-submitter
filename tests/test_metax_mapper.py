"""Test Metax metadata mapping methods."""
import json
import unittest
from pathlib import Path

from metadata_backend.services.metax_mapper import MetaDataMapper


class MetaDataMapperTestCase(unittest.TestCase):
    """MetaDataMapper Test Cases."""

    TESTFILES_ROOT = Path(__file__).parent / "test_files"

    def setUp(self):
        """Configure variables for tests."""
        self.mapper = MetaDataMapper("dataset", {}, {})
        doi_file = self.TESTFILES_ROOT / "doi" / "test_doi.json"
        self.test_doi = json.loads(doi_file.read_text())
        metax_file = self.TESTFILES_ROOT / "metax" / "research_dataset.json"
        self.test_metax = json.loads(metax_file.read_text())

    # Below tests will be activated in future PR
    '''
    def test_map_metadata(self):
        """Test that Metax metadata receives new data from DOI of a submission."""
        submission = {"doiInfo": self.test_doi, "extraInfo": {}}
        new_mapper = MetaDataMapper("dataset", {}, submission)
        research_dataset = new_mapper.map_metadata()
        new_keys = [
            "creator",
            "keyword",
            "contributor",
            "temporal",
            "spatial",
            "other_identifier",
            "language",
            "field_of_science",
        ]
        for key in new_keys:
            self.assertIn(key, research_dataset)

    def test_map_creators(self):
        """Test that creators are mapped correctly from DOI."""
        creators = self.test_doi["creators"]
        self.mapper._map_creators(creators)
        self.assertEqual(
            self.test_doi["creators"][0]["affiliation"][0]["affiliationIdentifier"],
            self.mapper.research_dataset["creator"][0]["member_of"]["identifier"],
        )
        self.assertEqual("Organization", self.mapper.research_dataset["creator"][0]["member_of"]["@type"])

    def test_map_field_of_science(self):
        """Test that field of science is mapped correctly from DOI subjects."""
        subjects = self.test_doi["subjects"]
        self.mapper._map_field_of_science(subjects)
        self.assertEqual(
            self.test_doi["subjects"][0]["valueUri"],
            self.mapper.research_dataset["field_of_science"][0]["identifier"],
        )
        self.assertEqual("Other", self.mapper.research_dataset["field_of_science"][0]["pref_label"]["en"])

    def test_map_field_of_science_with_error(self):
        """Test that field of science mapping method raises error response with a faulty subject title."""
        bad_subjects = [
            {"subject": "this subject is not part of the submission schema"},
            {"subject": "0 - neither is this"},
        ]
        with self.assertRaises(SubjectNotFoundException):
            self.mapper._map_field_of_science(bad_subjects)
    '''
