"""FastAPI endpoint error handing.

Every error is returned as RFC 7807 problem JSON in one of three shapes, each a model below. The
models are also the error responses documented in the OpenAPI schema by add_error_responses.
"""

import traceback
from http import HTTPStatus
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError
from pydantic.json_schema import models_json_schema
from starlette import status
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..api.exceptions import AppException, UserException, UserExceptions
from ..helpers.logger import LOG

PROBLEM_MEDIA_TYPE = "application/problem+json"

USER_ERROR: Literal["User error"] = "User error"
VALIDATION_ERROR: Literal["Validation error"] = "Validation error"


class Problem(BaseModel):
    """RFC 7807 problem JSON."""

    type: Literal["about:blank"]
    title: str = Field(description="The HTTP status phrase, for example 'Not Found'.")
    detail: str
    status: int = Field(description="The HTTP status code.")
    instance: str = Field(description="The request path.")


class UserErrorProblem(Problem):
    """A user error: the request cannot be completed as sent, and the errors explain why."""

    detail: Literal["User error"]
    errors: list[str] = Field(description="Error messages to show to the user.")


class FieldError(BaseModel):
    """An invalid field."""

    field: str = Field(
        description="The name of the field, with nested field names and list indexes joined with dots. "
        "Empty for an error in the document as a whole."
    )
    message: str = Field(description="The error message.")


class ValidationErrorProblem(Problem):
    """Request parameter or submitted documents field error."""

    detail: Literal["Validation error"]
    errors: list[FieldError] = Field(description="The invalid fields.")


class ServerErrorProblem(Problem):
    """A server or external service error."""

    detail: str = Field(description="The error message.")


def _problem_response(problem: Problem) -> JSONResponse:
    """Create an RFC 7807 problem JSON response."""
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        headers={"content-type": PROBLEM_MEDIA_TYPE},
    )


def _problem_fields(path: str, status_code: int) -> dict[str, Any]:
    """Return the problem fields that every problem shares."""
    return {"type": "about:blank", "title": HTTPStatus(status_code).phrase, "status": status_code, "instance": path}


def user_error_response(request: Request, status_code: int, errors: list[str]) -> JSONResponse:
    """Create a user error response."""
    return _problem_response(
        UserErrorProblem(**_problem_fields(request.url.path, status_code), detail=USER_ERROR, errors=errors)
    )


def validation_error_response(request: Request, exc: RequestValidationError | ValidationError) -> JSONResponse:
    """Create a validation error response."""
    errors = [FieldError(field=".".join(map(str, err["loc"])), message=err["msg"]) for err in exc.errors()]
    return _problem_response(
        ValidationErrorProblem(
            **_problem_fields(request.url.path, status.HTTP_400_BAD_REQUEST), detail=VALIDATION_ERROR, errors=errors
        )
    )


def server_error_response(request: Request, status_code: int, detail: str) -> JSONResponse:
    """Create a server error response."""
    return _problem_response(ServerErrorProblem(**_problem_fields(request.url.path, status_code), detail=detail))


def app_exception_response(request: Request, exc: AppException) -> JSONResponse:
    """Create the response for an application exception, raised in a handler or a middleware."""
    if isinstance(exc, UserExceptions):
        return user_error_response(request, exc.status_code, exc.messages)
    if isinstance(exc, UserException):
        return user_error_response(request, exc.status_code, [str(exc)])
    return server_error_response(request, exc.status_code, str(exc))


def _format_exception(exc: Exception) -> str:
    """
    Return the full stack trace of an exception as a string.

    :param exc: The exception instance.
    :return: Full stack trace as a string.
    """
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers to format errors as RFC 7807 formatted problem JSON."""

    # Handle HTTPException, raised by Starlette for an unknown path or an unsupported method,
    # and by FastAPI and our own code, since FastAPI's HTTPException is a subclass.
    #
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
        if exc.status_code in {400, 401, 403, 404, 405, 415, 422, 502, 504}:
            LOG.error(
                "HTTP '%r' request to '%r' raised an HTTP '%d' exception.",
                request.method,
                request.url.path,
                exc.status_code,
            )
            if exc.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
                response = user_error_response(request, exc.status_code, [str(exc.detail)])
            else:
                response = server_error_response(request, exc.status_code, str(exc.detail))
            # For example, the Allow header of a 405.
            response.headers.update(exc.headers or {})
            return response

        # Return others errors as 500 and hide error details.
        LOG.error(
            "HTTP '%r' request to %r raised an unexpected HTTP '%d' exception:\n%s",
            request.method,
            request.url.path,
            exc.status_code,
            _format_exception(exc),
        )
        return server_error_response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected HTTP error")

    # Handle FastAPI RequestValidationError.
    #
    @app.exception_handler(RequestValidationError)
    async def fastapi_validation_error_handler(request: Request, exc: RequestValidationError) -> Response:
        LOG.error("HTTP '%r' request to '%r' raised a RequestValidationError.", request.method, request.url.path)
        return validation_error_response(request, exc)

    # Handle Pydantic ValidationError.
    #
    @app.exception_handler(ValidationError)
    async def pydantic_validation_error_handler(request: Request, exc: ValidationError) -> Response:
        LOG.error("HTTP '%r' request to '%r' raised a ValidationError.", request.method, request.url.path)
        return validation_error_response(request, exc)

    # Handle AppExceptions.
    #
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> Response:
        if isinstance(exc, UserException):
            LOG.error("HTTP '%r' request to '%r' raised a UserException.", request.method, request.url.path)
        else:
            LOG.error(
                "HTTP '%r' request to '%r' raised a SystemException:\n%s",
                request.method,
                request.url.path,
                _format_exception(exc),
            )
        return app_exception_response(request, exc)

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
        return server_error_response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected error")


ERRORS_DESCRIPTION = """
## Errors

Errors are returned as RFC 7807 problem JSON, in one of the following three shapes:

- User error: detail is "User error", and errors is a list of error messages. The status is 4xx.
- Validation error: detail is "Validation error", and errors is a list of invalid fields,
  with their names and the error message. The status is 400.
- Server error: detail is the error message. The status is 5xx.
"""

_REF_TEMPLATE = "#/components/schemas/{model}"


def add_error_responses(openapi_schema: dict[str, Any]) -> None:
    """
    Document the error responses of every operation in the OpenAPI schema.

    Every operation can return a user error (4XX) or a server error (5XX). An operation with
    parameters or a body can also return a validation error (400). FastAPI documents those
    operations with a 422, which this API never returns, so the 422 is replaced with the 400.

    :param openapi_schema: The OpenAPI schema to change.
    """
    _add_error_schemas(openapi_schema)

    for path, path_item in openapi_schema["paths"].items():
        for operation in path_item.values():
            responses = operation["responses"]
            if "422" in responses:
                del responses["422"]
                responses["400"] = _error_response(
                    "User error or validation error",
                    UserErrorProblem(
                        **_problem_fields(path, status.HTTP_400_BAD_REQUEST),
                        detail=USER_ERROR,
                        errors=["Submission belongs to a different project: 'other_project'"],
                    ),
                    ValidationErrorProblem(
                        **_problem_fields(path, status.HTTP_400_BAD_REQUEST),
                        detail=VALIDATION_ERROR,
                        errors=[FieldError(field="name", message="Field required")],
                    ),
                )
            responses["4XX"] = _error_response(
                "User error",
                UserErrorProblem(
                    **_problem_fields(path, status.HTTP_404_NOT_FOUND),
                    detail=USER_ERROR,
                    errors=["Submission 'abc' not found."],
                ),
            )
            responses["5XX"] = _error_response(
                "Server error",
                ServerErrorProblem(
                    **_problem_fields(path, status.HTTP_502_BAD_GATEWAY), detail="External service error: Metax"
                ),
            )


def _add_error_schemas(openapi_schema: dict[str, Any]) -> None:
    """Add the error models to the OpenAPI schemas, and remove the models of FastAPI's 422 response."""
    schemas = openapi_schema["components"]["schemas"]

    # The JSON schemas of the error models, and of FieldError used in ValidationErrorProblem.
    _, error_schemas = models_json_schema(
        [(model, "serialization") for model in (UserErrorProblem, ValidationErrorProblem, ServerErrorProblem)],
        ref_template=_REF_TEMPLATE,
    )
    schemas.update(error_schemas["$defs"])

    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)


def _error_response(description: str, *examples: Problem) -> dict[str, Any]:
    """
    Return an OpenAPI response with a problem JSON body.

    :param description: The response description.
    :param examples: One example for each model the body may be, shown in Swagger UI.
    :returns: The OpenAPI response.
    """
    refs = [{"$ref": _REF_TEMPLATE.format(model=type(example).__name__)} for example in examples]
    schema = refs[0] if len(refs) == 1 else {"oneOf": refs}
    return {
        "description": description,
        "content": {
            PROBLEM_MEDIA_TYPE: {
                "schema": schema,
                "examples": {example.detail: {"value": example.model_dump()} for example in examples},
            }
        },
    }
