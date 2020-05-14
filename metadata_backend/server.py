"""Functions to launch backend server."""

import asyncio

import uvloop
from aiohttp.web import Application, RouteTableDef, run_app

from .api.views import SiteHandler
from .helpers.logger import LOG

routes = RouteTableDef()
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init() -> Application:
    """Initialise server and setup routes."""
    server = Application()
    handler = SiteHandler()
    server.router.add_post('/submit', handler.submit)
    LOG.info("Server configurations and routes loaded")
    return server


def main():
    """Launch the server."""
    host = '0.0.0.0'  # nosec
    port = 5430
    LOG.info(f"Started server on {host}:{port}")
    run_app(init(), host=host, port=port, shutdown_timeout=0)


if __name__ == '__main__':
    main()
