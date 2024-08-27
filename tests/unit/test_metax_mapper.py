"""Test Metax metadata mapping methods."""

import json
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from metadata_backend.api.operators.file import FileOperator
from metadata_backend.services.metax_mapper import MetaDataMapper, SubjectNotFoundException


class MetaDataMapperTestCase(IsolatedAsyncioTestCase):
    """MetaDataMapper Test Cases."""

    TESTFILES_ROOT = Path(__file__).parent.parent / "test_files"

    def setUp(self):
        """Configure variables for tests."""
        self.client = MagicMock()
        self.mapper = MetaDataMapper("dataset", {}, {}, FileOperator(self.client))
        doi_file = self.TESTFILES_ROOT / "doi" / "test_doi.json"
        self.test_doi = json.loads(doi_file.read_text())
        metax_file = self.TESTFILES_ROOT / "metax" / "research_dataset.json"
        self.test_metax = json.loads(metax_file.read_text())

    async def test_map_metadata(self):
        """Test that Metax metadata receives new data from DOI of a submission."""
        submission = {"doiInfo": self.test_doi, "extraInfo": {}, "files": []}
        new_mapper = MetaDataMapper("dataset", {}, submission, FileOperator(self.client))
        research_dataset = await new_mapper.map_metadata()
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
            "http://www.yso.fi/onto/okm-tieteenala/ta999",
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

    async def test_map_file_bytes(self):
        """Test that the total size of files is calculated correctly."""
        submission = {
            "doiInfo": {},
            "extraInfo": {},
            "files": [
                {"accessionId": "672", "version": 1},
                {"accessionId": "781", "version": 2},
                {"accessionId": "268", "version": 1},
            ],
        }
        file_operator = FileOperator(self.client)
        file_operator.db_service.do_aggregate = AsyncMock(side_effect=_read_file_side_effect)
        new_mapper = MetaDataMapper("dataset", {}, submission, file_operator)
        await new_mapper._map_file_bytes()
        self.assertEqual(4440, new_mapper.research_dataset["total_remote_resources_byte_size"])


def _read_file_side_effect(*args):
    match args[1][0]["$match"]["accessionId"]:
        case "672":
            return [{"bytes": 3476, "flagDeleted": False}]
        case "781":
            return [{"bytes": 964, "flagDeleted": False}]
        case "268":
            return [{"bytes": 1623, "flagDeleted": True}]
