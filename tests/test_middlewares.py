"""Test API middlewares."""

from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init


class MiddlewaresTestCase(AioHTTPTestCase):
    """Api middlewares test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    @unittest_run_loop
    async def test_bad_HTTP_request_converts_into_json_response(self):
        """Test that middleware converts HTTP error into a JSON response."""
        data = FormData()
        data.add_field("study", "content of a file",
                       filename='file', content_type='text/xml')
        response = await self.client.post("/submit", data=data)
        # Submission method in API handlers raises Bad Request error
        # if no submission type is included on the first field of request
        self.assertEqual(response.status, 400)
        self.assertEqual(response.content_type, "application/json")
        self.assertIn("detail", await response.json())

    @unittest_run_loop
    async def test_random_error_converts_into_json_response(self):
        """Test that middleware converts random error into a JSON response."""
        response = await self.client.post("/submit", data=None)
        # POST requesting nothing results in an assertion error
        # which is not an HTTP error. Thus error status should be 500.
        self.assertEqual(response.status, 500)
        self.assertEqual(response.content_type, "application/json")
        self.assertIn("detail", await response.json())

    # TODO: Test for 404 and test for non error
