# DataCite service handler patches.

from unittest.mock import AsyncMock, patch

from metadata_backend.services.datacite_service import DataciteServiceHandler


def patch_datacite_create_draft_doi(doi: str):
    return patch.object(DataciteServiceHandler, "create_draft_doi", new=AsyncMock(return_value=doi))


def patch_datacite_publish():
    return patch.object(DataciteServiceHandler, "publish", new=AsyncMock(return_value=None))
