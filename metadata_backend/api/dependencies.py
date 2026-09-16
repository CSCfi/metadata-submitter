"""FastAPI endpoint dependencies."""

from typing import Annotated

import jwt
from fastapi import Depends, Path
from fastapi.security.utils import get_authorization_scheme_param
from starlette.requests import Request

from ..api.models.models import User
from ..conf.conf import DEPLOYMENT_CSC, DEPLOYMENT_NBIS
from ..conf.deployment import deployment_config
from ..conf.sync import sync_config
from ..helpers.logger import LOG
from .exceptions import SystemException, UnauthorizedUserException
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


# The allowlist for algorithms the sync JWT tokens are signed with.
SYNC_TOKEN_ALGORITHM = "ES256"

# How much the clock of the sync client may differ from ours.
SYNC_TOKEN_LEEWAY = 30

# Mandatory sync JWT token claims.
SYNC_TOKEN_CLAIMS = ["iss", "sub", "aud", "iat", "exp"]


def verify_sync(request: Request) -> None:
    """Verify signed bearer JWT sync tokens.

    The sync service client signs the JWT token with its private key.
    This service validates the JWT token using the public key.

    :param request: The request.
    :raises UnauthorizedUserException: if the bearer token verification failed.
    """

    scheme, token = get_authorization_scheme_param(request.headers.get("Authorization"))

    config = sync_config()
    if scheme.lower() != "bearer" or not token or not config.SYNC_CLIENTS:
        raise UnauthorizedUserException("Authorization failed")

    # Every configured public key is tried. This allows the sync client to
    # replace a key while the previous one is still accepted.
    error: jwt.InvalidTokenError | None = None
    for client in config.SYNC_CLIENTS:
        for public_key in client.public_keys:
            try:
                jwt.decode(
                    token,
                    key=public_key,
                    algorithms=[SYNC_TOKEN_ALGORITHM],
                    audience=config.SYNC_AUDIENCE,
                    issuer=client.iss,
                    leeway=SYNC_TOKEN_LEEWAY,
                    options={"require": SYNC_TOKEN_CLAIMS},
                )
                LOG.debug("Sync request authorized for %s.", client.iss)
                return
            except jwt.InvalidSignatureError as ex:
                # Not the key this token was signed with, which is the expected
                # answer from every key but one.
                if error is None:
                    error = ex
            except jwt.InvalidTokenError as ex:
                # A key verified the signature, so this is about the token itself.
                error = ex

    # The specific error is logged but not reported to the caller.
    LOG.info("Sync token verification failed: %s", error)
    raise UnauthorizedUserException("Authorization failed")


# Type aliases
#

UserDependency = Annotated[User, Depends(get_user)]
WorkflowDependency = Annotated[SubmissionWorkflow, Depends(get_workflow)]
SubmissionIdPathParam = Annotated[str, Path(alias="submissionId", description="The submission ID")]
SubmissionIdOrNamePathParam = Annotated[str, Path(alias="submissionId", description="The submission ID or name")]
