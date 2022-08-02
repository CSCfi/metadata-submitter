"""Middleware methods for server."""
import time
from http import HTTPStatus

import aiohttp_session
import ujson
from aiohttp import web
from yarl import URL

from ..conf.conf import API_PREFIX, OIDC_ENABLED
from ..helpers.logger import LOG
from .handlers.restapi import RESTAPIHandler
from .operators import (
    Operator,
    ProjectOperator,
    SubmissionOperator,
    UserOperator,
    XMLOperator,
)

HTTP_ERROR_MESSAGE = "HTTP %r request to %r raised an HTTP %d exception."
HTTP_ERROR_MESSAGE_BUG = "HTTP %r request to %r raised an HTTP %d exception. This IS a bug."


@web.middleware
async def http_error_handler(req: web.Request, handler: aiohttp_session.Handler) -> web.StreamResponse:
    """Middleware for handling exceptions received from the API methods.

    :param req: A request instance
    :param handler: A request handler
    :raises: Reformatted HTTP Exceptions
    :returns: Successful requests unaffected
    """
    c_type = "application/problem+json"
    try:
        response = await handler(req)
        return response
    except (web.HTTPSuccessful, web.HTTPRedirection):  # pylint: disable=try-except-raise
        # Catches 200s and 300s
        raise
    except web.HTTPError as error:
        # Catch 400s and 500s
        LOG.error(HTTP_ERROR_MESSAGE, req.method, req.path, error.status)
        problem = _json_problem(error, req.url)
        LOG.debug("Response payload is %r", problem)

        if error.status in {400, 401, 403, 404, 415, 422, 502, 504}:
            error.content_type = c_type
            error.text = problem
            raise error
        LOG.exception(HTTP_ERROR_MESSAGE_BUG, req.method, req.path, error.status)
        raise web.HTTPInternalServerError(text=problem, content_type=c_type)
    except Exception as exc:
        # We don't expect any other errors, so we log it and return a nice message instead of letting server crash
        LOG.exception("HTTP %r request to %r raised an unexpected exception. This IS a bug.", req.method, req.path)
        exception = web.HTTPInternalServerError(reason="Server ran into an unexpected error", content_type=c_type)
        problem = _json_problem(exception, req.url)
        exception.text = problem
        raise exception from exc


@web.middleware
async def check_session(req: web.Request, handler: aiohttp_session.Handler) -> web.StreamResponse:
    """Raise on expired sessions or invalid sessions.

    :param req: A request instance
    :param handler: A request handler
    :raises: Reformatted HTTP Exceptions
    :returns: Successful requests unaffected
    """
    if OIDC_ENABLED:
        try:
            session = await aiohttp_session.get_session(req)
            LOG.debug(f"session: {session}")

            if session.empty:
                session.invalidate()
                raise _unauthorized("You must provide authentication to access SD-Submit API.")

            if not all(k in session for k in ["access_token", "user_info", "at", "oidc_state"]):
                LOG.error(f"Checked session parameter, session is invalid {session}. This could be a bug or abuse.")
                session.invalidate()
                raise _unauthorized("Invalid session, authenticate again.")

            if session["at"] + 28800 < time.time():
                session.invalidate()
                raise _unauthorized("Token expired.")

        except KeyError as error:
            reason = f"No valid session. A session was invalidated due to invalid token. {error}"
            LOG.info(reason)
            raise _unauthorized(reason) from error
        except web.HTTPException:
            # HTTPExceptions are processed in the other middleware
            raise
        except Exception as error:
            reason = f"No valid session. A session was invalidated due to another reason: {error}"
            LOG.exception("No valid session. A session was invalidated due to another reason")
            raise _unauthorized(reason) from error

    return await handler(req)


@web.middleware
async def protect_published(req: web.Request, handler: aiohttp_session.Handler) -> web.StreamResponse:
    """Prevent modifying published objects and submissions.

    - For all requests: Check user has access rights
    - For modifying requests: Check resource is not published
    - Injects the target object or submission in the request object.

    :param req: A request instance
    :param handler: A request handler
    :raises: HTTPBadRequest when the resource is in published state
    :returns: Successful requests with injected object / submission
    """
    if req.path.split("/")[2] not in {"objects", "drafts", "submissions", "publish"}:
        # No checks for other endpoints
        return await handler(req)

    session = await aiohttp_session.get_session(req)

    db_client = req.app["db_client"]

    user_op = UserOperator(db_client)
    submission_op = SubmissionOperator(db_client)
    current_user = session["user_info"]
    user = await user_op.read_user(current_user)
    user_id = user["userId"]

    content = {}
    req_format = req.query.get("format", "json").lower()
    if req.body_exists and ("json" in req.content_type and req_format == "json"):
        content = await RESTAPIHandler.get_data(req)
        req["content"] = content

    project_id = req.query.get("projectId", "")
    if project_id == "" and isinstance(content, dict):
        project_id = content.get("projectId", "")

    if project_id:
        # Check that project exists
        project_op = ProjectOperator(db_client)
        await project_op.check_project_exists(project_id)

        # Check that user is affiliated with project
        user_has_project = await user_op.check_user_has_project(project_id, user_id)
        if not user_has_project:
            reason = f"user {user_id} is not affiliated with project {project_id}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

    # We get accessionID only when changing an object directly. Those requests don't come with submissionID
    # Object creation requests do come with schema and submissionID
    schema = req.match_info.get("schema", "")

    if submission_id := req.match_info.get("submissionId", "") or req.query.get("submission", ""):
        await submission_op.check_submission_exists(submission_id)
        await RESTAPIHandler.handle_check_ownership(req, "submissions", submission_id)
        submission = await submission_op.read_submission(submission_id)
        req["submission"] = submission
        project_id = submission["projectId"]
        if submission.get("published", False) and req.method in {"PUT", "POST", "PATCH", "DELETE"}:
            reason = (
                f"User {user_id} attempted to {req.method} a published submission '{submission_id}' "
                f"from project {project_id}"
            )
            if schema:
                reason = (
                    f"User {user_id} attempted to {req.method} the schema '{schema}' of "
                    f"a published submission '{submission_id}' from project {project_id}"
                )
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    if schema:
        RESTAPIHandler.check_schema_exists(schema)
        collection = f"draft-{schema}" if req.path.startswith(f"{API_PREFIX}/drafts") else schema
        req["collection"] = collection
        type_collection = f"xml-{collection}" if req_format == "xml" else collection

        if accession_id := req.match_info.get("accessionId", "") or req.query.get("accessionId", ""):
            operator = XMLOperator(db_client) if req_format == "xml" else Operator(db_client)

            await operator.check_exists(collection, accession_id)
            await RESTAPIHandler.handle_check_ownership(req, collection, accession_id)
            exists, object_submission_id, published = await submission_op.check_object_in_submission(
                collection, accession_id
            )
            if not exists:
                reason = f"Object with schema '{schema}' and accessionId '{accession_id}' was not found"
                raise web.HTTPNotFound(reason=reason)
            if published and req.method in {"PUT", "POST", "PATCH", "DELETE"}:
                reason = (
                    f"User {user_id} attempted to {req.method} the object '{accession_id}' with schema '{schema}' of "
                    f"a published submission '{object_submission_id}' from project {project_id}"
                )
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            data, content_type = await operator.read_metadata_object(type_collection, accession_id)
            req["object"] = (data, content_type)

    return await handler(req)


def _unauthorized(reason: str) -> web.HTTPUnauthorized:
    return web.HTTPUnauthorized(headers={"WWW-Authenticate": 'OAuth realm="/", charset="UTF-8"'}, reason=reason)


def _json_problem(exception: web.HTTPError, url: URL, _type: str = "about:blank") -> str:
    """Convert an HTTP exception into a problem detailed JSON object.

    The problem details are in accordance with RFC 7807.
    (https://tools.ietf.org/html/rfc7807)

    :param exception: an HTTPError exception
    :param url: Request URL that caused the exception
    :param _type: Url to a document describing the error
    :returns: Problem detail JSON object as a string
    """
    body = ujson.dumps(
        {
            # Replace type value with an URL to
            # a custom error document when one exists
            "type": _type,
            "title": HTTPStatus(exception.status).phrase,
            "detail": exception.reason,
            "status": exception.status,
            "instance": url.path,  # optional
        },
        escape_forward_slashes=False,
    )
    return body
