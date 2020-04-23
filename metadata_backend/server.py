from aiohttp import web
from metadata_backend.logger import LOG
from metadata_backend.routes import setup_routes
from metadata_backend.config import init_loadenv
from metadata_backend.views import SiteHandler
import asyncio
import uvloop
import os

routes = web.RouteTableDef()
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init():
    """Initialise server and setup routes."""
    server = web.Application()
    handler = SiteHandler()
    setup_routes(server, handler)
    return server


def main():
    """Do the server."""
    host = '0.0.0.0'  # nosec
    port = 5430

    LOG.info(f"Started server on {host}:{port}")
    web.run_app(init(), host=host, port=port, shutdown_timeout=0)


if __name__ == '__main__':
    main()
