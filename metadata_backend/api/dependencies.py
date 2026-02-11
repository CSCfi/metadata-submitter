"""FastAPI endpoint dependencies."""

from typing import Annotated

from fastapi import Depends, Path
from starlette.requests import Request

from ..api.models.models import User
from .models.app import request_state


def get_user(request: Request) -> User:
    """Get authorized user as a FastAPI dependency."""
    return request_state(request).user


# Type aliases
#

UserDependency = Annotated[User, Depends(get_user)]
SubmissionIdPathParam = Annotated[str, Path(alias="submissionId", description="The submission ID")]
SubmissionIdOrNamePathParam = Annotated[str, Path(alias="submissionId", description="The submission ID or name")]
