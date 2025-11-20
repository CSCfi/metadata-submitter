"""Class for mapping Submitter metadata to Metax metadata."""

from copy import deepcopy
from datetime import datetime
from typing import Any

from ..api.models.datacite import (
    AlternateIdentifier,
    Contributor,
    Creator,
    Date,
    FundingReference,
    GeoLocation,
    Subject,
)
from ..api.models.submission import SubmissionMetadata
from ..conf.conf import METAX_REFERENCE_DATA
from ..helpers.logger import LOG


class MetaDataMapper:
    """Methods for mapping submitter's metadata to METAX service metadata.

    This helper class maps data from datacite, study and dataset schemas to Metax research_dataset
    schema:
    https://raw.githubusercontent.com/CSCfi/metax-api/master/src/metax_api/api/rest/v2/schemas/att_dataset_schema.json
    {
        "ResearchDataset": {
            # DOI
            "preferred_identifier": {
                "type": "string",
                "format": "uri",
            },
            # dates - Modified (date-time+zone)
            "modified": {
                "type": "string",
                "format": "date-time",
            },
            # dates - Issued (date)
            "issued": {
                "type": "string",
                "format": "date",
            },
            # object - title
            "title": {
                "type": "object",
                "$ref": "#/definitions/langString",
            },
            # keywords
            "keyword": {
                "type": "array",
                "items": {"minLength": 1, "type": "string"},
            },
            # object - description/abstract
            "description": {
                "type": "object",
                "$ref": "#/definitions/langString",
            },
            # alternateIdentifiers
            "other_identifier": {
                "type": "array",
                "items": {
                    "notation": {
                        "description": "Literal value of the identifier",
                        "type": "string",
                    },
                    "type": {
                        "description": "a type of the identifier",
                        "type": "object",
                        "items": {
                            "identifier": {
                                "description": "This is the IRI identifier for the concept",
                                "type": "string",
                                "format": "uri",
                            },
                            "in_scheme": "http://uri.suomi.fi/codelist/fairdata/identifier_type",
                        },
                    },
                },
                "required": ["notation"],
            },
            # CSC / contributors - Distributor
            "publisher": {
                "type": "object",
                "$ref": "#/definitions/ResearchAgent",
            },
            # creators
            "creator": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/ResearchAgent"},
            },
            # contributors (vs rights_holder, curator)
            "contributor": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/ResearchAgent"},
            },
            # describes study from same submission for mapped datasets
            "is_output_of": {
                "title": "Producer project",
                "description": "A project that has caused the dataset to be created",
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/Project"},
            },
            # contributor - Rights Holder
            # TODO: This can be an organisation at some point
            "rights_holder": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/ResearchAgent"},
            },
            # study/dataset type
            # not mappable as Metax requires identifier from pre-configured list
            "theme": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/Concept"},
            },
            # language
            "language": {
                "type": "array",
                "items": {
                    "type": "object",
                    "item": {
                        "title": {
                            "description": (
                                "A name of the Linguistic System. Name is given as localized text from IETF language "
                                "codes. In case text cannot be localized 'zxx' or 'und' language codes must be used."
                            ),
                            "type": "object",
                            "$ref": "#/definitions/langString",
                        },
                        "identifier": {
                            "description": (
                                "Recommended best practice is to identify the resource by means of a string conforming "
                                "to a formal identification system. An unambiguous reference to the resource "
                                "within a given context."
                            ),
                            "type": "string",
                            "format": "uri",
                        },
                    },
                },
            },
            # geoLocations, MUST be WGS84 coordinates, https://epsg.io/4326
            "spatial": {
                "geographic_name": {
                    "description": (
                        "A geographic name is a proper noun applied to a spatial object. Taking the example used in "
                        "the relevant INSPIRE data specification (page 18), the following are all valid geographic "
                        "names for the Greek capital:"
                        "- Αθήνα (the Greek endonym written in the Greek script)"
                        "- Athína (the standard romanisation of the endonym)"
                        "- Athens (the English language exonym)"
                        "For INSPIRE-conformant data, provide the metadata for the geographic name using "
                        "a skos:Concept as a datatype."
                    ),
                    "type": "string",
                },
                "as_wkt": {
                    "title": "Geometry",
                    "description": "Supported format for geometry is WKT string in WGS84 coordinate system.",
                    "type": "array",
                    "example": [
                        "POLYGON((-122.358 47.653, -122.348 47.649, -122.348 47.658, -122.358 47.658, -122.358 47.653))"
                    ],
                    "items": {"minLength": 1, "type": "string"},
                },
            },
            # dates - Collected (date-time+zone)
            "temporal": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/PeriodOfTime"},
            },
            # datasets from same submission
            "relation": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["relation_type", "entity"],
                    "item": {
                        "entity": {
                            "type": "object",
                            "item": {
                                "title": {
                                    "description": "A name given to the resource.",
                                    "type": "object",
                                    "$ref": "#/definitions/langString",
                                },
                                "description": {
                                    "description": "An account of the resource.",
                                    "type": "object",
                                    "$ref": "#/definitions/langString",
                                },
                                "identifier": {
                                    "description": "Recommended best practice is to identify the resource by means of "
                                    "a string conforming to a formal identification system.  An unambiguous reference "
                                    "to the resource within a given context.",
                                    "type": "string",
                                    "format": "uri",
                                },
                                "type": {
                                    "description": "Type of the entity, for example: API, Application, News article, "
                                    "paper, post or visualization.",
                                    "type": "object",
                                    "$ref": "#/definitions/Concept",
                                },
                            },
                        },
                        "relation_type": {
                            "description": "Role of the influence.",
                            "type": "object",
                            "$ref": "#/definitions/Concept",
                        },
                    },
                },
            },
            "field_of_science": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/Concept"},
            },
            # restricted
            "access_rights": {
                "type": "object",
                "$ref": "#/definitions/RightsStatement",
            },
            # contributors - Data Curator
            "curator": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/ResearchAgent"},
            },
            "total_remote_resources_byte_size": {
                "type": "integer",
            },
        }
    }
    """

    def __init__(
        self,
        metax_data: dict[str, Any],
        metadata: SubmissionMetadata,
        file_bytes: int,
    ) -> None:
        """Set variables.

        :param metax_data: Metax research_dataset metadata
        :param metadata: The submission metadata
        :param file_bytes: The number of file bytes
        """
        self.research_dataset = metax_data
        self.metadata = metadata
        self.research_dataset["total_remote_resources_byte_size"] = file_bytes
        self.affiliations: list[Any] = []
        self.identifier_types = METAX_REFERENCE_DATA["identifier_types"]
        self.languages = METAX_REFERENCE_DATA["languages"]
        self.fields_of_science = METAX_REFERENCE_DATA["fields_of_science"]
        self.funding_references = METAX_REFERENCE_DATA["funding_references"]
        self.person: dict[str, Any] = {
            "name": "",
            "@type": "Person",
            "member_of": {"name": {"en": ""}, "@type": "Organization"},
            "identifier": "",
        }

    async def map_metadata(self) -> dict[str, Any]:
        """Public class for actual mapping of metadata fields.

        :returns: Research dataset
        """
        LOG.info("Mapping DataCite data to Metax metadata: %r.", self.metadata)

        self._map_creators(self.metadata.creators)

        if self.metadata.keywords:
            self.research_dataset["keyword"] = self.metadata.keywords.split(",")

        if self.metadata.contributors:
            self._map_contributors(self.metadata.contributors)

        if self.metadata.dates:
            self._map_dates(self.metadata.dates)

        if self.metadata.geoLocations:
            self._map_spatial(self.metadata.geoLocations)

        if self.metadata.alternateIdentifiers:
            self._map_alternative_identifier(self.metadata.alternateIdentifiers)

        if self.metadata.language:
            self.research_dataset["language"] = []
            self.research_dataset["language"].append(
                {"title": {"en": self.metadata.language}, "identifier": self.languages[self.metadata.language]}
            )

        if self.metadata.subjects:
            self._map_field_of_science(self.metadata.subjects)

        if self.metadata.fundingReferences:
            self._map_funding_references(self.metadata.fundingReferences)

        return self.research_dataset

    def _map_creators(self, creators: list[Creator]) -> None:
        """Map creators.

        :param creators: Creators data from datacite
        """
        LOG.info("Mapping creator")
        LOG.debug(creators)
        self.research_dataset["creator"] = []
        for creator in creators:
            metax_creator = deepcopy(self.person)
            metax_creator["name"] = str(creator.givenName).strip() + " " + str(creator.familyName).strip()

            # Metax schema accepts only one affiliation per creator
            # so we take first one
            if creator.affiliation:
                affiliation = creator.affiliation[0]
                metax_creator["member_of"]["name"]["en"] = affiliation.name
                if affiliation.affiliationIdentifier:
                    metax_creator["member_of"]["identifier"] = affiliation.affiliationIdentifier
                # here we collect affiliations for
                if metax_creator["member_of"] not in self.affiliations:
                    self.affiliations.append(metax_creator["member_of"])
            # Metax schema accepts only one identifier per creator
            # so we take first one
            if creator.nameIdentifiers and creator.nameIdentifiers[0].nameIdentifier:
                metax_creator["identifier"] = creator.nameIdentifiers[0].nameIdentifier
            else:
                del metax_creator["identifier"]
            self.research_dataset["creator"].append(metax_creator)

    def _map_contributors(self, contributors: list[Contributor]) -> None:
        """Map contributors.

        :param contributors: Contributors data from
        """
        LOG.info("Mapping contributors")
        LOG.debug(contributors)
        self.research_dataset["contributor"] = []

        for contributor in contributors:
            metax_contributor = deepcopy(self.person)
            metax_contributor["name"] = str(contributor.givenName).strip() + " " + str(contributor.familyName).strip()
            # Metax schema accepts only one affiliation per contributor
            # so we take first one
            if contributor.affiliation:
                affiliation = contributor.affiliation[0]
                metax_contributor["member_of"]["name"]["en"] = affiliation.name
                if affiliation.affiliationIdentifier:
                    metax_contributor["member_of"]["identifier"] = affiliation.affiliationIdentifier
                if metax_contributor["member_of"] not in self.affiliations:
                    self.affiliations.append(metax_contributor["member_of"])
            # Metax schema accepts only one identifier per contributor
            # so we take first one
            if contributor.nameIdentifiers and contributor.nameIdentifiers[0].nameIdentifier:
                metax_contributor["identifier"] = contributor.nameIdentifiers[0].nameIdentifier
            else:
                del metax_contributor["identifier"]

            self.research_dataset["contributor"].append(metax_contributor)

    def _map_dates(self, dates: list[Date]) -> None:
        """Map dates.

        :param dates: Dates data from datacite
        """
        LOG.info("Mapping dates")
        LOG.debug(dates)
        self.research_dataset["temporal"] = []
        temporal_date = {
            "start_date": {
                "type": "string",
                "format": "date-time",
            },
            "end_date": {
                "type": "string",
                "format": "date-time",
            },
        }

        # format of date must be forced
        for date in dates:
            date_list: list[Any] = list(filter(None, date.date.split("/")))
            if date.dateType == "Issued":
                if not self.research_dataset.get("issued", None) or datetime.strptime(
                    self.research_dataset["issued"], "%Y-%m-%d"
                ) > datetime.strptime(date_list[0], "%Y-%m-%d"):
                    self.research_dataset["issued"] = date_list[0]
            if date.dateType == "Updated":
                if not self.research_dataset.get("modified", None) or datetime.strptime(
                    self.research_dataset["modified"][:9], "%Y-%m-%d"
                ) < datetime.strptime(date_list[0], "%Y-%m-%d"):
                    self.research_dataset["modified"] = date_list[-1] + "T00:00:00+03:00"
            if date.dateType == "Collected":
                temporal_date["start_date"] = date_list[0] + "T00:00:00+03:00"
                temporal_date["end_date"] = date_list[-1] + "T00:00:00+03:00"
                self.research_dataset["temporal"].append(temporal_date)

        if not self.research_dataset["temporal"]:
            del self.research_dataset["temporal"]

    def _map_spatial(self, locations: list[GeoLocation]) -> None:
        """Map geoLocations.

        If geoLocationPoint or geoLocationBox is coming with location data
        lat lon coordinates will be mapped to wkt geometric presentation.
        Inputs MUST be WGS84 degrees coordinates as geographic coordinate system (GCS) is used here.

        :param locations: GeoLocations data from datacite
        """
        LOG.info("Mapping locations")
        LOG.debug(locations)

        spatials = self.research_dataset["spatial"] = []
        for location in locations:
            spatial: dict[str, Any] = {}
            spatial["as_wkt"] = []
            if location.geoLocationPlace:
                spatial["geographic_name"] = location.geoLocationPlace
            if location.geoLocationPoint:
                lat = location.geoLocationPoint.pointLatitude
                lon = location.geoLocationPoint.pointLongitude
                spatial["as_wkt"].append(f"POINT({lon} {lat})")
            if location.geoLocationBox:
                west_lon = location.geoLocationBox.westBoundLongitude
                east_lon = location.geoLocationBox.eastBoundLongitude
                north_lat = location.geoLocationBox.northBoundLatitude
                south_lat = location.geoLocationBox.southBoundLatitude
                spatial["as_wkt"].append(
                    f"POLYGON(({west_lon} {north_lat}, {east_lon} {north_lat}, "
                    f"{east_lon} {south_lat}, {west_lon} {south_lat}, {west_lon} {north_lat}))"
                )
            if not spatial["as_wkt"]:
                del spatial["as_wkt"]
            spatials.append(spatial)

    def _map_alternative_identifier(self, identifiers: list[AlternateIdentifier]) -> None:
        """Map alternateIdentifiers.

        :param identifiers: Alternate identifiers data from datacite
        """
        LOG.info("Mapping alternate identifiers")
        LOG.debug(identifiers)

        other_identifier: dict[str, Any] = {
            "type": {
                "identifier": "",
                "in_scheme": "http://uri.suomi.fi/codelist/fairdata/identifier_type",
            },
            "notation": "",
        }
        other_identifiers = self.research_dataset["other_identifier"] = []
        for identifier in identifiers:
            other_identifier["notation"] = identifier.alternateIdentifier
            identifier_type = self.identifier_types[identifier.alternateIdentifierType.lower()]
            other_identifier["type"]["identifier"] = identifier_type
            other_identifiers.append(other_identifier)

    def _map_field_of_science(self, subjects: list[Subject]) -> None:
        """Map subjects to field of science.

        :param subjects: Subjects data from datacite
        :raises: Custom SubjectNotFoundException if subject cannot be mapped to metax field of science
        """
        LOG.info("Mapping subjects")
        LOG.debug(subjects)

        fos: dict[str, Any] = {
            "in_scheme": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
            "identifier": "",
            "pref_label": {},
        }
        field_of_science = self.research_dataset["field_of_science"] = []
        for subject in subjects:
            try:
                subject_code = subject.subject.split(" - ")[0]
                code = [i for i in self.fields_of_science if i == f"ta{subject_code}"]
                fos["identifier"] = self.fields_of_science[code[0]]["uri"]
                fos["pref_label"] = self.fields_of_science[code[0]]["label"]
            except IndexError as exc:
                raise SubjectNotFoundException from exc

            field_of_science.append(fos)

    # Metax mapping for fundingReferences is optional
    # It can be removed after we get the confirmation that it is not needed.

    def _map_funding_references(self, funders: list[FundingReference]) -> None:
        """Map funding references.

        :param funders: Funders data from datacite
        """
        LOG.info("Mapping funding references")
        LOG.debug(funders)

        funding: dict[str, Any] = {
            "funder": {
                "organization": {
                    "identifier": "",
                    "pref_label": {},
                },
            },
        }

        funding_references = self.research_dataset["funding"] = []

        for funder in funders:
            try:
                fund = [i for i in self.funding_references if i == funder.funderName]
                funding["funder"]["organization"]["identifier"] = self.funding_references[fund[0]]["uris"]
                funding["funder"]["organization"]["pref_label"] = self.funding_references[fund[0]]["label"]

            except IndexError as exc:
                raise SubjectNotFoundException from exc

            funding_references.append(funding)


class SubjectNotFoundException(Exception):
    """Custom exception to be raised when subject cannot be mapped to metax field of science."""

    def __init__(self) -> None:
        """Set up exception message."""
        Exception.__init__(self, "The provided subject does not correspond with any of the possible subject names.")
