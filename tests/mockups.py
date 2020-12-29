"""Mock-up classes and functions for testing."""

import hashlib
import os
import yarl
import json

import cryptography.fernet


class MockResponse:
    """Mock-up class for HTTP response."""

    def __init__(self, text, status):
        """Initialize Mock Response."""
        self._text = text
        self.status = status

    async def text(self):
        """Get Mock Response body."""
        return self._text

    async def json(self):
        """Get Mock Response body."""
        return self._text

    async def __aexit__(self, exc_type, exc, tb):
        """Return async exit."""
        pass

    async def __aenter__(self):
        """Return async enter."""
        return self


class Mock_Request:
    """
    Mock-up class for the aiohttp.web.Request.

    It contains the dictionary
    representation of the requests that will be passed to the functions.
    (the actual request eing a MutableMapping instance)
    """

    def __init__(self):
        """Initialize Mock request."""
        # Application mutable mapping represented by a dictionary
        self.app = {}
        self.headers = {}
        self.cookies = {}
        self.query = {}
        self.remote = "127.0.0.1"
        self.url = yarl.URL("http://localhost:8080")
        self.post_data = {}

    def set_headers(self, headers):
        """
        Set mock request headers.

        Params:
            headers: dict
        """
        for i in headers.keys():
            self.headers[i] = headers[i]

    def set_cookies(self, cookies):
        """
        Set mock request cookies.

        Params:
            cookies: dict
        """
        for i in cookies.keys():
            self.cookies[i] = cookies[i]

    def set_post(self, data):
        """Set post data."""
        self.post_data = data

    async def post(self):
        """Return post data."""
        return self.post_data


def get_request_with_fernet():
    """Create a request with a working fernet object."""
    ret = Mock_Request()
    ret.app["Session"] = set({})
    ret.app["Cookies"] = {}
    ret.app["Crypt"] = cryptography.fernet.Fernet(cryptography.fernet.Fernet.generate_key())
    ret.app["Salt"] = hashlib.sha256(os.urandom(512)).hexdigest()
    return ret


def add_csrf_to_cookie(cookie, req, bad_sign=False):
    """Add specified csrf test variables to cookie."""
    # Getting options as a set
    cookie["referer"] = "http://localhost:8080"
    if bad_sign:
        cookie["signature"] = "incorrect"
    else:
        cookie["signature"] = hashlib.sha256(
            (cookie["id"] + cookie["referer"] + req.app["Salt"]).encode("utf-8")
        ).hexdigest()
    return cookie


def encrypt_cookie(cookie, req):
    """Add encrypted cookie to request."""
    cookie_crypted = req.app["Crypt"].encrypt(json.dumps(cookie).encode("utf-8")).decode("utf-8")
    req.cookies["MTD_SESSION"] = cookie_crypted
