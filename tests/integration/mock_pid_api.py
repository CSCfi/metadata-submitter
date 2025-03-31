"""Mock aiohttp.web server for PID API calls."""

import json
import logging
from os import getenv
from urllib.parse import urlparse
from uuid import uuid4

from aiohttp import web

mock_pid_prefix = "10.80869"

FORMAT = "[%(asctime)s][%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

LOG = logging.getLogger("server")
LOG.setLevel(getenv("LOG_LEVEL", "INFO"))

REQUIRED = ["event", "creators", "titles", "types", "publisher", "publicationYear", "url"]
DOIS = {}


def check_url(url) -> bool:
    """Check if url is valid."""
    domain = urlparse(url).netloc
    return "csc.fi" in domain or "fairdata.fi" in domain


async def create(req: web.Request) -> web.Response:
    """DOI draft creation endpoint."""
    try:
        content = await req.json()
    except json.decoder.JSONDecodeError as e:
        # NB PID ms doesn't provide error messages
        reason = f"JSON is not correctly formatted. See: {e}"
        LOG.info(reason)
        raise web.HTTPBadRequest(reason=reason)
    try:
        if content["data"]["attributes"]["doi"] == "":
            uuid = uuid4()
            doi = f"{mock_pid_prefix}/sd-{uuid}"
            DOIS.update({doi: ""})
            return web.Response(status=200, text=doi)
    except Exception as e:
        reason = f"Provided payload did not include required attributes: {e}"
        LOG.exception(reason)
        raise web.HTTPBadRequest(reason=reason)


async def update(req: web.Request) -> web.Response:
    """DOI update endpoint."""
    try:
        content = await req.json()
    except json.decoder.JSONDecodeError as e:
        reason = f"JSON is not correctly formatted: {e}"
        LOG.exception(reason)
        raise web.HTTPBadRequest(reason=reason)
    prefix = req.match_info["prefix"]
    suffix = req.match_info["suffix"]
    doi = f"{prefix}/{suffix}"
    if doi not in DOIS.keys():
        reason = f"Invalid draft DOI in request: {doi}"
        LOG.exception(reason)
        raise web.HTTPBadRequest(reason=reason)
    try:
        # only checks that attributes exist in payload
        for attr in REQUIRED:
            if attr not in content["data"]["attributes"]:
                raise KeyError(attr)
        url: str = content["data"]["attributes"]["url"]
        url_valid = check_url(url)
        if not url_valid or url in DOIS.values():
            raise ValueError(f"url {url} already in use")
    except Exception as e:
        reason = f"Missing or invalid required attributes in payload: {e}"
        LOG.exception(reason)
        raise web.HTTPBadRequest(reason=reason)
    DOIS.update({doi: url})
    return web.Response(status=200, text=url)


async def heartbeat(req: web.Request) -> web.Response:
    """PID heartbeat endpoint."""
    data = {"status": "UP", "checks": []}
    return web.json_response(data, status=200)


async def init() -> web.Application:
    """Start server."""
    app = web.Application()
    app.router.add_get("/q/health/live", heartbeat)
    app.router.add_post("/v1/pid/doi", create)
    app.router.add_put("/v1/pid/doi/{prefix}/{suffix}", update)
    # PID has no endpoints to delete draft DOIs or retrieve DOIs
    return app


if __name__ == "__main__":
    web.run_app(init(), port=8005)
