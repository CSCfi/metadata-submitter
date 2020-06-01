"""Test api endpoints from views module."""

from pathlib import Path


from metadata_backend.api.parser import SubmissionXMLToJSONParser
from aiohttp import web
from metadata_backend.helpers.schema_load import SchemaLoader
import unittest
import datetime
from pprint import pprint

from unittest.mock import patch


class ParserTestCase(unittest.TestCase):
    """Api endpoint class test cases."""

    TESTFILES_ROOT = Path(__file__).parent.parent / 'test_files'

    def setUp(self):
        """Configure default values and test variables for tests."""
        self.mock_accessionId = "EGA123456"
        self.parser = SubmissionXMLToJSONParser()
        self.patch_accession = patch.object(self.parser,
                                            "_generate_accessionId",
                                            return_value=self.mock_accessionId,
                                            autospec=True)
        self.patch_accession.start()

    def tearDown(self):
        """Cleanup patches."""
        self.patch_accession.stop()

    def load_xml_from_file(self, submission, filename):
        """Load xml as string from given file."""
        path_to_xml_file = self.TESTFILES_ROOT / submission / filename
        return path_to_xml_file.read_text()

    def test_accessionId_is_generated(self):
        """Test for accessionId."""
        accession = self.parser._generate_accessionId()
        assert accession == self.mock_accessionId

    @patch('metadata_backend.api.parser.datetime')
    def test_study_is_parsed(self, mocked_datetime):
        """Test that study is parsed correctly and accessionId is set.

        Tests for some values that converted json should have.
        """
        mocked_datetime.now.return_value = datetime.datetime(2020, 4, 14)
        study_xml = self.load_xml_from_file("study", "SRP000539.xml")
        study_json = self.parser.parse("study", study_xml)
        self.assertEqual(self.mock_accessionId, study_json['accessionId'])
        self.assertEqual(datetime.datetime(2020, 6, 14, 0, 0),
                         study_json['publishDate'])
        self.assertIn("Highly integrated epigenome maps in Arabidopsis",
                      study_json['descriptor']['studyTitle'])
        self.assertIn("18423832", study_json['studyLinks']['studyLink'][
            'xrefLink']['id'])

    def test_sample_is_parsed(self):
        """Test that sample is parsed correctly and accessionId is set.

        Tests for some values that converted json should have.
        """
        sample_xml = self.load_xml_from_file("sample", "SRS001433.xml")
        sample_json = self.parser.parse("sample", sample_xml)
        self.assertEqual(self.mock_accessionId, sample_json['accessionId'])
        self.assertIn("Human HapMap individual NA18758",
                      sample_json['description'])
        self.assertIn("Homo sapiens",
                      sample_json['sampleName']['scientificName'])

    def test_experiment_is_parsed(self):
        """Test that experiment is parsed correctly and accessionId is set.

        Tests for some values that convert json should have.
        """
        experiment_xml = self.load_xml_from_file("experiment", "ERX000119.xml")
        experiment_json = self.parser.parse("experiment", experiment_xml)
        self.assertEqual(self.mock_accessionId, experiment_json['accessionId'])
        self.assertIn("SOLiD sequencing of Human HapMap individual NA18504",
                      experiment_json['design']['designDescription'])

    def test_run_is_parsed(self):
        """Test that run is parsed correctly and accessionId is set.

        Tests for some values that convert json should have.
        """
        run_xml = self.load_xml_from_file("run", "ERR000076.xml")
        run_json = self.parser.parse("run", run_xml)
        self.assertEqual(self.mock_accessionId, run_json['accessionId'])
        self.assertIn("ERA000/ERA000014/srf/BGI-FC304RWAAXX_5.srf",
                      run_json['dataBlock']['files']['file']['attributes'][
                          'filename'])
        self.assertIn("ERX000037", run_json['experimentRef']['attributes'][
            'accession'])

    def test_analysis_is_parsed(self):
        """Test that run is parsed correctly and accessionId is set.

        Tests for some values that convert json should have.
        """
        analysis_xml = self.load_xml_from_file("analysis", "ERZ266973.xml")
        analysis_json = self.parser.parse("analysis", analysis_xml)
        pprint(analysis_json)
        self.assertEqual(self.mock_accessionId, analysis_json['accessionId'])
        self.assertIn("GCA_000001405.1", analysis_json['analysisType'][
            'processedReads']['assembly']['standard']['attributes'][
            'accession'])

    def test_error_raised_when_schema_not_found(self):
        """Test 400 is returned when schema."""
        with self.assertRaises(web.HTTPBadRequest):
            self.parser._load_schema("None")

    def test_error_raised_when_validate_fails_against_schema(self):
        """Create sample validator, which should fail to validate study."""
        loader = SchemaLoader()
        schema = loader.get_schema("sample")
        with self.assertRaises(web.HTTPBadRequest):
            self.parser._validate("<STUDY_SET></STUDY_SET>", schema)

    def test_error_raised_when_input_xml_not_valid_xml(self):
        """Give validator xml with broken syntax, should fail."""
        loader = SchemaLoader()
        schema = loader.get_schema("study")
        study_xml = self.load_xml_from_file("study", "SRP000539_invalid.xml")
        with self.assertRaises(web.HTTPBadRequest):
            self.parser._validate(study_xml, schema)

    def test_submission_xml_actions_are_sorted(self):
        """Check xmls are sorted to correct order."""
        original_list = [{"schema": "dac", "content": "foo"},
                         {"schema": "analysis", "content": "bar"},
                         {"schema": "study", "content": "foo"},
                         {"schema": "sample", "content": "bar"}]
        goal_list = [{"schema": "study", "content": "foo"},
                     {"schema": "sample", "content": "bar"},
                     {"schema": "analysis", "content": "bar"},
                     {"schema": "dac", "content": "foo"}]
        sorted_list = self.parser._sort_actions_by_schemas(original_list)
        self.assertEqual(goal_list, sorted_list)
