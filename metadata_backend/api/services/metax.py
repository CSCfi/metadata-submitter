"""Metax services."""

from datetime import datetime
from typing import Any

from ...conf.conf import METAX_REFERENCE_DATA
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
)
from ..models.submission import SubmissionMetadata
from ..services.publish import check_subject_format


class MetaxMapper:
    """Map DataCite metadata to Metax metadata."""

    def __init__(
        self,
        metax_data: dict[str, Any],
        metadata: SubmissionMetadata,
    ) -> None:
        """Map DataCite metadata to Metax metadata.

        :param metax_data: Metax's data
        :param metadata: The submission metadata
        """
        self.metax_dataset = MetaxFields(**metax_data)
        self.metadata = metadata

        # Values from Metax reference data
        self.ror_organizations = METAX_REFERENCE_DATA["ror_organizations"]
        self.languages = METAX_REFERENCE_DATA["languages"]
        self.fields_of_science = METAX_REFERENCE_DATA["fields_of_science"]
        self.geo_locations = METAX_REFERENCE_DATA["geo_locations"]

    def map_metadata(self) -> MetaxFields:
        """Public class for actual mapping of Metax's fields.

        :returns: Metax's dataset.
        """
        LOG.info("Mapping DataCite metadata to Metax's fields: %r.", self.metadata)

        self._map_actors(self.metadata.creators, Roles.creator)
        self._map_publisher(self.metadata.publisher)
        self._map_issued()
        self._map_projects(self.metadata.publisher, self.metadata.fundingReferences)

        if self.metadata.contributors:
            self._map_actors(self.metadata.contributors, Roles.contributor)

        if self.metadata.dates:
            self._map_temporal(self.metadata.dates)

        if self.metadata.geoLocations:
            self._map_spatial(self.metadata.geoLocations)

        if self.metadata.language:
            self._map_language(self.metadata.language)

        if self.metadata.subjects:
            self._map_field_of_science_and_keyword(self.metadata.subjects)

        return self.metax_dataset

    def _map_actors(self, people: list[Creator] | list[Contributor], role: str) -> None:
        """Map Metax's actors.

        :param creators: Datacite's creators
        :param contributors: Datacite's contributors
        """
        LOG.info("Mapping Metax's creators or contributors.")

        for p in people:
            if not p.affiliation:
                raise ValueError("Affiliation is required to map an Actor.")

            # Only one organization is allowed in Metax
            affiliation = p.affiliation[0]
            self._validate_organization(affiliation.name)
            organization = Organization(
                pref_label=affiliation.name, external_identifier=affiliation.affiliationIdentifier
            )

            nameIdentifier = None
            if p.nameIdentifiers:
                nameIdentifier = p.nameIdentifiers[0].nameIdentifier
            # Only one Person is allowed in Metax
            person = Person(name=p.name, external_identifier=nameIdentifier)
            actor = Actor(organization=organization, roles=[role], person=person)
            self.metax_dataset.actors.append(actor)

    def _map_publisher(self, publisher: Publisher) -> None:
        """Map Datacite's publisher to Metax's actor with role Publisher."""
        LOG.info("Mapping Metax's publisher.")

        self._validate_organization(publisher.name)
        organization = Organization(pref_label=publisher.name, external_identifier=publisher.publisherIdentifier)
        actor = Actor(organization=organization, roles=[Roles.publisher])
        self.metax_dataset.actors.append(actor)

    def _map_field_of_science_and_keyword(self, subjects: list[Subject]) -> None:
        """Map subjects to Metax's field of science and keyword.

        :param subjects: Subjects data from datacite
        :raises UserException: If a subject contains an invalid OKM subject code.
        """
        LOG.info("Mapping Metax's field_of_science and keyword.")

        label_to_code = {value["label"]["en"]: code for code, value in self.fields_of_science.items()}

        for subject in subjects:
            # Case UI user input with subject format "code - subject" e.g (111 - Mathematics)
            subj = check_subject_format(subject.subject)
            if subj is not None:
                fos = FieldOfScience(url=subject.valueUri)

            # Case API user input with subject format "subject"
            # url is subject's valueUri if there is input data otherwise getting from FOS's reference data.
            if subject.subject in label_to_code:
                code = label_to_code[subject.subject]
                fos = FieldOfScience(
                    url=subject.valueUri if subject.valueUri else self.fields_of_science[f"ta{code}"]["uri"]
                )

            self.metax_dataset.field_of_science.append(fos)
            self.metax_dataset.keyword.append(subject.subject)

    def _map_issued(self) -> None:
        """
        Map Metax's issued.
        For current SD submission, issued is the date when the dataset is published.
        """
        LOG.info("Mapping Metax's issued.")

        issued = datetime.now().strftime("%Y-%m-%d")
        self.metax_dataset.issued = issued

    def _map_temporal(self, dates: list[Date]) -> None:
        """Map Metax's temporal.

        :param dates: Datacite's dates
        """
        LOG.info("Mapping Metax's temporal.")

        for date in dates:
            if date.dateType == "Other":
                date_list = [d.strip() for d in date.date.split("/") if d.strip()]
                if len(date_list) == 1:
                    self.metax_dataset.temporal.append(Temporal(start_date=self._to_valid_date(date_list[0])))
                elif len(date_list) == 2:
                    self.metax_dataset.temporal.append(
                        Temporal(
                            start_date=self._to_valid_date(date_list[0]), end_date=self._to_valid_date(date_list[1])
                        )
                    )
                else:
                    raise ValueError(f"Invalid date format for Metax's temporal: {date.date}")

    def _map_language(self, language: str) -> None:
        """Map Metax's language."""
        LOG.info("Mapping Metax's language.")

        if language not in self.languages:
            raise UserException(f"Invalid language: {language}")

        self.metax_dataset.language = [Language(url=self.languages[language]["uri"])]

    def _map_projects(self, publisher: Publisher, fundingReferences: list[FundingReference] | None = None) -> None:
        """Map Metax's projects."""
        LOG.info("Mapping Metax's projects.")

        participating_organizations = []
        fundings = []

        # Only 1 participating_organization as there is only 1 publisher in Datacite.
        self._validate_organization(publisher.name)
        participating_organizations.append(
            Organization(pref_label=publisher.name, external_identifier=publisher.publisherIdentifier)
        )

        for fundingRef in fundingReferences:
            self._validate_organization(fundingRef.funderName)
            funder = Funder(
                organization=Organization(
                    pref_label=fundingRef.funderName, external_identifier=fundingRef.funderIdentifier
                )
            )
            funding_identifier = fundingRef.awardNumber
            fundings.append(Funding(funder=funder, funding_identifier=funding_identifier))

        self.metax_dataset.projects.append(
            Project(
                participating_organizations=participating_organizations,
                funding=fundings,
            )
        )

    def _map_spatial(self, locations: list[GeoLocation]) -> None:
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
                loc["uri"]
                for loc in self.geo_locations
                if "en" in loc.get("pref_label", {}) and loc["pref_label"]["en"] == geographic_name
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
            self.metax_dataset.spatial.append(spatial)

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

    def _validate_organization(self, org_name: str) -> None:
        """
        Validate organizations.
        - Creators' and Contributors' affliation.
        - Publisher's organization.

        :raises UserException: If organization not in ROR organizations list.
        """

        if self.ror_organizations.get(org_name.lower().strip()) is None:
            raise UserException(f"Invalid organization name: {org_name}")
