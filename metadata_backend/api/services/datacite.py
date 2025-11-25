"""Datacite Service."""

from abc import ABC, abstractmethod
from typing import Any, cast

from ...api.services.publish import format_subject_okm_field_of_science
from ..exceptions import UserException
from ..json import to_json_dict
from ..models.datacite import AlternateIdentifier, DataCiteMetadata, Description, Title
from ..models.models import Registration


class DataciteService(ABC):
    """Datacite Service."""

    @abstractmethod
    async def create_draft_doi(self) -> str:
        """Create a draft DOI.

        :returns: The draft DOI.
        """

    @abstractmethod
    async def _publish(self, doi: str, data: dict[str, Any]) -> None:
        """Publish a draft DOI with DataCite metadata.

        :param doi: The draft DOI
        :param data: The request data
        """

    async def publish(
        self,
        registration: Registration,
        datacite: DataCiteMetadata,
        discovery_url: str,
        *,
        require_okm_field_of_science: bool = False,
        publish: bool = True,
    ) -> dict[str, Any]:
        """Publish a draft DOI with DataCite metadata.

        :param registration: The registration.
        :param datacite: The DataCite metadata
        :param discovery_url: The discovery URL
        :param require_okm_field_of_science: Require OKM field of science
        :param publish: If True then publish the data. If false do not change the status.
        :return: The request body.
        """

        # Add accession number.
        if datacite.alternateIdentifiers is None:
            datacite.alternateIdentifiers = []
        datacite.alternateIdentifiers.append(
            AlternateIdentifier(
                alternateIdentifier="Local accession number", alternateIdentifierType=registration.submissionId
            )
        )

        # Set title.
        datacite.titles = []
        datacite.titles.append(Title(title=registration.title))

        # Set description.
        datacite.descriptions = []
        datacite.descriptions.append(Description(description=registration.description))

        data: dict[str, Any] = {
            "data": {
                "type": "dois",
                "attributes": {
                    "doi": registration.doi,
                    **({"event": "publish"} if publish else {}),
                    "url": discovery_url,
                },
            },
        }

        if require_okm_field_of_science:
            if datacite.subjects is None:
                raise UserException("Datacite's subject is required.")
            format_subject_okm_field_of_science(datacite.subjects)

        cast(dict[str, Any], data["data"]["attributes"]).update(to_json_dict(datacite))

        await self._publish(registration.doi, data)

        return data
