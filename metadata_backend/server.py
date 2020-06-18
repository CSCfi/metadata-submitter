"""Functions to launch backend server."""

import asyncio

import uvloop
from aiohttp import web

from .api.handlers import RESTApiHandler, StaticHandler, SubmissionAPIHandler
from .conf.conf import frontend_static_files
from .helpers.logger import LOG

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init() -> web.Application:
    """Initialise server and setup routes.

    Routes should be setup by adding similar paths one after the another. (i.e.
    POST and GET for same path grouped together). Handler method names should
    be used for route names, so they're easy to use in other parts of the
    application.
    Note:: if using variable resources (such as {schema}), add
    specific ones on top of more generic ones.
    """
    server = web.Application()
    rest_handler = RESTApiHandler()
    submission_handler = SubmissionAPIHandler()
    api_routes = [
        web.get('/objects', rest_handler.get_objects),
        web.get('/object/{schema}/{accessionId}', rest_handler.get_object),
        web.get('/object/{schema}', rest_handler.query_objects),
        web.post('/object/{schema}', rest_handler.post_object),
        web.post('/submit', submission_handler.submit),
        web.post('/validate', submission_handler.validate)
    ]
    server.router.add_routes(api_routes)
    if frontend_static_files.exists():
        static_handler = StaticHandler(frontend_static_files)
        frontend_routes = [
            web.static('/static', static_handler.setup_static()),
            web.get('/{path:.*}', static_handler.frontend),
        ]
        server.router.add_routes(frontend_routes)
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
