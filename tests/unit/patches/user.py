from unittest.mock import AsyncMock, patch

from metadata_backend.api.models.models import Project, User
from metadata_backend.api.services.project import ProjectService

MOCK_PROJECT_ID = "1001"
MOCK_USER_ID = "mock-userid"
MOCK_USER_NAME = "mock-username"

patch_verify_authorization = patch(
    "metadata_backend.api.middlewares.verify_authorization",
    new=AsyncMock(return_value=User(user_id=MOCK_USER_ID, user_name=MOCK_USER_NAME)),
)

patch_verify_user_project = patch.object(ProjectService, "verify_user_project", new=AsyncMock(return_value=True))

patch_get_user_projects = patch.object(
    ProjectService, "get_user_projects", new=AsyncMock(return_value=[Project(project_id=MOCK_PROJECT_ID)])
)
