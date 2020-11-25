"""Test the EGA data mirroring tool."""
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from aiohttp import web

from metadata_backend.helpers.mirror import MetadataMirror


class MirrorTestCase(unittest.TestCase):
    """Data mirroring class test cases."""

    TESTFILES_ROOT = Path(__file__).parent / "test_files"

    def setUp(self):
        """Set class for tests."""
        self.mirror = MetadataMirror()

    def test_mirroring_fails(self):
        """Test 400 is raised when request to EGA fails."""
        with self.assertRaises(web.HTTPBadRequest) as err:
            self.mirror.mirror_dataset("EGAD")
        self.assertEqual(str(err.exception), "Something went wrong")

    def test_mirroring_fails_with_wrong_id(self):
        """Test 400 is raised if dataset ID is faulty."""
        with self.assertRaises(web.HTTPBadRequest) as err:
            self.mirror.mirror_dataset("not_ega")
        self.assertEqual(str(err.exception), "not_ega does not appear to be a valid EGA dataset.")

    def test_mirroring_works(self):
        """Test mirroring works with mock values."""
        with patch("metadata_backend.helpers.mirror.requests.Session.get") as mocked_get:
            mocked_get.return_value.status_code = 200
            mocked_get.return_value.json.return_value = {"response": {"result": [{"name": "test_dataset"}]}}
            self.mirror.get_dataset_objects = MagicMock(return_value=iter([{}, {}, {}, {}]))

            output = self.mirror.mirror_dataset("EGAD")
            assert mocked_get.called
            assert self.mirror.get_dataset_objects.called
            result = {
                "analysis": [],
                "dac": [],
                "dataset": {"datasetLinks": {}, "name": "test_dataset"},
                "sample": [],
                "study": [],
            }
            self.assertEqual(output, result)
