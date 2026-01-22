"""Metax services."""

import re
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic_string_url import AnyUrl
from yarl import URL

from ...helpers.logger import LOG
from ..exceptions import UserException
from ..models.datacite import (
    Contributor,
    Creator,
    DataCiteMetadata,
    Date,
    FundingReference,
    GeoLocation,
    Publisher,
    Subject,
)
from ..models.metax import (
    Actor,
    FieldOfScience,
    Funder,
    Funding,
    Language,
    MetaxFields,
    Organization,
    Person,
    Project,
    ReferenceLocation,
    Roles,
    Spatial,
    Temporal,
    Url,
)
from ..resource.metax import METAX_MAPPING_GEO_LOCATIONS, METAX_MAPPING_LANGUAGES
from .ror import RorService


class MetaxService(ABC):
    """Metax service."""

    @abstractmethod
    async def get_fields_of_science(self) -> list[FieldOfScience]:
        """
        Get Metax fields of science.

        :return: The Metax fields of science.
        """

    async def get_field_of_science(self, subject: Subject) -> FieldOfScience | None:
        """
        Get Metax fields of science from DataCite subject.

        :param subject: DataCite subject.
        :return: The Metax fields of science or None if not found.
        """

        fields = await self.get_fields_of_science()

        # Search field of science url from subject.valueUrl and subject.subject.
        for field in fields:
            field_of_science = None
            if subject.valueUri is not None:
                field_of_science = self._get_field_of_science_from_url(str(subject.valueUri), field)
            if not field_of_science:
                if subject.subject is not None:
                    field_of_science = self._get_field_of_science_from_url(str(subject.subject), field)
            if field_of_science:
                return field

        # Search field of science code from DataCite subject.subject.
        for field in fields:
            field_of_science = self._get_field_of_science_from_code(subject.subject, field)
            if field_of_science:
                return field

        # Search field of science label from DataCite subject.subject.
        for field in fields:
            field_of_science = self._get_field_of_science_from_label(subject.subject, field)
            if field_of_science:
                return field

        # Search field of science format (e.g '111 - Mathematics') from DataCite subject.subject.
        for field in fields:
            field_of_science = self._get_field_of_science_from_ui(subject.subject, field)
            if field_of_science:
                return field

        return None

    @staticmethod
    def _get_field_of_science_from_url(text: str, field: FieldOfScience) -> FieldOfScience | None:
        try:
            url = URL(text)
            field_url = URL(str(field.url))
        except ValueError:
            return None

        if (
            url.host
            and field_url.host
            and url.path
            and field_url.path
            and url.host.lower() == field_url.host.lower()
            and url.path.lower().rstrip("/") == field_url.path.lower().rstrip("/")
        ):
            return field
        return None

    @staticmethod
    def _get_field_of_science_from_code(text: str, field: FieldOfScience) -> FieldOfScience | None:
        normalized_text = MetaxService._normalize(text)
        normalized_code = MetaxService._normalize(field.code)

        # Exact match (e.g. "ta111").
        if normalized_code == normalized_text:
            return field
        # Numeric match (e.g. "111" -> "ta111").
        if normalized_text.isdigit() and normalized_code.endswith(normalized_text):
            return field

        return None

    @staticmethod
    def _get_field_of_science_from_label(text: str, field: FieldOfScience) -> FieldOfScience | None:
        normalized_text = MetaxService._normalize(text)
        for label in field.pref_label.values():
            if MetaxService._normalize(label) == normalized_text:
                return field

        return None

    @staticmethod
    def _get_field_of_science_from_ui(text: str, field: FieldOfScience) -> FieldOfScience | None:
        match = re.match(r"^\s*(\d+)\s*-\s*(.+)$", text)
        if match:
            field_of_science = MetaxService._get_field_of_science_from_code(match.group(1), field)
            if field_of_science:
                return field

            field_of_science = MetaxService._get_field_of_science_from_label(match.group(2), field)
            if field_of_science:
                return field

        return None

    @staticmethod
    def _normalize(value: str) -> str:
        """Normalize text for case- and punctuation-insensitive comparison."""
        return re.sub(r"[^\w]", "", value.lower())


class MetaxMapper:
    """Map DataCite metadata to Metax metadata."""

    def __init__(self, metax_service: MetaxService, ror_service: RorService) -> None:
        """
        Map DataCite metadata to Metax metadata.

        :param metax_service: The Metax service.
        :param ror_service: the ROR service.
        """

        self._metax_service = metax_service
        self._ror_service = ror_service

    async def map_metadata(self, metax_metadata: MetaxFields, datacite_metadata: DataCiteMetadata) -> MetaxFields:
        """Map DataCite metadata to Metax metadata.

        :param metax_metadata: existing Metax metadata
        :param datacite_metadata: DataCite metadata
        :returns: Metax metadata.
        """
        LOG.info("Mapping DataCite metadata to Metax metadata: %r.", datacite_metadata)

        await self._map_actors(datacite_metadata.creators, Roles.creator, metax_metadata)
        await self._map_publisher(datacite_metadata.publisher, metax_metadata)
        self._map_issued(metax_metadata)
        await self._map_projects(datacite_metadata.publisher, datacite_metadata.fundingReferences, metax_metadata)

        if datacite_metadata.contributors:
            await self._map_actors(datacite_metadata.contributors, Roles.contributor, metax_metadata)

        if datacite_metadata.dates:
            self._map_temporal(datacite_metadata.dates, metax_metadata)

        if datacite_metadata.geoLocations:
            self._map_spatial(datacite_metadata.geoLocations, metax_metadata)

        if datacite_metadata.language:
            self._map_language(datacite_metadata.language, metax_metadata)

        if datacite_metadata.subjects:
            await self._map_field_of_science_and_keyword(datacite_metadata.subjects, metax_metadata)

        return metax_metadata

    async def _map_actors(
        self, people: list[Creator] | list[Contributor], role: str, metax_metadata: MetaxFields
    ) -> None:
        """
        Map DataCite creators or contributors to Metax actors.

        :param people: DataCite creators or contributors.
        :param role: Metax role.
        :param metax_metadata: Metax metadata.
        """
        for p in people:
            if not p.affiliation:
                raise ValueError("Affiliation is required to map a Metax Actor.")

            # Metax supports only one organization.
            affiliation = p.affiliation[0]
            # Check that the ROR organisation exists and get organisation identifier and preferred name.
            affiliation.affiliationIdentifier, affiliation.name = await self._map_organization(affiliation.name)
            organization = Organization(
                pref_label=affiliation.name, external_identifier=affiliation.affiliationIdentifier
            )

            external_identifier = None
            if p.nameIdentifiers:
                # Metax supports only one nameIdentifier.
                external_identifier = p.nameIdentifiers[0].nameIdentifier
            person = Person(name=p.name, external_identifier=external_identifier)
            actor = Actor(organization=organization, roles=[role], person=person)
            metax_metadata.actors.append(actor)

    async def _map_publisher(self, publisher: Publisher, metax_metadata: MetaxFields) -> None:
        """Map Datacite publisher to Metax actor with role Publisher.

        :param publisher: DataCite publisher.
        :param metax_metadata: Metax metadata.
        """

        # Check that the ROR organisation exists and get organisation identifier and preferred name.
        publisher.publisherIdentifier, publisher.name = await self._map_organization(publisher.name)
        organization = Organization(pref_label=publisher.name, external_identifier=publisher.publisherIdentifier)
        actor = Actor(organization=organization, roles=[Roles.publisher])
        metax_metadata.actors.append(actor)

    async def _map_field_of_science_and_keyword(self, subjects: list[Subject], metax_metadata: MetaxFields) -> None:
        """
        Map Datacite subjects to Metax fields of science and keywords.

        :param subjects: DataCite subjects
        :param metax_metadata: Metax metadata.
        :raises UserException: If a subject contains an invalid OKM subject code.
        """

        for subject in subjects:
            # Get Metax field of science from DataCite subject.
            field_of_science = await self._metax_service.get_field_of_science(subject)

            if field_of_science:
                # Subject was a Metax field of science.
                metax_metadata.field_of_science.append(Url(url=field_of_science.url))
                metax_metadata.keyword.append(field_of_science.label)
            else:
                # Subject was not a Metax field of science.
                metax_metadata.keyword.append(subject.subject)

        if not metax_metadata.keyword:
            raise ValueError("At least one Metax keyword is required.")

    @staticmethod
    def _map_issued(metax_metadata: MetaxFields) -> None:
        """Set Metax issued date to the publish date.

        :param metax_metadata: Metax metadata.
        """

        metax_metadata.issued = datetime.now().strftime("%Y-%m-%d")

    def _map_temporal(self, dates: list[Date], metax_metadata: MetaxFields) -> None:
        """Map DataCite dates to Metax temporal.

        :param dates: Datacite dates
        :param metax_metadata: Metax metadata.
        """

        for date in dates:
            if date.dateType == "Other":
                # The date value can be either a single data or a data range. A data range
                # has two dates separated by /.
                date_list = [d.strip() for d in date.date.split("/") if d.strip()]
                if len(date_list) == 1:
                    metax_metadata.temporal.append(Temporal(start_date=self._to_valid_date(date_list[0])))
                elif len(date_list) == 2:
                    metax_metadata.temporal.append(
                        Temporal(
                            start_date=self._to_valid_date(date_list[0]), end_date=self._to_valid_date(date_list[1])
                        )
                    )
                else:
                    raise ValueError(f"Invalid Metax temporal date format: {date.date}")

    @staticmethod
    def _map_language(language: str, metax_metadata: MetaxFields) -> None:
        """Map DataCite language to Metax language.

        :param language: DataCite language
        :param metax_metadata: Metax metadata.
        """

        if language not in METAX_MAPPING_LANGUAGES:
            raise UserException(f"Invalid language: {language}")

        metax_metadata.language = [Language(url=METAX_MAPPING_LANGUAGES[language].uri)]

    async def _map_projects(
        self, publisher: Publisher, funding_references: list[FundingReference] | None, metax_metadata: MetaxFields
    ) -> None:
        """
        Map DataCite publisher and funding references to Metax project.

        :param publisher: DataCite publisher.
        funding_references: DataCite funding references.
        :param metax_metadata: Metax metadata.
        """

        participating_organizations = []
        fundings = []

        # Check that the ROR organisation exists and get organisation identifier and preferred name.
        publisher.publisherIdentifier, publisher.name = await self._map_organization(publisher.name)
        participating_organizations.append(
            Organization(pref_label=publisher.name, external_identifier=publisher.publisherIdentifier)
        )

        for fundingRef in funding_references:
            # Check that the ROR organisation exists and get organisation identifier and preferred name.
            fundingRef.funderIdentifier, fundingRef.funderName = await self._map_organization(fundingRef.funderName)
            funder = Funder(
                organization=Organization(
                    pref_label=fundingRef.funderName, external_identifier=fundingRef.funderIdentifier
                )
            )
            funding_identifier = fundingRef.awardNumber
            fundings.append(Funding(funder=funder, funding_identifier=funding_identifier))

        metax_metadata.projects.append(
            Project(
                participating_organizations=participating_organizations,
                funding=fundings,
            )
        )

    @staticmethod
    def _map_spatial(locations: list[GeoLocation], metax_metadata: MetaxFields) -> None:
        """Map DataCite geolocation to Metax spatial.

        :param locations: Datacite geoLocations.
        :param metax_metadata: Metax metadata.
        """

        for location in locations:
            geographic_name = location.geoLocationPlace

            # geoLocationPlace is mapped to YSO ontology URL.
            reference_url = [
                loc.uri
                for loc in METAX_MAPPING_GEO_LOCATIONS
                if "en" in loc.pref_label and loc.pref_label["en"] == geographic_name
            ]
            reference = ReferenceLocation(url=reference_url[0]) if reference_url[0] else None
            custom_wkt = []

            #  geoLocationPoint, geoLocationBox and geolocationPolygon are mapped to custom_wkt.

            if location.geoLocationPoint is not None:
                lon = location.geoLocationPoint.pointLongitude
                lat = location.geoLocationPoint.pointLatitude
                custom_wkt.append(f"POINT ({lon} {lat})")
            if location.geoLocationBox is not None:
                box = location.geoLocationBox
                west_lon = box.westBoundLongitude
                east_lon = box.eastBoundLongitude
                north_lat = box.northBoundLatitude
                south_lat = box.southBoundLatitude
                custom_wkt.append(
                    (
                        f"POLYGON(({west_lon} {south_lat}, {east_lon} {south_lat}, {east_lon} {north_lat}, "
                        f"{west_lon} {north_lat}, {west_lon} {south_lat}))"
                    )
                )
            if location.geoLocationPolygon is not None:
                pol_points = []
                in_pol_points = []

                for pol in location.geoLocationPolygon:
                    if pol.polygonPoint is not None:
                        pol_points.append((pol.polygonPoint.pointLongitude, pol.polygonPoint.pointLatitude))
                    if pol.inPolygonPoint is not None:
                        in_pol_points.append((pol.inPolygonPoint.pointLongitude, pol.inPolygonPoint.pointLatitude))

                # Polygon should be closed
                if pol_points[0] != pol_points[-1]:
                    pol_points.append(pol_points[0])

                pol_str = ", ".join(f"{lon} {lat}" for lon, lat in pol_points)
                in_pol_str = ", ".join(f"{lon} {lat}" for lon, lat in in_pol_points)

                custom_wkt.extend([f"POLYGON(({pol_str}))", f"POINT({in_pol_str})"])

            spatial = Spatial(geographic_name=geographic_name, reference=reference, custom_wkt=custom_wkt)
            metax_metadata.spatial.append(spatial)

    @staticmethod
    def _to_valid_date(date: str) -> str:
        """
        Convert Datacite date to Metax date.

        - Datacite supports dates in YYYY, YYYY-MM-DD, YYYY-MM-DDThh:mm:ssTZD
        or any formats described in https://www.w3.org/TR/NOTE-datetime.
        - Datacite date range follows https://www.ukoln.ac.uk/metadata/dcmi/collection-RKMS-ISO8601/
        - Metax supports dates in YYYY-MM-DD format.

        :raises ValueError: If input date can't be mapped to Metax.
        """
        date_value = date.strip()

        # Case YYYY
        if len(date_value) == 4 and date_value.isdigit():
            return date_value + "-01-01"
        # Case YYYY-MM
        try:
            return datetime.strptime(date_value, "%Y-%m").strftime("%Y-%m-01")
        except ValueError:
            pass
        # Case YYYY-MM-DD
        try:
            return datetime.strptime(date_value, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass

        # Case ISO-8601
        try:
            iso_value = date_value.replace("Z", "+00:00")
            date_time = datetime.fromisoformat(iso_value)
            return date_time.date().isoformat()
        except ValueError:
            pass

        raise ValueError(f"Invalid date value: {date_value}")

    async def _map_organization(self, organisation: str) -> tuple[AnyUrl, str]:
        """
        Map organisation name to ROR organization identifier and preferred name.

        :param organisation: The organisation name.
        :return: The ROR organization identifier and preferred name.
        :raises UserException: If the ROR organization could not be found.
        """

        result = await self._ror_service.get_organisation(organisation.strip())

        if result is None:
            raise UserException(f"Invalid ROR organization name: {organisation}")

        return result
