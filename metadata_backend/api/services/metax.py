"""Metax services."""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ...helpers.logger import LOG
from ..exceptions import UserException
from ..models.datacite import (
    Contributor,
    Creator,
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
from ..models.submission import SubmissionMetadata
from ..resource.metax import METAX_MAPPING_GEO_LOCATIONS, METAX_MAPPING_LANGUAGES
from ..services.publish import check_subject_format
from .ror import RorService


class MetaxService(ABC):
    """Metax service."""

    @abstractmethod
    async def get_fields_of_science(self) -> list[FieldOfScience]:
        """
        Get Metax fields of science.

        :return: The Metax fields of science.
        """

    async def get_field_of_science(self, text: str) -> FieldOfScience | None:
        fields = await self.get_fields_of_science()

        if not text:
            return None

        def _normalize(value: str) -> str:
            """Case- and punctuation-insensitive comparison."""
            return re.sub(r"[^\w]", "", value.lower())

        norm_text = _normalize(text)

        # Match code.
        for field in fields:
            norm_code = _normalize(field.code)
            # Exact normalized match (e.g. "ta111")
            if norm_code == norm_text:
                return field
            # Numeric suffix match (e.g. "111" -> "ta111").
            if norm_text.isdigit() and norm_code.endswith(norm_text):
                return field

        # Match label.
        for field in fields:
            for label in field.pref_label.values():
                if _normalize(label) == norm_text:
                    return field

        return None


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

    async def map_metadata(self, metax_data: dict[str, Any], metadata: SubmissionMetadata) -> MetaxFields:
        """Public class for actual mapping of Metax's fields.

        :param metax_data: Metax's data
        :param metadata: The submission metadata
        :returns: Metax's dataset.
        """
        LOG.info("Mapping DataCite metadata to Metax's fields: %r.", metadata)

        metax_dataset = MetaxFields(**metax_data)

        await self._map_actors(metadata.creators, Roles.creator, metax_dataset)
        await self._map_publisher(metadata.publisher, metax_dataset)
        self._map_issued(metax_dataset)
        await self._map_projects(metadata.publisher, metadata.fundingReferences, metax_dataset)

        if metadata.contributors:
            await self._map_actors(metadata.contributors, Roles.contributor, metax_dataset)

        if metadata.dates:
            self._map_temporal(metadata.dates, metax_dataset)

        if metadata.geoLocations:
            self._map_spatial(metadata.geoLocations, metax_dataset)

        if metadata.language:
            self._map_language(metadata.language, metax_dataset)

        if metadata.subjects:
            await self._map_field_of_science_and_keyword(metadata.subjects, metax_dataset)

        return metax_dataset

    async def _map_actors(
        self, people: list[Creator] | list[Contributor], role: str, metax_dataset: MetaxFields
    ) -> None:
        """
        Map DataCite actors To Metax metadata.

        :param people: DataCite creators or contributors.
        :param role: Metax role.
        :param metax_dataset: Metax metadata.
        """
        LOG.info("Mapping Metax's creators or contributors.")

        for p in people:
            if not p.affiliation:
                raise ValueError("Affiliation is required to map an Actor.")

            # Only one organization is allowed in Metax
            affiliation = p.affiliation[0]
            affiliation.name = await self._validate_organization(affiliation.name)
            organization = Organization(
                pref_label=affiliation.name, external_identifier=affiliation.affiliationIdentifier
            )

            nameIdentifier = None
            if p.nameIdentifiers:
                nameIdentifier = p.nameIdentifiers[0].nameIdentifier
            # Only one Person is allowed in Metax
            person = Person(name=p.name, external_identifier=nameIdentifier)
            actor = Actor(organization=organization, roles=[role], person=person)
            metax_dataset.actors.append(actor)

    async def _map_publisher(self, publisher: Publisher, metax_dataset: MetaxFields) -> None:
        """Map Datacite's publisher to Metax's actor with role Publisher."""
        LOG.info("Mapping Metax's publisher.")

        publisher.name = await self._validate_organization(publisher.name)
        organization = Organization(pref_label=publisher.name, external_identifier=publisher.publisherIdentifier)
        actor = Actor(organization=organization, roles=[Roles.publisher])
        metax_dataset.actors.append(actor)

    async def _map_field_of_science_and_keyword(self, subjects: list[Subject], metax_dataset: MetaxFields) -> None:
        """Map subjects to Metax's field of science and keyword.

        :param subjects: Subjects data from datacite
        :raises UserException: If a subject contains an invalid OKM subject code.
        """
        LOG.info("Mapping Metax's field_of_science and keyword.")

        for subject in subjects:
            fos = None

            # Case UI user input with subject format "code - subject" e.g (111 - Mathematics)
            subj = check_subject_format(subject.subject)
            if subj is not None:
                fos = Url(url=subject.valueUri)

            # Case API user input with field of science code or label.
            field_of_science = await self._metax_service.get_field_of_science(subject.subject)
            if field_of_science is not None:
                fos = Url(url=field_of_science.url)

            if fos is not None:
                metax_dataset.field_of_science.append(fos)
            metax_dataset.keyword.append(subject.subject)

    def _map_issued(self, metax_dataset: MetaxFields) -> None:
        """
        Map Metax's issued.
        For current SD submission, issued is the date when the dataset is published.
        """
        LOG.info("Mapping Metax's issued.")

        issued = datetime.now().strftime("%Y-%m-%d")
        metax_dataset.issued = issued

    def _map_temporal(self, dates: list[Date], metax_dataset: MetaxFields) -> None:
        """Map Metax's temporal.

        :param dates: Datacite's dates
        """
        LOG.info("Mapping Metax's temporal.")

        for date in dates:
            if date.dateType == "Other":
                date_list = [d.strip() for d in date.date.split("/") if d.strip()]
                if len(date_list) == 1:
                    metax_dataset.temporal.append(Temporal(start_date=self._to_valid_date(date_list[0])))
                elif len(date_list) == 2:
                    metax_dataset.temporal.append(
                        Temporal(
                            start_date=self._to_valid_date(date_list[0]), end_date=self._to_valid_date(date_list[1])
                        )
                    )
                else:
                    raise ValueError(f"Invalid date format for Metax's temporal: {date.date}")

    def _map_language(self, language: str, metax_dataset: MetaxFields) -> None:
        """Map Metax's language."""
        LOG.info("Mapping Metax's language.")

        if language not in METAX_MAPPING_LANGUAGES:
            raise UserException(f"Invalid language: {language}")

        metax_dataset.language = [Language(url=METAX_MAPPING_LANGUAGES[language].uri)]

    async def _map_projects(
        self, publisher: Publisher, funding_references: list[FundingReference] | None, metax_dataset: MetaxFields
    ) -> None:
        """Map Metax's projects."""
        LOG.info("Mapping Metax's projects.")

        participating_organizations = []
        fundings = []

        # Only 1 participating_organization as there is only 1 publisher in Datacite.
        publisher.name = await self._validate_organization(publisher.name)
        participating_organizations.append(
            Organization(pref_label=publisher.name, external_identifier=publisher.publisherIdentifier)
        )

        for fundingRef in funding_references:
            fundingRef.funderName = await self._validate_organization(fundingRef.funderName)
            funder = Funder(
                organization=Organization(
                    pref_label=fundingRef.funderName, external_identifier=fundingRef.funderIdentifier
                )
            )
            funding_identifier = fundingRef.awardNumber
            fundings.append(Funding(funder=funder, funding_identifier=funding_identifier))

        metax_dataset.projects.append(
            Project(
                participating_organizations=participating_organizations,
                funding=fundings,
            )
        )

    def _map_spatial(self, locations: list[GeoLocation], metax_dataset: MetaxFields) -> None:
        """Map Metax's spatial.

        Location's reference url will be mapped from the list of Metax's reference data for geo_locations.

        If there is geoLocationPoint, geoLocationBox or geolocationPolygon coming from Datacite's geolocation data,
        longitude latitude coordinates will be mapped to Metax's custom_wkt geometric presentation.

        :param locations: Datacite's geoLocations data.
        """
        LOG.info("Mapping Metax's spatial.")

        for location in locations:
            geographic_name = location.geoLocationPlace

            reference_url = [
                loc.uri
                for loc in METAX_MAPPING_GEO_LOCATIONS
                if "en" in loc.pref_label and loc.pref_label["en"] == geographic_name
            ]
            reference = ReferenceLocation(url=reference_url[0]) if reference_url[0] else None
            custom_wkt = []

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
            metax_dataset.spatial.append(spatial)

    def _to_valid_date(self, date: str) -> str:
        """
        Convert Datacite's dates to valid Metax's date.

        - Datacite's dates can be in YYYY, YYYY-MM-DD, YYYY-MM-DDThh:mm:ssTZD
        or any formats described in https://www.w3.org/TR/NOTE-datetime.
        - Datacite's date range follows https://www.ukoln.ac.uk/metadata/dcmi/collection-RKMS-ISO8601/
        - Metax only accepts date format as YYYY-MM-DD.

        :raises ValueError: If input date is not in correct format to be mapped to Metax.
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

    async def _validate_organization(self, org_name: str) -> str:
        """
        Validate ROR organization name and return the preferred organisation name.

        :raises UserException: If the ROR organization could not be found.
        """

        preferred_org_name = await self._ror_service.is_ror_organisation(org_name.strip())

        if preferred_org_name is None:
            raise UserException(f"Invalid organization name: {org_name}")

        return preferred_org_name
