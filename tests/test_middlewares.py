"""Test API middlewares."""

import json
import os

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


class AuthMiddlewareTestCase(AioHTTPTestCase):
    """Authentication middleware test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Configure default values for testing JWTs.

        Also set pem as an environment variable for the duration of the tests.
        """
        self.header = {"alg": "HS256", "typ": "JWT"}
        self.payload = {
            "sub": "test",
            "name": "tester",
            "iss": "haka_iss",
            "exp": 9999999999,
        }
        self.pem = {"kty": "oct", "alg": "RS256", "k": "GawgguFyGrWKav7AX4VKUg"}
        os.environ["PUBLIC_KEY"] = json.dumps(self.pem)

    async def tearDownAsync(self):
        """Unset the public key."""
        os.unsetenv("PUBLIC_KEY")

    @unittest_run_loop
    async def test_authentication_passes(self):
        """Test that JWT authenticates."""
        # Add claims to mocked token
        token = jwt.encode(self.header, self.payload, self.pem).decode("utf-8")
        data = _create_improper_data()
        response = await self.client.post("/submit", data=data, headers={"Authorization": f"Bearer {token}"})

        # Auth passes, hence response should be 400
        self.assertEqual(response.status, 400)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn("Bad Request", resp_dict["title"])
        os.unsetenv("PUBLIC_KEY")

    @unittest_run_loop
    async def test_authentication_fails_with_expired_jwt(self):
        """Test that JWT does not authenticate if token has expired."""
        # Add claims to mocked token
        payload = self.payload
        payload["exp"] = 0
        token = jwt.encode(self.header, payload, self.pem).decode("utf-8")
        data = _create_improper_data()
        response = await self.client.post("/submit", data=data, headers={"Authorization": f"Bearer {token}"})

        # Auth does not pass so response should be 401
        self.assertEqual(response.status, 401)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertEqual("expired_token: The token is expired", resp_dict["detail"])

    @unittest_run_loop
    async def test_authentication_fails_with_missing_claim(self):
        """Test JWT does not authenticate if 'iss' key is not in claims."""
        payload = self.payload
        del payload["iss"]
        token = jwt.encode(self.header, self.payload, self.pem).decode("utf-8")
        data = _create_improper_data()
        response = await self.client.post("/submit", data=data, headers={"Authorization": f"Bearer {token}"})

        # Auth does not pass so response should be 401
        self.assertEqual(response.status, 401)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertEqual('missing_claim: Missing "iss" claim', resp_dict["detail"])

    @unittest_run_loop
    async def test_authentication_fails_with_invalid_claim(self):
        """Test JWT does not authenticate with wrong 'iss' value."""
        # Add claims to mocked token
        payload = self.payload
        payload["iss"] = "wrong_iss"
        token = jwt.encode(self.header, payload, self.pem).decode("utf-8")
        data = _create_improper_data()
        response = await self.client.post("/submit", data=data, headers={"Authorization": f"Bearer {token}"})

        # Token contains incorrect info for authenticating so response is 403
        self.assertEqual(response.status, 403)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn('Token contains invalid_claim: Invalid claim "iss"', resp_dict["detail"])

    @unittest_run_loop
    async def test_bad_signature_error(self):
        """Test that altering the key raises bad signature error."""
        otherkey = {
            "kty": "oct",
            "alg": "RS256",
            "k": "hJtXIZ2uSN5kbQfbtTNWbpdmhkV8FJG",
        }
        token = jwt.encode(self.header, self.payload, otherkey).decode("utf-8")
        data = _create_improper_data()
        response = await self.client.post("/submit", data=data, headers={"Authorization": f"Bearer {token}"})

        # Auth does not pass so response should be 401
        self.assertEqual(response.status, 401)
        self.assertEqual(response.content_type, "application/problem+json")
        resp_dict = await response.json()
        self.assertIn("Token signature is invalid, bad_signature:", resp_dict["detail"])


def _create_improper_data():
    """Create request data that produces a 404 error.

    Submission method in API handlers raises Bad Request (400) error
    if 'submission' is not included on the first field of request
    """
    data = FormData()
    data.add_field("study", "content of a file", filename="file", content_type="text/xml")
    return data
