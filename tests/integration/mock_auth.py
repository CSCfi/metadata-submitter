"""
Proxy for mock-oauth2. Modifies /userinfo responses to
inject pouta access tokens. Modifies all responses to change
URLs. Supports DPoP and acts as a DPoP termination point, validating DPoP
proofs and forwarding requests upstream as standard Bearer token requests.
"""

import base64
import contextlib
import hashlib
import json
import logging
import re
import time
from os import getenv
from typing import Any

import httpx
import jwt
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

LOG = logging.getLogger("proxy")
logging.basicConfig(level="INFO")

PROXY_URL = "http://mockauth:8000"
PROXIED_BASE_URL = "http://mock-oauth2:8001"
PROXIED_URL = f"{PROXIED_BASE_URL}/issuer"
PROXIED_PATTERN = re.compile(re.escape(PROXIED_URL), re.IGNORECASE)
PROXIED_BASE_PATTERN = re.compile(re.escape(PROXIED_BASE_URL), re.IGNORECASE)

MOCK_KEYSTONE_URL = getenv("KEYSTONE_ENDPOINT")
MOCK_KEYSTONE_USERNAME = "swift"
MOCK_KEYSTONE_PASSWORD = "veryfast"

DPoP_REPLAY_CACHE = set()
DPoP_SKEW = 60


def validate_and_terminate_dpop(request: Request, headers: dict):
    """
    Validates DPoP proof and converts Authorization header to Bearer.
    Removes DPoP header before forwarding upstream.
    """

    auth = headers.get("authorization")

    if not auth or not auth.lower().startswith("dpop "):
        # Not a DPoP request.
        return

    LOG.info("DPoP authorization header")

    dpop_proof = headers.get("dpop")
    if not dpop_proof:
        raise RuntimeError("Missing DPoP proof")

    access_token = auth.split(" ", 1)[1]

    LOG.info("Decoding DPoP proof without verification")

    try:
        claims = jwt.decode(dpop_proof, options={"verify_signature": False})
    except jwt.InvalidTokenError as e:
        raise RuntimeError(f"Invalid DPoP proof: {e}")

    LOG.info("Validating DPoP claims")

    # Validate DPoP claims
    if claims.get("htm") != request.method:
        raise RuntimeError("DPoP htm mismatch")
    if claims.get("htu") != str(request.url):
        raise RuntimeError("DPoP htu mismatch")

    def _b64url_sha256(_value: str) -> str:
        _digest = hashlib.sha256(_value.encode()).digest()
        return base64.urlsafe_b64encode(_digest).rstrip(b"=").decode()

    if claims.get("ath") != _b64url_sha256(access_token):
        raise RuntimeError("DPoP ath mismatch")

    LOG.info("Validating DPoP replay protection")

    jti = claims.get("jti")
    if not jti:
        raise RuntimeError("Missing jti in DPoP")

    if jti in DPoP_REPLAY_CACHE:
        raise RuntimeError("DPoP replay detected")

    DPoP_REPLAY_CACHE.add(jti)

    LOG.info("Validating DPoP issued-at time")

    iat = claims.get("iat")
    if not iat or abs(time.time() - iat) > DPoP_SKEW:
        raise RuntimeError("DPoP iat outside allowed skew")

    LOG.info("Terminating DPoP request")

    # Terminate DPoP by converting to Bearer token and removing dpop header.
    headers["authorization"] = f"Bearer {access_token}"
    headers.pop("dpop", None)

    LOG.info("DPoP proof validated and terminated")


async def log_request(request: Request) -> None:
    LOG.info("================ Proxied request ================>")
    LOG.info(f"Method: {request.method}")
    LOG.info(f"URL: {request.url}")
    LOG.info("Headers:")
    for k, v in request.headers.items():
        LOG.info(f"  {k}: {v}")
    try:
        body = await request.json()
        LOG.info(f"Body: {json.dumps(body)}")
    except Exception:
        body = await request.body()
        body = body.decode(errors="ignore") if body else None
        LOG.info(f"Body: {body}")
    LOG.info("<================ Proxied request ================")


def log_response(status_code, headers, body) -> None:
    LOG.info("================ Proxied response ================>")
    LOG.info(f"Status code: {status_code}")
    LOG.info("Headers:")
    for k, v in headers.items():
        LOG.info(f"  {k}: {v}")
    try:
        LOG.info(f"Body: {json.dumps(body)}")
    except Exception:
        LOG.info(f"Body: {body}")
    LOG.info("<================ Proxied response ================")


def rewrite_str(s: str) -> str:
    """
    Rewrite all URLs.
    """
    s = PROXIED_PATTERN.sub(PROXY_URL, s)
    return PROXIED_BASE_PATTERN.sub(PROXY_URL, s)


def rewrite_json(obj: Any) -> Any:
    """
    Recursively rewrite URLs in JSON body.
    """
    if isinstance(obj, dict):
        d = {}
        for k, v in obj.items():
            d[k] = rewrite_json(v)
        return d
    elif isinstance(obj, list):
        return [rewrite_json(o) for o in obj]
    elif isinstance(obj, str):
        return rewrite_str(obj)
    else:
        return obj


def rewrite_body(resp: httpx.Response) -> Any:
    """
    Rewrite URLs response body.
    """
    try:
        body = resp.json()
        body = rewrite_json(body)
        body = rewrite_id_token(body)
        return body
    except Exception:
        return rewrite_str(resp.text)


def rewrite_id_token(body: dict) -> dict:
    """Rewrite ID token issuer to point to this proxy."""

    if "id_token" not in body:
        return body

    # Decode without verification.
    claims = jwt.decode(body["id_token"], options={"verify_signature": False})

    old_iss = claims.get("iss")
    if old_iss:
        claims["iss"] = PROXY_URL
        LOG.info(f"Replaced id token issuer: {old_iss} -> {PROXY_URL}")

    body["id_token"] = jwt.encode(
        claims,
        key="",
        algorithm="none",
    )

    return body


def rewrite_headers(headers: dict):
    """
    Remove hop‑by‑hop headers as defined in RFC 7230 §6.1. Remove content-length
    header. Rewrite URLs.
    """
    new = {}
    for k, v in headers.items():
        if k.lower() in {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
            "content-length",
        }:
            continue

        if isinstance(v, str):
            v = rewrite_str(v)

        new[k] = v
    return new


async def get_pouta_token() -> str:
    keystone_data = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "domain": {"id": "default"},
                        "name": MOCK_KEYSTONE_USERNAME,
                        "password": MOCK_KEYSTONE_PASSWORD,
                    }
                },
            }
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MOCK_KEYSTONE_URL}/v3/auth/tokens",
            json=keystone_data,
        )

    if resp.status_code >= 400:
        raise RuntimeError(f"Keystone auth failed: {resp.text}")

    LOG.info("Fetched pouta access token")

    return resp.headers["X-Subject-Token"]


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Get pouta access token from keystone."""

    app.state.pouta_token = await get_pouta_token()

    yield


async def proxy_request(proxied_url: str, request: Request) -> httpx.Response:
    await log_request(request)

    headers = {k.lower(): v for k, v in request.headers.items()}
    headers.pop("host", None)

    validate_and_terminate_dpop(request, headers)

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            request.method, proxied_url, headers=headers, params=request.query_params, content=await request.body()
        )

    return resp


app = FastAPI(lifespan=lifespan)


@app.api_route("/userinfo", methods=["GET", "POST"])
async def userinfo(request: Request) -> JSONResponse:
    """Proxy userinfo to add pouta access token."""

    resp = await proxy_request(f"{PROXIED_URL}/userinfo", request)

    headers = rewrite_headers(resp.headers)
    body = rewrite_body(resp)
    body["pouta_access_token"] = request.app.state.pouta_token

    log_response(resp.status_code, headers, body)

    return JSONResponse(
        status_code=resp.status_code,
        headers=headers,
        content=body,
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    """Proxy other requests."""

    resp = await proxy_request(f"{PROXIED_URL}/{path}", request)

    headers = rewrite_headers(resp.headers)
    body = rewrite_body(resp)

    if isinstance(body, (dict, list)):
        content = json.dumps(body).encode("utf-8")
    else:
        content = body.encode("utf-8")

    log_response(resp.status_code, headers, content)

    return Response(
        status_code=resp.status_code,
        headers=headers,
        content=content,
    )


@app.exception_handler(Exception)
async def log_exceptions(request: Request, exc: Exception):
    LOG.exception(f"Auth proxy exception {request.method} {request.url}: {str(exc)}")
    raise exc


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
