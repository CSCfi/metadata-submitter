"""Mock-up classes and functions for testing."""

import hashlib
from os import urandom
import yarl
import json

import cryptography.fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from authlib.jose import jwt, jwk
from typing import Tuple


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
    ret.app["Session"] = {}
    ret.app["Cookies"] = set({})
    ret.app["Crypt"] = cryptography.fernet.Fernet(cryptography.fernet.Fernet.generate_key())
    ret.app["Salt"] = hashlib.sha256(urandom(512)).hexdigest()
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


def generate_token() -> Tuple:
    """Generate RSA Key pair to be used to sign token and the JWT Token itself."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # we set no `exp` and other claims as they are optional in a real scenario these should bde set
    # See available claims here: https://www.iana.org/assignments/jwt/jwt.xhtml
    # the important claim is the "authorities"
    public_jwk = jwk.dumps(public_key, kty="RSA")
    private_jwk = jwk.dumps(pem, kty="RSA")

    return (public_jwk, private_jwk)


jwk_pair = generate_token()

keys = [jwk_pair[0]]
keys[0]["kid"] = "rsa1"
jwk_data = {"keys": keys}
header = {"jku": "http://mockauth:8000/jwk", "kid": "rsa1", "alg": "RS256", "typ": "JWT"}
id_token = {
    "at_hash": "fSi3VUa5i2o2SgY5gPJZgg",
    "sub": "smth",
    "eduPersonAffiliation": "member;staff",
    "eppn": "eppn@test.fi",
    "displayName": "test user",
    "iss": "http://iss.domain.com:5430",
    "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
    "given_name": "user",
    "nonce": "nonce",
    "aud": "aud2",
    "acr": "http://iss.domain.com:5430/LoginHaka",
    "nsAccountLock": "false",
    "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
    "auth_time": 1606579533,
    "name": "test user",
    "schacHomeOrganization": "test.what",
    "exp": 9999999999,
    "iat": 1561621913,
    "family_name": "test",
    "email": "eppn@test.fi",
}
id_token_no_sub = {
    "at_hash": "fSi3VUa5i2o2SgY5gPJZgg",
    "eduPersonAffiliation": "member;staff",
    "eppn": "eppn@test.fi",
    "displayName": "test user",
    "iss": "http://iss.domain.com:5430",
    "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
    "given_name": "user",
    "nonce": "nonce",
    "aud": "aud2",
    "acr": "http://iss.domain.com:5430/LoginHaka",
    "nsAccountLock": "false",
    "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
    "auth_time": 1606579533,
    "name": "test user",
    "schacHomeOrganization": "test.what",
    "exp": 9999999999,
    "iat": 1561621913,
    "family_name": "test",
    "email": "eppn@test.fi",
}
id_token_bad_nonce = {
    "at_hash": "fSi3VUa5i2o2SgY5gPJZgg",
    "eduPersonAffiliation": "member;staff",
    "eppn": "eppn@test.fi",
    "sub": "smth",
    "displayName": "test user",
    "iss": "http://iss.domain.com:5430",
    "schacHomeOrganizationType": "urn:schac:homeOrganizationType:test:other",
    "given_name": "user",
    "nonce": "",
    "aud": "aud2",
    "acr": "http://iss.domain.com:5430/LoginHaka",
    "nsAccountLock": "false",
    "eduPersonScopedAffiliation": "staff@test.what;member@test.what",
    "auth_time": 1606579533,
    "name": "test user",
    "schacHomeOrganization": "test.what",
    "exp": 9999999999,
    "iat": 1561621913,
    "family_name": "test",
    "email": "eppn@test.fi",
}
jwt_data = {"access_token": "test", "id_token": jwt.encode(header, id_token, jwk_pair[1]).decode("utf-8")}
jwt_data_claim_miss = {
    "access_token": "test",
    "id_token": jwt.encode(header, id_token_no_sub, jwk_pair[1]).decode("utf-8"),
}
jwt_data_bad_nonce = {
    "access_token": "test",
    "id_token": jwt.encode(header, id_token_bad_nonce, jwk_pair[1]).decode("utf-8"),
}
