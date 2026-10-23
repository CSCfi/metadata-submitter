from typing import Any

from metadata_backend.api.models.datacite import Creator, DataCiteMetadata, Publisher
from metadata_backend.api.models.models import Registration
from metadata_backend.api.services.datacite import DataciteService


class MockDataciteService(DataciteService):
    def __init__(self) -> None:
        super().__init__(None)
        self.published: dict[str, Any] | None = None

    async def create_draft_doi(self) -> str:
        return "10.1234/test"

    async def _publish(self, doi: str, data: dict[str, Any]) -> None:
        self.published = data


async def test_publish_adds_submission_id_as_alternate_identifier():
    """Test that the submission id is the value of the local alternate identifier."""
    service = MockDataciteService()
    registration = Registration(
        submissionId="submission-1", title="title", description="description", doi="10.1234/test"
    )
    datacite = DataCiteMetadata(creators=[Creator(name="Creator")], publisher=Publisher(name="Publisher"))

    await service.publish(registration, datacite, "https://discovery.test/submission-1")

    assert service.published["data"]["attributes"]["alternateIdentifiers"] == [
        {"alternateIdentifier": "submission-1", "alternateIdentifierType": "LocalID"}
    ]
