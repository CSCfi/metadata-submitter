"""Functions to launch backend server."""

import asyncio

import uvloop
from aiohttp import web

from .api.views import SiteHandler
from .helpers.logger import LOG

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init() -> web.Application:
    """Initialise server and setup routes."""
    server = web.Application()
    handler = SiteHandler()
    server.router.add_post('/submit', handler.submit)
    LOG.info("Server configurations and routes loaded")
    return server


def main() -> None:
    """Launch the server."""
    host = '0.0.0.0'  # nosec
    port = 5430
    web.run_app(init(), host=host, port=port, shutdown_timeout=0)
    LOG.info(f"Started server on {host}:{port}")


if __name__ == '__main__':
    main()
