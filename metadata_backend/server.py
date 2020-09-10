"""Functions to launch backend server."""

import asyncio

import uvloop
from aiohttp import web
from aiohttp_session import setup as session_setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography.fernet import Fernet

from .api.handlers import RESTApiHandler, StaticHandler, SubmissionAPIHandler, AccessHandler
from .api.middlewares import http_error_handler, jwt_authentication
from .conf.conf import create_db_client, frontend_static_files, setup_aai
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
    server = web.Application(middlewares=[http_error_handler, jwt_authentication])
    session_setup(server, EncryptedCookieStorage(Fernet.generate_key()[:32]))
    rest_handler = RESTApiHandler()
    submission_handler = SubmissionAPIHandler()
    api_routes = [
        web.get("/schemas", rest_handler.get_schema_types),
        web.get("/schemas/{schema}", rest_handler.get_json_schema),
        web.get("/objects/{schema}/{accessionId}", rest_handler.get_object),
        web.delete("/objects/{schema}/{accessionId}", rest_handler.delete_object),
        web.get("/objects/{schema}", rest_handler.query_objects),
        web.post("/objects/{schema}", rest_handler.post_object),
        web.get("/drafts/{schema}/{accessionId}", rest_handler.get_object),
        web.put("/drafts/{schema}/{accessionId}", rest_handler.put_object),
        web.patch("/drafts/{schema}/{accessionId}", rest_handler.patch_object),
        web.delete("/drafts/{schema}/{accessionId}", rest_handler.delete_object),
        web.post("/drafts/{schema}", rest_handler.post_object),
        web.get("/folders", rest_handler.get_folders),
        web.post("/folders", rest_handler.post_folder),
        web.get("/folders/{folderId}", rest_handler.get_folder),
        web.patch("/folders/{folderId}", rest_handler.patch_folder),
        web.delete("/folders/{folderId}", rest_handler.delete_folder),
        web.get("/users/{userId}", rest_handler.get_user),
        web.patch("/users/{userId}", rest_handler.patch_user),
        web.delete("/users/{userId}", rest_handler.delete_user),
        web.post("/submit", submission_handler.submit),
        web.post("/validate", submission_handler.validate),
    ]
    server.router.add_routes(api_routes)
    LOG.info("Server configurations and routes loaded")
    if frontend_static_files.exists():
        static_handler = StaticHandler(frontend_static_files)
        frontend_routes = [
            web.static("/static", static_handler.setup_static()),
            web.get("/{path:.*}", static_handler.frontend),
        ]
        server.router.add_routes(frontend_routes)
        LOG.info("Frontend routes loaded")
    server["db_client"] = create_db_client()
    LOG.info("Database client loaded")
    aai_vars = setup_aai()
    access_handler = AccessHandler(aai_vars)
    aai_routes = [
        web.get("/login", access_handler.login),
        web.get("/logout", access_handler.logout),
        web.get("/callback", access_handler.callback),
    ]
    server.router.add_routes(aai_routes)
    LOG.info("AAI routes loaded")
    return server


def main() -> None:
    """Launch the server."""
    host = "0.0.0.0"  # nosec
    port = 5430
    web.run_app(init(), host=host, port=port, shutdown_timeout=0)
    LOG.info(f"Started server on {host}:{port}")


if __name__ == "__main__":
    main()
