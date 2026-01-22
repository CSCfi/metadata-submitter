"""Datacite Service."""

from abc import ABC, abstractmethod
from typing import Any, cast

from pydantic_string_url import AnyUrl

from ..exceptions import UserException
from ..json import to_json_dict
from ..models.datacite import AlternateIdentifier, DataCiteMetadata, Description, Subject, Title
from ..models.models import Registration
from .metax import MetaxService


class DataciteService(ABC):
    """Datacite Service."""

    def __init__(self, metax_service: MetaxService | None):
        self._metax_service = metax_service

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
        require_field_of_science: bool = False,
        publish: bool = True,
    ) -> dict[str, Any]:
        """Publish a draft DOI with DataCite metadata.

        :param registration: The registration.
        :param datacite: The DataCite metadata
        :param discovery_url: The discovery URL
        :param require_field_of_science: Require field of science.
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

        if require_field_of_science:
            if datacite.subjects is None:
                raise UserException("Missing DataCite subjects.")
            await self.map_metax_field_of_science(datacite.subjects)

        cast(dict[str, Any], data["data"]["attributes"]).update(to_json_dict(datacite))

        await self._publish(registration.doi, data)

        return data

    async def map_metax_field_of_science(self, subjects: list[Subject] | None) -> None:
        """
        Map DataCite subject to Metax field of science.

        :param subjects: DataCite subjects.
        """

        if self._metax_service is not None:
            if subjects:
                for subject in subjects:
                    field_of_science = await self._metax_service.get_field_of_science(subject)
                    if field_of_science:
                        subject.subjectScheme = "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus"
                        subject.schemeUri = AnyUrl("http://www.yso.fi/onto/okm-tieteenala/conceptscheme")
                        subject.valueUri = field_of_science.url
                        subject.classificationCode = field_of_science.code
