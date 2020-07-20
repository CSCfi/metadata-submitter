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

    async def setUpAsync(self):
        """Set key as environment variable for the duration of the test."""
        key = {
            "kty": "oct",
            "alg": "HS256",
            "k": "GawgguFyGrWKav7AX4VKUg"
        }
        os.environ['PUBLIC_KEY'] = json.dumps(key)

    async def tearDownAsync(self):
        """Unset the public key."""
        os.unsetenv('PUBLIC_KEY')

    def create_improper_data(self):
        """Create request data that produces a 404 error.

        Submission method in API handlers raises Bad Request (400) error
        if 'submission' is not included on the first field of request
        """
        data = FormData()
        data.add_field("study", "content of a file",
                       filename='file', content_type='text/xml')
        return data

    @unittest_run_loop
    async def test_bad_HTTP_request_converts_into_json_response(self):
        """Test that middleware reformats 400 error with problem details."""
        data = self.create_improper_data()
        response = await self.client.post("/submit", data=data)
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
        header = {'alg': "HS256", 'typ': "JWT"}
        payload = {'sub': "test", 'name': "tester", 'exp': 9999999999}
        pem = {
            "kty": "oct",
            "alg": "HS256",
            "k": "GawgguFyGrWKav7AX4VKUg"
        }
        token = jwt.encode(header, payload, pem).decode('utf-8')
        data = self.create_improper_data()
        response = await self.client.post("/submit", data=data,
                                          headers={'Authorization':
                                                   f'Bearer {token}'})

        # Auth passes, hence response should be 400
        self.assertEqual(response.status, 400)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn("Bad Request", resp_dict['title'])
        os.unsetenv('PUBLIC_KEY')

    @unittest_run_loop
    async def test_authentication_fails_with_expired_jwt(self):
        """Test that JWT does not authenticate if token has expired."""
        # Mock token
        header = {'alg': "HS256", 'typ': "JWT"}
        payload = {'sub': "test", 'name': "tester", 'exp': 0}
        pem = {
            "kty": "oct",
            "alg": "HS256",
            "k": "GawgguFyGrWKav7AX4VKUg"
        }
        token = jwt.encode(header, payload, pem).decode('utf-8')
        data = self.create_improper_data()
        response = await self.client.post("/submit", data=data,
                                          headers={'Authorization':
                                                   f'Bearer {token}'})

        # Auth does not pass so response should be 401
        self.assertEqual(response.status, 401)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertEqual("expired_token: The token is expired",
                         resp_dict['detail'])
