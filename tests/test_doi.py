"""Test the DOI registering tool."""
import unittest
from unittest.mock import patch

from aiohttp import web

from metadata_backend.services.datacite_service_handler import DataciteServiceHandler


class DOITestCase(unittest.TestCase):
    """DOI registering class test case."""

    def setUp(self):
        """Set class for tests."""
        self.doi = DataciteServiceHandler()

    async def test_400_is_raised(self):
        """Test 400 is raised when request to DataCite supposedly fails."""
        with patch("aiohttp.ClientSession.post") as mocked_post:
            mocked_post.return_value.status_code = 400
            with self.assertRaises(web.HTTPBadRequest) as err:
                await self.doi.create_draft()
                self.assertEqual(str(err.exception), "DOI API draft creation request failed with code: 400")

    async def test_create_doi_draft_works(self):
        """Test DOI info is returned correctly when request succeeds."""
        with patch("aiohttp.ClientSession.post") as mocked_post:
            mocked_post.return_value.status = 201
            mocked_post.return_value.json.return_value = {
                "data": {
                    "id": "10.xxxx/yyyyy",
                    "type": "dois",
                    "attributes": {
                        "doi": "10.xxxx/yyyyy",
                        "prefix": "10.xxxx",
                        "suffix": "yyyyy",
                        "identifiers": [{"identifier": "https://doi.org/10.xxxx/yyyyy", "identifierType": "DOI"}],
                    },
                }
            }

            output = await self.doi.create_draft()
            assert mocked_post.called
            result = {"fullDOI": "10.xxxx/yyyyy", "dataset": "https://doi.org/10.xxxx/yyyyy"}
            self.assertEqual(output, result)
