"""Test the EGA data mirroring tool."""
import os
import unittest
from unittest.mock import MagicMock
from pathlib import Path

from aiohttp import web

from metadata_backend.helpers.mirror import MetadataMirror


class MirrorTestCase(unittest.TestCase):
    """Data mirroring class test cases."""

    TESTFILES_ROOT = Path(__file__).parent / "test_files"

    def setUp(self):
        """Configure variables for tests."""
        self.mirror = MetadataMirror()
        os.environ["EGA_URL"] = "http://example.org/"

    def tearDown(self):
        """Revert environment variable."""
        os.unsetenv("EGA_URL")

    def test_mirroring_fails(self):
        """Test 400 is raised when request to EGA fails."""
        with self.assertRaises(web.HTTPBadRequest):
            self.mirror.mirror_dataset("EGAD")

    def test_mirroring_fails_with_wrong_id(self):
        """Test 400 is raised if dataset ID is faulty."""
        with self.assertRaises(web.HTTPBadRequest):
            self.mirror.mirror_dataset("not_ega")
