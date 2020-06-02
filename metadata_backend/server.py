"""Functions to launch backend server."""

import asyncio

import uvloop
from aiohttp import web

from .api.views import SiteHandler
from .helpers.logger import LOG

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init() -> web.Application:
    """Initialise server and setup routes.

    Routes should be setup by adding similar paths one after the another. (i.e.
    POST and GET for same path grouped together). Handler method names should
    be used for route names, so they're easy to use in other parts of the
    application. Note: if using variable resources (such as {schema}), add
    specific ones on top of more generic ones.
    """
    server = web.Application()
    handler = SiteHandler()
    routes = [web.get('/objects', handler.get_object_types),
              web.get('/object/{schema}/{accessionId}', handler.get_object,
                      name='get_object'),
              web.post('/object/{schema}', handler.submit_object,
                       name='submit_object'),
              web.post('/submit', handler.submit),
              web.get('/{schema}', handler.get_object),
              web.post('/{schema}', handler.submit_object)]
    server.router.add_routes(routes)
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
