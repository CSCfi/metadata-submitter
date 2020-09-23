"""Test API middlewares."""

import json
import os
import time

from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from authlib.jose import jwt

from metadata_backend.server import init


class ErrorMiddlewareTestCase(AioHTTPTestCase):
    """Error handling middleware test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    @unittest_run_loop
    async def test_bad_HTTP_request_converts_into_json_response(self):
        """Test that middleware reformats 400 error with problem details."""
        data = _create_improper_data()
        response = await self.client.post("/submit", data=data)
        self.assertEqual(response.status, 400)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn("Bad Request", resp_dict["title"])
        self.assertIn("There must be a submission.xml file in submission.", resp_dict["detail"])
        self.assertIn("/submit", resp_dict["instance"])

    @unittest_run_loop
    async def test_bad_url_returns_json_response(self):
        """Test that unrouted api url returns a 404 in JSON format."""
        response = await self.client.get("/objects/swagadagamaster")
        self.assertEqual(response.status, 404)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn("Not Found", resp_dict["title"])


def _create_improper_data():
    """Create request data that produces a 404 error.

    Submission method in API handlers raises Bad Request (400) error
    if 'submission' is not included on the first field of request
    """
    data = FormData()
    data.add_field("study", "content of a file", filename="file", content_type="text/xml")
    return data
