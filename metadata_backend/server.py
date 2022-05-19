"""Functions to launch backend server."""

import asyncio
import secrets
import time

import uvloop
from aiohttp import web
from cryptography.fernet import Fernet

from .api.auth import AccessHandler
from .api.handlers.restapi import RESTAPIHandler
from .api.handlers.static import StaticHandler
from .api.handlers.submission import SubmissionAPIHandler
from .api.handlers.object import ObjectAPIHandler
from .api.handlers.xml_submission import XMLSubmissionAPIHandler
from .api.handlers.template import TemplatesAPIHandler
from .api.handlers.user import UserAPIHandler
from .api.health import HealthHandler
from .api.middlewares import check_login, http_error_handler
from .conf.conf import aai_config, create_db_client, frontend_static_files
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
    LOG.debug("Removed session")


async def startup(server: web.Application) -> None:
    """Add startup web server state configuration."""
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
    server.on_startup.append(startup)

    server.middlewares.append(http_error_handler)
    server.middlewares.append(check_login)
    _schema = RESTAPIHandler()
    _object = ObjectAPIHandler()
    _submission = SubmissionAPIHandler()
    _user = UserAPIHandler()
    _xml_submission = XMLSubmissionAPIHandler()
    _template = TemplatesAPIHandler()
    api_routes = [
        # retrieve schema and informations about it
        web.get("/schemas", _schema.get_schema_types),
        web.get("/schemas/{schema}", _schema.get_json_schema),
        # metadata objects operations
        web.get("/objects/{schema}", _object.query_objects),
        web.post("/objects/{schema}", _object.post_object),
        web.get("/objects/{schema}/{accessionId}", _object.get_object),
        web.put("/objects/{schema}/{accessionId}", _object.put_object),
        web.patch("/objects/{schema}/{accessionId}", _object.patch_object),
        web.delete("/objects/{schema}/{accessionId}", _object.delete_object),
        # drafts objects operations
        web.post("/drafts/{schema}", _object.post_object),
        web.get("/drafts/{schema}/{accessionId}", _object.get_object),
        web.put("/drafts/{schema}/{accessionId}", _object.put_object),
        web.patch("/drafts/{schema}/{accessionId}", _object.patch_object),
        web.delete("/drafts/{schema}/{accessionId}", _object.delete_object),
        # template objects operations
        web.get("/templates", _template.get_templates),
        web.post("/templates/{schema}", _template.post_template),
        web.get("/templates/{schema}/{accessionId}", _template.get_template),
        web.patch("/templates/{schema}/{accessionId}", _template.patch_template),
        web.delete("/templates/{schema}/{accessionId}", _template.delete_template),
        # submissions/submissions operations
        web.get("/submissions", _submission.get_submissions),
        web.post("/submissions", _submission.post_submission),
        web.get("/submissions/{submissionId}", _submission.get_submission),
        web.put("/submissions/{submissionId}/doi", _submission.put_submission_doi),
        web.patch("/submissions/{submissionId}", _submission.patch_submission),
        web.delete("/submissions/{submissionId}", _submission.delete_submission),
        # publish submissions
        web.patch("/publish/{submissionId}", _submission.publish_submission),
        # users operations
        web.get("/users/{userId}", _user.get_user),
        web.delete("/users/{userId}", _user.delete_user),
        # submit
        web.post("/submit", _xml_submission.submit),
        # validate
        web.post("/validate", _xml_submission.validate),
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
    server["db_client"] = create_db_client()
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
