# Metax service handler patches.

from unittest.mock import AsyncMock, patch

from metadata_backend.services.metax_service import MetaxServiceHandler


def patch_metax_create_draft_dataset(metax_id: str):
    return patch.object(MetaxServiceHandler, "create_draft_dataset", new=AsyncMock(return_value=metax_id))


def patch_metax_update_dataset_metadata():
    return patch.object(MetaxServiceHandler, "update_dataset_metadata", new=AsyncMock(return_value=None))


def patch_metax_update_dataset_description():
    return patch.object(MetaxServiceHandler, "update_dataset_description", new=AsyncMock(return_value=None))


def patch_metax_publish_dataset():
    return patch.object(MetaxServiceHandler, "publish_dataset", new=AsyncMock(return_value=None))
