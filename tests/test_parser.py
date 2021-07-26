"""Test api endpoints from views module."""
import unittest
from pathlib import Path

from aiohttp import web

from metadata_backend.helpers.parser import XMLToJSONParser, CSVToJSONParser, jsonpatch_mongo
from pymongo import UpdateOne


class ParserTestCase(unittest.TestCase):
    """Parser Test Cases."""

    TESTFILES_ROOT = Path(__file__).parent / "test_files"

    def setUp(self):
        """Configure variables for tests."""
        self.xml_parser = XMLToJSONParser()
        self.csv_parser = CSVToJSONParser()

    def load_file_to_text(self, submission, filename):
        """Load XML or CSV as a string from given file."""
        path_to_xml_file = self.TESTFILES_ROOT / submission / filename
        return path_to_xml_file.read_text()

    def test_study_is_parsed(self):
        """Test that study is parsed correctly.

        Tests for some values that converted JSON should have.
        """
        study_xml = self.load_file_to_text("study", "SRP000539.xml")
        study_json = self.xml_parser.parse("study", study_xml)
        self.assertIn("Highly integrated epigenome maps in Arabidopsis", study_json["descriptor"]["studyTitle"])
        self.assertIn("18423832", study_json["studyLinks"][0]["xrefId"])

    def test_sample_is_parsed(self):
        """Test that sample is parsed correctly and accessionId is set.

        Tests for some values that converted JSON should have.
        """
        sample_xml = self.load_file_to_text("sample", "SRS001433.xml")
        sample_json = self.xml_parser.parse("sample", sample_xml)
        self.assertIn("Human HapMap individual NA18758", sample_json["description"])
        self.assertIn("Homo sapiens", sample_json["sampleName"]["scientificName"])

    def test_experiment_is_parsed(self):
        """Test that experiment is parsed correctly and accessionId is set.

        Tests for some values that convert JSON should have.
        """
        experiment_xml = self.load_file_to_text("experiment", "ERX000119.xml")
        experiment_json = self.xml_parser.parse("experiment", experiment_xml)
        self.assertIn(
            "SOLiD sequencing of Human HapMap individual NA18504", experiment_json["design"]["designDescription"]
        )

    def test_run_is_parsed(self):
        """Test that run is parsed correctly and accessionId is set.

        Tests for some values that convert JSON should have.
        """
        run_xml = self.load_file_to_text("run", "ERR000076.xml")
        run_json = self.xml_parser.parse("run", run_xml)
        self.assertIn("ERA000/ERA000014/srf/BGI-FC304RWAAXX_5.srf", run_json["files"][0]["filename"])
        self.assertIn("ERX000037", run_json["experimentRef"][0]["accessionId"])

    def test_analysis_is_parsed(self):
        """Test that run is parsed correctly and accessionId is set.

        Tests for some values that convert JSON should have.
        """
        analysis_xml = self.load_file_to_text("analysis", "ERZ266973.xml")
        analysis_json = self.xml_parser.parse("analysis", analysis_xml)
        self.assertIn(
            "GCA_000001405.1",
            analysis_json["analysisType"]["processedReads"]["assembly"]["accessionId"],
        )

    def test_submission_is_parsed(self):
        """Test that submission is parsed correctly.

        Test for specific actions in submission.
        """
        submission_xml = self.load_file_to_text("submission", "ERA521986_valid.xml")
        submission_json = self.xml_parser.parse("submission", submission_xml)
        self.assertEqual({"schema": "study", "source": "SRP000539.xml"}, submission_json["actions"]["action"][0]["add"])

    def test_error_raised_when_schema_not_found(self):
        """Test 400 is returned when schema type is invalid."""
        with self.assertRaises(web.HTTPBadRequest):
            self.xml_parser._load_schema("None")

    def test_error_raised_when_input_xml_not_valid_xml(self):
        """Give parser XML with broken syntax, should fail."""
        study_xml = self.load_file_to_text("study", "SRP000539_invalid.xml")
        with self.assertRaises(web.HTTPBadRequest):
            self.xml_parser.parse("study", study_xml)

    def test_csv_sample_is_parsed(self):
        """Test that a CSV sample is parsed and validated."""
        sample_csv = self.load_file_to_text("sample", "EGAformat.csv")
        result = self.csv_parser.parse("sample", sample_csv)
        self.assertEqual("test sample", result["title"])
        self.assertEqual({"taxonId": 9606}, result["sampleName"])

    def test_multiline_csv_raises_error(self):
        """Test 400 is raised with a multi-line CSV input."""
        with self.assertRaises(web.HTTPBadRequest):
            self.csv_parser.parse("sample", "id,title\n1,something\n2,something else\n")

    def test_csv_parse_with_wrong_schema(self):
        """Test 400 is raised with wrong schema type."""
        with self.assertRaises(web.HTTPBadRequest):
            self.csv_parser.parse("wrong", "id,title\n,\n")

    def test_empty_csv_raises_error(self):
        """Test 400 is raised with an empty or an incomplete CSV input."""
        with self.assertRaises(web.HTTPBadRequest):
            self.csv_parser.parse("sample", "")
        with self.assertRaises(web.HTTPBadRequest):
            self.csv_parser.parse("sample", "id,title,description\n")

    def test_is_csv_check(self):
        """Test 400 is raised with an empty or an incomplete CSV input."""
        sample_csv = self.load_file_to_text("sample", "EGAformat.csv")
        sample_xml = self.load_file_to_text("sample", "SRS001433.xml")
        self.assertEqual(self.csv_parser.is_csv(sample_csv), True)
        self.assertEqual(self.csv_parser.is_csv(sample_xml), False)
        self.assertEqual(self.csv_parser.is_csv(""), False)
        self.assertEqual(self.csv_parser.is_csv("a@b@;c@d@,e@f\ng"), False)
        self.assertEqual(self.csv_parser.is_csv("id,title,description\n,\n"), False)

    def test_json_patch_mongo_conversion(self):
        """Test JSON patch to mongo query conversion."""
        json_patch = [
            {
                "op": "add",
                "path": "/metadataObjects/-",
                "value": {"accessionId": "id", "schema": "study", "tags": {"submissionType": "XML"}},
            },
            {"op": "add", "path": "/drafts", "value": []},
            {"op": "replace", "path": "/published", "value": True},
        ]
        expected_mongo = [
            UpdateOne(
                {"accessionId": "id"},
                {
                    "$addToSet": {
                        "metadataObjects": {
                            "$each": [{"accessionId": "id", "schema": "study", "tags": {"submissionType": "XML"}}]
                        }
                    }
                },
                False,
                None,
                None,
                None,
            ),
            UpdateOne({"accessionId": "id"}, {"$set": {"drafts": []}}, False, None, None, None),
            UpdateOne({"accessionId": "id"}, {"$set": {"published": True}}, False, None, None, None),
        ]

        result = jsonpatch_mongo({"accessionId": "id"}, json_patch)
        self.assertEqual(result, expected_mongo)
