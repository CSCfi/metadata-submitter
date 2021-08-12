"""Functions to launch backend server."""

import asyncio

import uvloop
from aiohttp import web
from cryptography.fernet import Fernet
import secrets
import time

from .api.handlers import (
    RESTAPIHandler,
    StaticHandler,
    SubmissionAPIHandler,
    FolderAPIHandler,
    UserAPIHandler,
    ObjectAPIHandler,
)
from .api.auth import AccessHandler
from .api.middlewares import http_error_handler, check_login
from .api.health import HealthHandler
from .conf.conf import create_db_client, frontend_static_files, aai_config
from .helpers.logger import LOG

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def kill_sess_on_shutdown(app: web.Application) -> None:
    """Kill all open sessions and purge their data when killed."""
    LOG.info("Gracefully shutting down the program at %s", time.ctime())
    while app["Session"].keys():
        key = list(app["Session"].keys())[0]
        LOG.info("Purging session for %s", key)
        # Purge the openstack connection from the server
        app["Session"].pop(key)
        LOG.debug("Purged connection information for %s :: %s", key, time.ctime())
    app["Cookies"] = set({})
    LOG.debug("Removed session")


async def init() -> web.Application:
    """Initialise server and setup routes.

    Routes should be setup by adding similar paths one after the another. (i.e.
    ``POST`` and ``GET`` for same path grouped together). Handler method names should
    be used for route names, so they're easy to use in other parts of the
    application.

    .. note:: if using variable resources (such as ``{schema}``), add
              specific ones on top of more generic ones.

    """
    server = web.Application()
    # Mutable_map handles cookie storage, also stores the object that provides
    # the encryption we use
    server["Crypt"] = Fernet(Fernet.generate_key())
    # Create a signature salt to prevent editing the signature on the client
    # side. Hash function doesn't need to be cryptographically secure, it's
    # just a convenient way of getting ascii output from byte values.
    server["Salt"] = secrets.token_hex(64)
    server["Session"] = {}
    server["Cookies"] = set({})
    server["OIDC_State"] = set({})

    server.middlewares.append(http_error_handler)
    server.middlewares.append(check_login)
    _handler = RESTAPIHandler()
    _object = ObjectAPIHandler()
    _folder = FolderAPIHandler()
    _user = UserAPIHandler()
    _submission = SubmissionAPIHandler()
    api_routes = [
        web.get("/schemas", _handler.get_schema_types),
        web.get("/schemas/{schema}", _handler.get_json_schema),
        web.get("/objects/{schema}/{accessionId}", _object.get_object),
        web.delete("/objects/{schema}/{accessionId}", _object.delete_object),
        web.get("/objects/{schema}", _object.query_objects),
        web.post("/objects/{schema}", _object.post_object),
        web.put("/objects/{schema}/{accessionId}", _object.put_object),
        web.get("/drafts/{schema}/{accessionId}", _object.get_object),
        web.put("/drafts/{schema}/{accessionId}", _object.put_object),
        web.patch("/drafts/{schema}/{accessionId}", _object.patch_object),
        web.patch("/objects/{schema}/{accessionId}", _object.patch_object),
        web.delete("/drafts/{schema}/{accessionId}", _object.delete_object),
        web.post("/drafts/{schema}", _object.post_object),
        web.get("/folders", _folder.get_folders),
        web.post("/folders", _folder.post_folder),
        web.get("/folders/{folderId}", _folder.get_folder),
        web.patch("/folders/{folderId}", _folder.patch_folder),
        web.delete("/folders/{folderId}", _folder.delete_folder),
        web.patch("/publish/{folderId}", _folder.publish_folder),
        web.get("/users/{userId}", _user.get_user),
        web.patch("/users/{userId}", _user.patch_user),
        web.delete("/users/{userId}", _user.delete_user),
        web.post("/submit", _submission.submit),
        web.post("/validate", _submission.validate),
    ]
    server.router.add_routes(api_routes)
    LOG.info("Server configurations and routes loaded")
    _access = AccessHandler(aai_config)
    aai_routes = [
        web.get("/aai", _access.login),
        web.get("/logout", _access.logout),
        web.get("/callback", _access.callback),
    ]
    server.router.add_routes(aai_routes)
    LOG.info("AAI routes loaded")
    _health = HealthHandler()
    health_routes = [
        web.get("/health", _health.get_health_status),
    ]
    server.router.add_routes(health_routes)
    LOG.info("Health routes loaded")
    if frontend_static_files.exists():
        _static = StaticHandler(frontend_static_files)
        frontend_routes = [
            web.static("/static", _static.setup_static()),
            web.get("/{path:.*}", _static.frontend),
        ]
        server.router.add_routes(frontend_routes)
        LOG.info("Frontend routes loaded")
    server["db_client"] = await create_db_client()
    server.on_shutdown.append(kill_sess_on_shutdown)
    LOG.info("Database client loaded")
    return server


def main() -> None:
    """Launch the server."""
    host = "0.0.0.0"  # nosec
    port = 5430
    web.run_app(init(), host=host, port=port, shutdown_timeout=0)
    LOG.info(f"Started server on {host}:{port}")


if __name__ == "__main__":
    main()
