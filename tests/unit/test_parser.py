"""Test parser methods."""
import unittest
from pathlib import Path

from aiohttp import web
from pymongo import UpdateOne

from metadata_backend.helpers.parser import (
    CSVToJSONParser,
    XMLToJSONParser,
    jsonpatch_mongo,
)


class ParserTestCase(unittest.TestCase):
    """Parser Test Cases."""

    TESTFILES_ROOT = Path(__file__).parent.parent / "test_files"

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

        Tests for some values that converted JSON should have.
        """
        experiment_xml = self.load_file_to_text("experiment", "ERX000119.xml")
        experiment_json = self.xml_parser.parse("experiment", experiment_xml)
        self.assertIn(
            "SOLiD sequencing of Human HapMap individual NA18504", experiment_json["design"]["designDescription"]
        )

    def test_run_is_parsed(self):
        """Test that run is parsed correctly and accessionId is set.

        Tests for some values that converted JSON should have.
        """
        run_xml = self.load_file_to_text("run", "ERR000076.xml")
        run_json = self.xml_parser.parse("run", run_xml)
        self.assertIn("ERA000/ERA000014/srf/BGI-FC304RWAAXX_5.srf", run_json["files"][0]["filename"])
        self.assertIn("ERX000037", run_json["experimentRef"][0]["accessionId"])

    def test_analysis_is_parsed(self):
        """Test that run is parsed correctly and accessionId is set.

        Tests for some values that converted JSON should have.
        """
        analysis_xml = self.load_file_to_text("analysis", "ERZ266973.xml")
        analysis_json = self.xml_parser.parse("analysis", analysis_xml)
        self.assertIn(
            "GCA_000001405.1",
            analysis_json["analysisType"]["processedReads"]["assembly"]["accession"],
        )
        self.assertEqual(25, len(analysis_json["analysisType"]["processedReads"]["sequence"]))
        self.assertEqual(list, type(analysis_json["sampleRef"]))

    def test_submission_is_parsed(self):
        """Test that submission is parsed correctly.

        Test for specific actions in submission.
        """
        submission_xml = self.load_file_to_text("submission", "ERA521986_valid.xml")
        submission_json = self.xml_parser.parse("submission", submission_xml)
        self.assertEqual({"schema": "study", "source": "SRP000539.xml"}, submission_json["actions"]["action"][0]["add"])

    def test_dataset_is_parsed(self):
        """Test that dataset is parsed correctly.

        Tests for some values that converted JSON should have.
        """
        dataset_xml = self.load_file_to_text("dataset", "dataset.xml")
        dataset_json = self.xml_parser.parse("dataset", dataset_xml)
        self.assertEqual(2, len(dataset_json["datasetType"]))
        self.assertEqual(8, len(dataset_json["runRef"]))

    def test_policy_is_parsed(self):
        """Test that policy is parsed correctly.

        Tests for some values that converted JSON should have.
        """
        policy_xml = self.load_file_to_text("policy", "policy.xml")
        policy_json = self.xml_parser.parse("policy", policy_xml)
        self.assertIn("accessionId", policy_json["dacRef"])
        self.assertEqual(2, len(policy_json["dataUses"]))

    def test_multi_policy_is_parsed(self):
        """Test that xml with 2 policies is parsed correctly.

        Tests for some values that converted JSON should have.
        """
        policy_xml = self.load_file_to_text("policy", "policy2.xml")
        policy_json = self.xml_parser.parse("policy", policy_xml)
        self.assertEqual(2, len(policy_json))
        self.assertEqual("asgsasg", policy_json[0]["alias"])
        self.assertEqual("asgsasgaSas", policy_json[1]["alias"])

    def test_bp_image_is_parsed(self):
        """Test that BP image is parsed correctly.

        Tests for some values that converted JSON should have.
        """
        image_xml = self.load_file_to_text("bpimage", "images_single.xml")
        image_json = self.xml_parser.parse("bpimage", image_xml)
        self.assertEqual("Image_tSQsAkvutz", image_json["alias"])
        self.assertEqual(6, len(image_json["attributes"]["attribute"]))
        self.assertEqual(4, len(image_json["attributes"]["attributeSet"]))
        self.assertEqual("asdf", image_json["files"][0]["filename"])

    def test_multi_image_is_parsed(self):
        """Test that multiple BP images are parsed correctly.

        Tests for some values that converted JSON should have.
        """
        image_xml = self.load_file_to_text("bpimage", "images_multi.xml")
        image_json = self.xml_parser.parse("bpimage", image_xml)
        self.assertEqual(2, len(image_json))
        self.assertEqual("Image_tSQsAkvutz", image_json[0]["alias"])
        self.assertEqual("Image_ReLyCtLAWo", image_json[1]["alias"])
        self.assertEqual("asdf", image_json[1]["files"][0]["filename"])

    def test_bp_dataset_is_parsed(self):
        """Test that BP dataset is parsed correctly.

        Tests for some values that converted JSON should have.
        """
        bp_dataset_xml = self.load_file_to_text("bpdataset", "template_dataset.xml")
        bp_dataset_json = self.xml_parser.parse("bpdataset", bp_dataset_xml)
        self.assertEqual("Dataset_QoRIPbAPlP", bp_dataset_json["alias"])
        self.assertEqual("1", bp_dataset_json["attributes"][0]["value"])
        self.assertEqual(list, type(bp_dataset_json["datasetType"]))

    def test_bp_sample_is_parsed(self):
        """Test that BP sample is parsed correctly.

        Tests for some values that converted JSON should have.
        """
        bp_sample_xml = self.load_file_to_text("bpsample", "template_samples.xml")
        bp_sample_json = self.xml_parser.parse("bpsample", bp_sample_xml)
        self.assertEqual(12, len(bp_sample_json))
        bb_alias = "BiologicalBeing_qLNZYjYjyZ"
        self.assertEqual(bb_alias, bp_sample_json[0]["biologicalBeing"]["alias"])
        self.assertEqual(bb_alias, bp_sample_json[2]["case"]["biologicalBeing"]["refname"])
        self.assertEqual(bb_alias, bp_sample_json[4]["specimen"]["extractedFrom"]["refname"])
        self.assertEqual(65.0, bp_sample_json[4]["specimen"]["attributes"][3]["value"])
        self.assertEqual("sample_preparation", bp_sample_json[6]["block"]["attributes"][0]["tag"])
        self.assertEqual("something", bp_sample_json[9]["slide"]["stainingInformation"]["refname"])

    def test_bp_observation_is_parsed(self):
        """Test that BP observation is parsed correctly.

        Tests for some values that converted JSON should have.
        """
        observation_xml = self.load_file_to_text("bpobservation", "observations.xml")
        observation_json = self.xml_parser.parse("bpobservation", observation_xml)
        self.assertEqual("Observation_gHJhZLyAMP", observation_json["alias"])
        self.assertEqual("Case_GMGVsazraj", observation_json["observedOn"]["case"]["refname"])
        self.assertEqual("Diagnose", observation_json["statement"]["codedAttributesSet"][0]["tag"])

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
        self.assertEqual(len(result), 3)
        self.assertEqual("test sample", result[0]["title"])
        self.assertEqual({"taxonId": 9606}, result[0]["sampleName"])

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
