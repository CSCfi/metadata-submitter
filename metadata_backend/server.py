from aiohttp import web
from metadata_backend.logger import LOG
from metadata_backend.routes import setup_routes
import asyncio
import uvloop

routes = web.RouteTableDef()
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init():
    """Initialise server and setup routes."""
    server = web.Application()
    setup_routes(server)
    return server


def main():
    """Do the server."""
    host = '0.0.0.0'  # nosec
    port = 5430
    init_loadenv()
    LOG.info(f"Started server on {host}:{port}")
    web.run_app(init(), host=host, port=port, shutdown_timeout=0)


if __name__ == '__main__':
    main()
