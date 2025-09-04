"""Test DOI registering tools."""

import unittest
from unittest.mock import AsyncMock

from aiohttp import web

from metadata_backend.services.datacite_service_handler import DataciteServiceHandler
from metadata_backend.services.pid_ms_handler import PIDServiceHandler


class DataciteTestCase(unittest.IsolatedAsyncioTestCase):
    """Datacite DOI registering class test case."""

    def setUp(self):
        """Set class for tests."""
        self.datacite = DataciteServiceHandler()

    async def test_400_is_raised(self):
        """Test 400 is raised when request to DataCite supposedly fails."""
        self.datacite._request = AsyncMock(side_effect=web.HTTPBadRequest)
        with self.assertRaises(web.HTTPBadRequest):
            await self.datacite.create_draft_doi_datacite("study")
        assert self.datacite._request.assert_called_once

    async def test_create_doi_draft_works(self):
        """Test DOI info is returned correctly when request succeeds."""
        example_doi = "10.xxxx/yyyyy"
        self.datacite._request = AsyncMock(
            return_value={
                "data": {
                    "id": example_doi,
                    "type": "dois",
                    "attributes": {
                        "doi": example_doi,
                        "prefix": "10.xxxx",
                        "suffix": "yyyyy",
                        "identifiers": [{"identifier": "https://doi.org/10.xxxx/yyyyy", "identifierType": "DOI"}],
                    },
                }
            }
        )
        doi = await self.datacite.create_draft_doi_datacite("dataset")
        assert self.datacite._request.assert_called_once
        self.assertEqual(doi, example_doi)


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
