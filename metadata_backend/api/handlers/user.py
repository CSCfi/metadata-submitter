"""User API handler."""

from ...api.dependencies import UserDependency
from ..models.models import User
from .restapi import RESTAPIHandler


class UserAPIHandler(RESTAPIHandler):
    """User API handler."""

    async def get_user(self, user: UserDependency) -> User:
        """Get user information."""

        return User(
            user_id=user.user_id,
            user_name=user.user_name,
            projects=await self._services.project.get_user_projects(user.user_id),
        )
