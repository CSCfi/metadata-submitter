"""Test API middlewares."""

import unittest
from aiohttp import FormData, web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from metadata_backend.server import init
from metadata_backend.api.middlewares import generate_cookie, decrypt_cookie, _check_csrf
from .mockups import get_request_with_fernet, add_csrf_to_cookie, encrypt_cookie
from cryptography import fernet


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


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""

    def test_generate_cookie(self):
        """Test that the cookie generation works."""
        testreq = get_request_with_fernet()
        self.assertTrue(generate_cookie(testreq) is not None)

    def test_decrypt_cookie(self):
        """Test that the cookie decrypt function works."""
        testreq = get_request_with_fernet()
        # Generate cookie is tested separately, it can be used for testing the
        # rest of the functions without mockups
        cookie, testreq.cookies["MTD_SESSION"] = generate_cookie(testreq)
        self.assertEqual(cookie, decrypt_cookie(testreq))

    def test_session_check_nocookie(self):
        """Test session check raise 401 on non-existing cookie."""
        req = get_request_with_fernet()
        with self.assertRaises(web.HTTPUnauthorized):
            _check_csrf(req)

    def test_session_check_invtoken(self):
        """Test session check raise 401 on a stale cookie."""
        req = get_request_with_fernet()
        _, req.cookies["MTD_SESSION"] = generate_cookie(req)
        req.app["Crypt"] = fernet.Fernet(fernet.Fernet.generate_key())
        with self.assertRaises(web.HTTPUnauthorized):
            _check_csrf(req)

    def test_check_csrf_frontend_skip(self):
        """Test check_csrf when skipping referer from frontend."""
        with unittest.mock.patch(
            "metadata_backend.api.middlewares.aai_config",
            new={"redirect": "http://frontend:3000"},
        ):
            testreq = get_request_with_fernet()
            cookie, _ = generate_cookie(testreq)
            cookie = add_csrf_to_cookie(cookie, testreq)
            encrypt_cookie(cookie, testreq)
            testreq.headers["Referer"] = "http://frontend:3000"
            self.assertTrue(_check_csrf(testreq))

    def test_check_csrf_idp_skip(self):
        """Test check_csrf when skipping referer from auth endpoint."""
        with unittest.mock.patch(
            "metadata_backend.api.middlewares.aai_config",
            new={"auth_referer": "http://idp:3000"},
        ):
            testreq = get_request_with_fernet()
            cookie, _ = generate_cookie(testreq)
            cookie = add_csrf_to_cookie(cookie, testreq)
            encrypt_cookie(cookie, testreq)
            testreq.headers["Referer"] = "http://idp:3000"
            self.assertTrue(_check_csrf(testreq))

    def test_check_csrf_incorrect_referer(self):
        """Test check_csrf when Referer header is incorrect."""
        with unittest.mock.patch(
            "metadata_backend.api.middlewares.aai_config",
            new={"redirect": "http://localhost:3000"},
        ):
            testreq = get_request_with_fernet()
            cookie, _ = generate_cookie(testreq)
            cookie = add_csrf_to_cookie(cookie, testreq)
            encrypt_cookie(cookie, testreq)
            testreq.headers["Referer"] = "http://notlocaclhost:8080"
            with self.assertRaises(web.HTTPForbidden):
                _check_csrf(testreq)

    def test_check_csrf_no_referer(self):
        """Test check_csrf when no Referer header is present."""
        with unittest.mock.patch(
            "metadata_backend.api.middlewares.aai_config",
            new={"redirect": "http://localhost:5430"},
        ):
            testreq = get_request_with_fernet()
            cookie, _ = generate_cookie(testreq)
            cookie = add_csrf_to_cookie(cookie, testreq)
            encrypt_cookie(cookie, testreq)
            self.assertTrue(_check_csrf(testreq))

    def test_check_csrf_correct_referer(self):
        """Test check_csrf when the session is valid."""
        with unittest.mock.patch(
            "metadata_backend.api.middlewares.aai_config",
            new={"redirect": "http://localhost:5430"},
        ):
            testreq = get_request_with_fernet()
            cookie, _ = generate_cookie(testreq)
            cookie = add_csrf_to_cookie(cookie, testreq)
            encrypt_cookie(cookie, testreq)
            testreq.headers["Referer"] = "http://localhost:5430"
            self.assertTrue(_check_csrf(testreq))
