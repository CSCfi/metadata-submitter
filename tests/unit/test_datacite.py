"""Test the Datacite DOI registering tool."""

import unittest
from unittest.mock import AsyncMock

from aiohttp import web

from metadata_backend.services.datacite_service_handler import DataciteServiceHandler


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
