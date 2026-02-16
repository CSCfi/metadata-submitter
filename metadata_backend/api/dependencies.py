"""FastAPI endpoint dependencies."""

from typing import Annotated

from fastapi import Depends, Path
from starlette.requests import Request

from ..api.models.models import User
from ..conf.conf import DEPLOYMENT_CSC, DEPLOYMENT_NBIS
from ..conf.deployment import deployment_config
from .exceptions import SystemException
from .models.app import request_state
from .models.submission import SubmissionWorkflow


def get_user(request: Request) -> User:
    """Get authorized user as a FastAPI dependency."""
    return request_state(request).user


def get_workflow() -> SubmissionWorkflow:
    """Get deployment-specific workflow."""

    if deployment_config().DEPLOYMENT == DEPLOYMENT_CSC:
        return SubmissionWorkflow.SD

    if deployment_config().DEPLOYMENT == DEPLOYMENT_NBIS:
        return SubmissionWorkflow.BP

    raise SystemException("No workflow specified for {deployment_config().DEPLOYMENT} deployment")


# Type aliases
#

UserDependency = Annotated[User, Depends(get_user)]
WorkflowDependency = Annotated[SubmissionWorkflow, Depends(get_workflow)]
SubmissionIdPathParam = Annotated[str, Path(alias="submissionId", description="The submission ID")]
SubmissionIdOrNamePathParam = Annotated[str, Path(alias="submissionId", description="The submission ID or name")]
