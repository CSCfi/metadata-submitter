"""Test XML parser."""
import unittest
from pathlib import Path

from aiohttp import web

from metadata_backend.helpers.parser import XMLToJSONParser


class ParserTestCase(unittest.TestCase):
    """XML parser class test cases."""

    TESTFILES_ROOT = Path(__file__).parent / "test_files"

    def setUp(self):
        """Configure variables for tests."""
        self.parser = XMLToJSONParser()

    def load_xml_from_file(self, submission, filename):
        """Load xml as string from given file."""
        path_to_xml_file = self.TESTFILES_ROOT / submission / filename
        return path_to_xml_file.read_text()

    def test_study_is_parsed(self):
        """Test that study is parsed correctly.

        Tests for some values that converted json should have.
        """
        study_xml = self.load_xml_from_file("study", "SRP000539.xml")
        study_json = self.parser.parse("study", study_xml)
        self.assertIn("Highly integrated epigenome maps in Arabidopsis", study_json["descriptor"]["studyTitle"])
        self.assertIn("18423832", study_json["studyLinks"]["xrefLinks"][0]["id"])

    def test_sample_is_parsed(self):
        """Test that sample is parsed correctly and accessionId is set.

        Tests for some values that converted json should have.
        """
        sample_xml = self.load_xml_from_file("sample", "SRS001433.xml")
        sample_json = self.parser.parse("sample", sample_xml)
        self.assertIn("Human HapMap individual NA18758", sample_json["description"])
        self.assertIn("Homo sapiens", sample_json["sampleName"]["scientificName"])

    def test_experiment_is_parsed(self):
        """Test that experiment is parsed correctly and accessionId is set.

        Tests for some values that convert json should have.
        """
        experiment_xml = self.load_xml_from_file("experiment", "ERX000119.xml")
        experiment_json = self.parser.parse("experiment", experiment_xml)
        self.assertIn(
            "SOLiD sequencing of Human HapMap individual NA18504", experiment_json["design"]["designDescription"]
        )

    def test_run_is_parsed(self):
        """Test that run is parsed correctly and accessionId is set.

        Tests for some values that convert json should have.
        """
        run_xml = self.load_xml_from_file("run", "ERR000076.xml")
        run_json = self.parser.parse("run", run_xml)
        self.assertIn("ERA000/ERA000014/srf/BGI-FC304RWAAXX_5.srf", run_json["files"][0]["filename"])
        self.assertIn("ERX000037", run_json["experimentRef"]["accessionId"])

    def test_analysis_is_parsed(self):
        """Test that run is parsed correctly and accessionId is set.

        Tests for some values that convert json should have.
        """
        analysis_xml = self.load_xml_from_file("analysis", "ERZ266973.xml")
        analysis_json = self.parser.parse("analysis", analysis_xml)
        self.assertIn(
            "GCA_000001405.1",
            analysis_json["analysisType"]["processedReads"]["assembly"]["standard"]["accessionId"],
        )

    def test_submission_is_parsed(self):
        """Test that submission is parsed correctly.

        Test for specific actions in submission.
        """
        submission_xml = self.load_xml_from_file("submission", "ERA521986_valid.xml")
        submission_json = self.parser.parse("submission", submission_xml)
        self.assertEqual({"schema": "study", "source": "SRP000539.xml"}, submission_json["actions"]["action"][0]["add"])

    def test_error_raised_when_schema_not_found(self):
        """Test 400 is returned when schema."""
        with self.assertRaises(web.HTTPBadRequest):
            self.parser._load_schema("None")

    def test_error_raised_when_input_xml_not_valid_xml(self):
        """Give parser xml with broken syntax, should fail."""
        study_xml = self.load_xml_from_file("study", "SRP000539_invalid.xml")
        with self.assertRaises(web.HTTPBadRequest):
            self.parser.parse("study", study_xml)
