# PID service handler patches.

from unittest.mock import AsyncMock, patch

from metadata_backend.services.pid_service import PIDServiceHandler


def patch_pid_create_draft_doi(doi: str):
    return patch.object(PIDServiceHandler, "create_draft_doi", new=AsyncMock(return_value=doi))


def patch_pid_publish():
    return patch.object(PIDServiceHandler, "publish", new=AsyncMock(return_value=None))
