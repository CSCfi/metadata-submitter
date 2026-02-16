"""
Reverse proxy for mock-oauth2. Modifies /userinfo responses to
inject pouta access tokens, and all responses to change issue URLs.
Supports DPoP and acts as a DPoP termination point, validating DPoP
proofs and forwarding requests upstream as standard Bearer token requests.
"""

import base64
import contextlib
import hashlib
import json
import logging
import time
from os import getenv
from urllib.parse import urlparse, urlunparse

import httpx
import jwt
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

LOG = logging.getLogger("proxy")
logging.basicConfig(level=getenv("LOG_LEVEL", "INFO"))

MOCK_PROXY_URL = "http://mockauth:8000"
MOCK_PROXIED_URL = "http://mock-oauth2:8001/issuer"
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


async def log_request(request: Request):
    body = None
    try:
        body = await request.json()
    except Exception:
        try:
            raw = await request.body()
            body = raw.decode(errors="ignore") if raw else None
        except Exception as ex:
            LOG.error(f"Failed to decode request body: {str(ex)}")

    LOG.info("================ Proxied request ================>")
    LOG.info(f"Method: {request.method}")
    LOG.info(f"URL: {request.url}")
    LOG.info("Headers:")
    for k, v in request.headers.items():
        LOG.info(f"  {k}: {v}")
    if body:
        LOG.info(f"Body: {json.dumps(body)}")
    LOG.info("<================ Proxied request ================")


async def log_response(resp: httpx.Response):
    try:
        body = resp.json()
    except Exception:
        body = resp.text

    LOG.info("================ Proxied response ================>")
    LOG.info(f"Status code: {resp.status_code}")
    LOG.info("Headers:")
    for k, v in resp.headers.items():
        LOG.info(f"  {k}: {v}")
    if body:
        if isinstance(body, dict):
            LOG.info(f"Body: {json.dumps(body, indent=2)}")
        else:
            LOG.info(f"Body: {body}")
    LOG.info("<================ Proxied response ================")


def rewrite_issuer_urls(body: dict) -> dict:
    """Rewrite issuer and all endpoint URLs to point to this proxy, removing '/issuer' from paths."""

    body = body.copy()
    for key in [
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "userinfo_endpoint",
        "revocation_endpoint",
        "end_session_endpoint",
        "introspection_endpoint",
        "jwks_uri",
    ]:
        if key in body:
            url = urlparse(body[key])
            new_path = url.path.replace("/issuer", "")
            new_url = urlunparse(urlparse(MOCK_PROXY_URL)._replace(path=new_path, query=url.query))
            body[key] = new_url
            LOG.info(f"Replaced '{key}' URL: {url} -> {new_url}")

    return body


def rewrite_id_token_issuer(body: dict) -> dict:
    """Rewrite ID token issuer to point to this proxy, removing '/issuer' from paths."""

    if "id_token" not in body:
        return body

    # Decode without verification.
    claims = jwt.decode(body["id_token"], options={"verify_signature": False})

    old_iss = claims.get("iss")
    if old_iss:
        claims["iss"] = MOCK_PROXY_URL
        LOG.info(f"Replaced id token issuer: {old_iss} -> {MOCK_PROXY_URL}")

    body["id_token"] = jwt.encode(
        claims,
        key="",
        algorithm="none",
    )

    return body


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

    await log_response(resp)

    return resp


app = FastAPI(lifespan=lifespan)


@app.api_route("/userinfo", methods=["GET", "POST"])
async def userinfo(request: Request) -> JSONResponse:
    """Proxy OAUTH userinfo request to add pouta access token to userinfo."""

    proxied_url = f"{MOCK_PROXIED_URL}/userinfo"
    resp = await proxy_request(proxied_url, request)

    data = resp.json()
    data["pouta_access_token"] = request.app.state.pouta_token

    LOG.info(f"Returning userinfo: {json.dumps(data)}")

    return JSONResponse(
        content=data,
        status_code=resp.status_code,
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    """Proxy other OAUTH requests."""

    proxied_url = f"{MOCK_PROXIED_URL}/{path}"

    LOG.info(f"Auth proxy request {request.method} {request.url} to {proxied_url}/")

    resp = await proxy_request(proxied_url, request)

    LOG.info(f"Auth proxy response status code: {resp.status_code}")
    LOG.info(f"Auth proxy response content-type: {resp.headers.get('content-type')}")

    updated_content = None

    remove_headers = {
        # Remove hop‑by‑hop headers as defined in RFC 7230 §6.1.
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        # Remove content length header.
        "content-length",
    }
    headers = {k: v for k, v in resp.headers.items() if k.lower() not in remove_headers}

    try:
        body = resp.json()
    except ValueError:
        try:
            body = json.loads(resp.text)
        except json.JSONDecodeError:
            body = None

    if body is not None:
        try:
            body = rewrite_issuer_urls(body)
            body = rewrite_id_token_issuer(body)
            updated_content = json.dumps(body).encode("utf-8")
            LOG.info("================ Updated response body ================>")
            LOG.info(updated_content)
            LOG.info("<================ Updated response body ================")
        except Exception as ex:
            LOG.error(f"Failed to update response body: {str(ex)}")

    return Response(
        content=updated_content or resp.content,
        status_code=resp.status_code,
        headers=headers,
    )


@app.exception_handler(Exception)
async def log_exceptions(request: Request, exc: Exception):
    LOG.exception(f"Auth proxy exception {request.method} {request.url}: {str(exc)}")
    raise exc


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
