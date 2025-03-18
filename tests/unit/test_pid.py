"""Test the PID DOI registering tool."""

import unittest
from unittest.mock import AsyncMock

from aiohttp import web

from metadata_backend.services.pid_ms_handler import PIDServiceHandler


class PIDTestCase(unittest.IsolatedAsyncioTestCase):
    """PID DOI registering class test case."""

    def setUp(self):
        """Set class for tests."""
        self.pid = PIDServiceHandler()

    async def test_400_is_raised(self):
        """Test 400 is raised when request to PID supposedly fails."""
        self.pid._request = AsyncMock(side_effect=web.HTTPBadRequest)
        with self.assertRaises(web.HTTPBadRequest):
            await self.pid.create_draft_doi_pid()
        assert self.pid._request.assert_called_once

    async def test_create_doi_draft_works(self):
        """Test draft DOI is returned correctly."""
        example_doi = "10.80869/sd-2108ec42-6ae9-39c0-9941-2ef802ff5b7f"
        self.pid._request = AsyncMock(return_value=example_doi)
        draft_doi = await self.pid.create_draft_doi_pid()
        assert self.pid._request.assert_called_once
        self.assertEqual(draft_doi, example_doi)
