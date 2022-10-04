"""Test API middlewares."""

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp_session
from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase

from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.server import init


class ErrorMiddlewareTestCase(AioHTTPTestCase):
    """Error handling middleware test cases."""

    async def get_application(self):
        """Retrieve web Application for test."""
        return await init()

    async def setUpAsync(self):
        """Configure default values for testing and other modules.

        This patches used modules and sets default return values for their
        methods. Also sets up reusable test variables for different test
        methods.
        """
        self.app = await self.get_application()
        self.server = await self.get_server(self.app)
        self.client = await self.get_client(self.server)

        self.session_return = aiohttp_session.Session(
            "test-identity",
            new=True,
            data={},
        )

        self.session_return["access_token"] = "not-really-a-token"  # nosec
        self.session_return["at"] = time.time()
        self.session_return["user_info"] = "value"
        self.session_return["oidc_state"] = "state"

        self.aiohttp_session_get_session_mock = AsyncMock()
        self.aiohttp_session_get_session_mock.return_value = self.session_return
        self.p_get_sess_restapi = patch(
            "metadata_backend.api.handlers.restapi.aiohttp_session.get_session",
            self.aiohttp_session_get_session_mock,
        )

        await self.client.start_server()

    async def test_bad_HTTP_request_converts_into_json_response(self):
        """Test that middleware reformats 400 error with problem details."""
        data = _create_improper_data()
        with self.p_get_sess_restapi:
            response = await self.client.post(f"{API_PREFIX}/submit/FEGA", data=data)
            self.assertEqual(response.status, 400)
            self.assertEqual(response.content_type, "application/problem+json")
            resp_dict = await response.json()
            self.assertEqual("Bad Request", resp_dict["title"])
            self.assertEqual("There must be a submission.xml file in submission.", resp_dict["detail"])
            self.assertEqual(f"{API_PREFIX}/submit/FEGA", resp_dict["instance"])

    async def test_bad_url_returns_json_response(self):
        """Test that unrouted API url returns a 404 in JSON format."""
        with self.p_get_sess_restapi:
            response = await self.client.get(f"{API_PREFIX}/objects/swagadagamaster")
            self.assertEqual(response.status, 404)
            self.assertEqual(response.content_type, "application/problem+json")
            resp_dict = await response.json()
            self.assertEqual("Not Found", resp_dict["title"])


def _create_improper_data():
    """Create request data that produces a 400 error.

    Submission method in API handlers raises Bad Request (400) error
    if 'submission' is not included on the first field of request
    """
    path_to_file = Path(__file__).parent.parent / "test_files" / "study" / "SRP000539_invalid.xml"
    data = FormData()
    data.add_field("STUDY", open(path_to_file.as_posix(), "r"), filename="file", content_type="text/xml")
    return data
