"""FastAPI endpoint error handing."""

import traceback
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette import status
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..api.exceptions import AppException, UserExceptions
from ..helpers.logger import LOG


def problem_response(request: Request, status_code: int, detail: str, errors: Any | None = None) -> JSONResponse:
    """Create RFC 7807 formatted problem JSON response."""
    return JSONResponse(
        status_code=status_code,
        content=problem_json(status_code=status_code, detail=detail, url=request.url, errors=errors),
        headers={"content-type": "application/problem+json"},
    )


def problem_json(status_code: int, detail: str, url: URL, errors: Any | None = None) -> dict[str, Any]:
    """Create RFC 7807 formatted problem JSON."""

    problem = {
        "type": "about:blank",
        "title": HTTPStatus(status_code).phrase,
        "detail": detail,
        "status": status_code,
        "instance": url.path,
    }

    if errors:
        problem["errors"] = errors

    return problem


def _format_exception(exc: Exception) -> str:
    """
    Return the full stack trace of an exception as a string.

    :param exc: The exception instance.
    :return: Full stack trace as a string.
    """
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers to format errors as RFC 7807 formatted problem JSON."""

    # Handle FastAPI HTTPException.
    #
    @app.exception_handler(HTTPException)
    async def fastapi_exception_handler(request: Request, exc: HTTPException) -> Response:
        if exc.status_code in {400, 401, 403, 404, 405, 415, 422, 502, 504}:
            LOG.error(
                "HTTP '%r' request to '%r' raised an HTTP '%d' exception.",
                request.method,
                request.url.path,
                exc.status_code,
            )
            return problem_response(request, exc.status_code, str(exc.detail))

        # Return others errors as 500 and hide error details.
        LOG.error(
            "HTTP '%r' request to %r raised an unexpected HTTP '%d' exception:\n%s",
            request.method,
            request.url.path,
            exc.status_code,
            _format_exception,
        )
        return problem_response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected HTTP error")

    def pydantic_problem_response(request: Request, exc: RequestValidationError | ValidationError) -> JSONResponse:
        errors = [{"field": ".".join(map(str, err["loc"])), "message": err["msg"]} for err in exc.errors()]
        return problem_response(request, status.HTTP_400_BAD_REQUEST, "Validation error", errors)

    # Handle FastAPI RequestValidationError.
    #
    @app.exception_handler(RequestValidationError)
    async def fastapi_validation_error_handler(request: Request, exc: RequestValidationError) -> Response:
        LOG.error("HTTP '%r' request to '%r' raised a RequestValidationError.", request.method, request.url.path)
        return pydantic_problem_response(request, exc)

    # Handle Pydantic ValidationError.
    #
    @app.exception_handler(ValidationError)
    async def pydantic_validation_error_handler(request: Request, exc: ValidationError) -> Response:
        LOG.error("HTTP '%r' request to '%r' raised a ValidationError.", request.method, request.url.path)
        return pydantic_problem_response(request, exc)

    # Handle AppExceptions.
    #
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> Response:
        LOG.error("HTTP '%r' request to '%r' raised a AppException.", request.method, request.url.path)
        if isinstance(exc, UserExceptions):
            return problem_response(request, status.HTTP_400_BAD_REQUEST, "User error", exc.messages)
        else:
            return problem_response(request, exc.status_code, str(exc))

    # Handle unexpected exceptions.
    #
    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> Response:
        LOG.error(
            "HTTP '%r' request to '%r' raised an unexpected exception:\n%s",
            request.method,
            request.url.path,
            _format_exception(exc),
        )
        return problem_response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected error")
