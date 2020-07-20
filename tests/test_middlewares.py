"""Test API middlewares."""

import json
import os
from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from authlib.jose import jwt

from metadata_backend.server import init


class MiddlewaresTestCase(AioHTTPTestCase):
    """Api middlewares test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    @unittest_run_loop
    async def test_bad_HTTP_request_converts_into_json_response(self):
        """Test that middleware reformats 400 error with problem details."""
        data = FormData()
        data.add_field("study", "content of a file",
                       filename='file', content_type='text/xml')
        response = await self.client.post("/submit", data=data)
        # Submission method in API handlers raises Bad Request error
        # if submission type is not included on the first field of request
        self.assertEqual(response.status, 400)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn("Bad Request", resp_dict['title'])
        self.assertIn("There must be a submission.xml file in submission.",
                      resp_dict['detail'])
        self.assertIn("/submit", resp_dict['instance'])

    @unittest_run_loop
    async def test_bad_url_returns_json_response(self):
        """Test that unrouted api url returns a 404 in JSON format."""
        response = await self.client.get("/objects/swagadagamaster")
        self.assertEqual(response.status, 404)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn("Not Found", resp_dict['title'])

    @unittest_run_loop
    async def test_authentication_passes(self):
        """Test that JWT authenticates."""
        # Mock token
        header = {'alg': "HS256", 'type': "JWT"}
        payload = {'sub': "test", 'name': "tester", 'exp': 9999999999}
        pem = {
            "kty": "oct",
            "alg": "HS256",
            "k": "GawgguFyGrWKav7AX4VKUg"
        }
        token = jwt.encode(header, payload, pem).decode('utf-8')
        # Set pem as environment variable for the duration of the test
        os.environ['PUBLIC_KEY'] = json.dumps(pem)
        data = FormData()
        # This data would otherwise cause 400 error if authentication passed
        data.add_field("study", "content of a file",
                       filename='file', content_type='text/xml')
        response = await self.client.post("/submit", data=data,
                                          headers={'Authorization':
                                                   f"Bearer {token}"})

        self.assertEqual(response.status, 400)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn("Bad Request", resp_dict['title'])
        os.unsetenv('PUBLIC_KEY')

    @unittest_run_loop
    async def test_authentication_fails_with_expired_jwt(self):
        """Test that JWT does not authenticate if token has expired."""
        # Mock token
        header = {'alg': "HS256", 'type': "JWT"}
        payload = {'sub': "test", 'name': "tester", 'exp': 0}
        pem = {
            "kty": "oct",
            "alg": "HS256",
            "k": "GawgguFyGrWKav7AX4VKUg"
        }
        token = jwt.encode(header, payload, pem).decode('utf-8')
        # Set pem as environment variable for the duration of the test
        os.environ['PUBLIC_KEY'] = json.dumps(pem)
        data = FormData()
        # This data would otherwise cause 400 error if authentication passed
        data.add_field("study", "content of a file",
                       filename='file', content_type='text/xml')
        response = await self.client.post("/submit", data=data,
                                          headers={'Authorization':
                                                   f"Bearer {token}"})

        self.assertEqual(response.status, 401)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertEqual("expired_token: The token is expired",
                         resp_dict['detail'])
        os.unsetenv('PUBLIC_KEY')
