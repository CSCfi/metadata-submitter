"""Class for mapping Submitter metadata to Metax metadata."""
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List

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
            # not mappable as Metax requires identifier from preconfigured list
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
                                "codes. In case text cannot be localixed 'zxx' or 'und' language codes must be used."
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
                        "- Athína (the standard Romanisation of the endonym)"
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
            # TODO: this need to be extracted from linked files metadata on integration with SD Connect
            "total_remote_resources_byte_size": {
                "type": "integer",
            },
        }
    }
    """

    def __init__(self, object_type: str, metax_data: Dict, data: Dict) -> None:
        """Set variables.

        :param object_type: Schema name (dataset or study)
        :param metax_data: Metax research_dataset metadata
        :param data: Dict containing datacite data
        """
        self.object_type = object_type
        self.research_dataset = metax_data
        self.datacite_data = data
        self.affiliations: List = []
        self.identifier_types = METAX_REFERENCE_DATA["identifier_types"]
        self.languages = METAX_REFERENCE_DATA["languages"]
        self.fields_of_science = METAX_REFERENCE_DATA["fields_of_science"]
        self.person: Dict[str, Any] = {
            "name": "",
            "@type": "Person",
            "member_of": {"name": {"en": ""}, "@type": "Organization"},
            "identifier": "",
        }

    def map_metadata(self) -> Dict[str, Any]:
        """Public class for actual mapping of metadata fields.

        :returns: Research dataset
        """
        LOG.info("Mapping datasite data to Metax metadata")
        LOG.debug("Data incomming for mapping: %r.", self.datacite_data)
        for key, value in self.datacite_data["doiInfo"].items():
            if key == "creators":
                self._map_creators(value)
            if key == "keywords":
                self.research_dataset["keyword"] = value.split(",")
            if key == "contributors":
                self._map_contributors(value)
            if key == "dates":
                self._map_dates(value)
            if key == "geoLocations":
                self._map_spatial(value)
            if key == "alternateIdentifiers":
                self._map_other_identifier(value)
            if key == "language":
                self.research_dataset["language"] = []
                self.research_dataset["language"].append({"title": {"en": value}, "identifier": self.languages[value]})
            if key == "subjects":
                self._map_field_of_science(value)

        for key, value in self.datacite_data["extraInfo"].items():
            if self.object_type == "study" and key == "datasetIdentifiers":
                self._map_relations(value)
            if self.object_type == "dataset" and key == "studyIdentifier":
                self._map_is_output_of(value)
        return self.research_dataset

    def _map_creators(self, creators: List) -> None:
        """Map creators.

        :param creators: Creators data from datacite
        """
        LOG.info("Mapping creator")
        LOG.debug(creators)
        self.research_dataset["creator"] = []
        for creator in creators:
            metax_creator = deepcopy(self.person)
            metax_creator["name"] = creator["name"]
            # Metax schema accepts only one affiliation per creator
            # so we take first one
            if creator.get("affiliation", None):
                affiliation = creator["affiliation"][0]
                metax_creator["member_of"]["name"]["en"] = affiliation["name"]
                if affiliation.get("affiliationIdentifier"):
                    metax_creator["member_of"]["identifier"] = affiliation["affiliationIdentifier"]
                # here we collect affiliations for
                if metax_creator["member_of"] not in self.affiliations:
                    self.affiliations.append(metax_creator["member_of"])
            # Metax schema accepts only one identifier per creator
            # so we take first one
            if creator.get("nameIdentifiers", None) and creator["nameIdentifiers"][0].get("nameIdentifier", None):
                metax_creator["identifier"] = creator["nameIdentifiers"][0]["nameIdentifier"]
            else:
                del metax_creator["identifier"]
            self.research_dataset["creator"].append(metax_creator)

    def _map_contributors(self, contributors: List) -> None:
        """Map contributors.

        :param contributors: Contributors data from
        """
        LOG.info("Mapping contributors")
        LOG.debug(contributors)
        self.research_dataset["contributor"] = []
        self.research_dataset["rights_holder"] = []
        self.research_dataset["curator"] = []

        for contributor in contributors:
            metax_contributor = deepcopy(self.person)
            metax_contributor["name"] = contributor["name"]
            # Metax schema accepts only one affiliation per contributor
            # so we take first one
            if contributor.get("affiliation", None):
                affiliation = contributor["affiliation"][0]
                metax_contributor["member_of"]["name"]["en"] = affiliation["name"]
                if affiliation.get("affiliationIdentifier"):
                    metax_contributor["member_of"]["identifier"] = affiliation["affiliationIdentifier"]
                if metax_contributor["member_of"] not in self.affiliations:
                    self.affiliations.append(metax_contributor["member_of"])
            # Metax schema accepts only one identifier per contributor
            # so we take first one
            if contributor.get("nameIdentifiers", None) and contributor["nameIdentifiers"][0].get(
                "nameIdentifier", None
            ):
                metax_contributor["identifier"] = contributor["nameIdentifiers"][0]["nameIdentifier"]
            else:
                del metax_contributor["identifier"]

            if contributor.get("contributorType", None):
                if contributor["contributorType"] == "Data Curator":
                    self.research_dataset["curator"].append(metax_contributor)
                elif contributor["contributorType"] == "Rights Holder":
                    self.research_dataset["rights_holder"].append(metax_contributor)
                else:
                    self.research_dataset["contributor"].append(metax_contributor)

        if not self.research_dataset["rights_holder"]:
            del self.research_dataset["rights_holder"]
        if not self.research_dataset["curator"]:
            del self.research_dataset["curator"]

    def _map_dates(self, dates: List) -> None:
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
            date_list: List = list(filter(None, date["date"].split("/")))
            if date["dateType"] == "Issued":
                if not self.research_dataset.get("issued", None) or datetime.strptime(
                    self.research_dataset["issued"], "%Y-%m-%d"
                ) > datetime.strptime(date_list[0], "%Y-%m-%d"):
                    self.research_dataset["issued"] = date_list[0]
            if date["dateType"] == "Updated":
                if not self.research_dataset.get("modified", None) or datetime.strptime(
                    self.research_dataset["modified"][:9], "%Y-%m-%d"
                ) < datetime.strptime(date_list[0], "%Y-%m-%d"):
                    self.research_dataset["modified"] = date_list[-1] + "T00:00:00+03:00"
            if date["dateType"] == "Collected":
                temporal_date["start_date"] = date_list[0] + "T00:00:00+03:00"
                temporal_date["end_date"] = date_list[-1] + "T00:00:00+03:00"
                self.research_dataset["temporal"].append(temporal_date)

        if not self.research_dataset["temporal"]:
            del self.research_dataset["temporal"]

    def _map_spatial(self, locations: List) -> None:
        """Map geoLocations.

        If geoLocationPoint or geoLocationBox is comming with location data
        lat lon coordinates will be mapped to wkt geometric presentation.
        Inputs MUST be WGS84 degrees coordinates as geographic coordinate system (GCS) is used here.

        :param locations: GeoLocations data from datacite
        """
        LOG.info("Mapping locations")
        LOG.debug(locations)

        spatials = self.research_dataset["spatial"] = []
        for location in locations:
            spatial: Dict = {}
            spatial["as_wkt"] = []
            if location.get("geoLocationPlace", None):
                spatial["geographic_name"] = location["geoLocationPlace"]
            if location.get("geoLocationPoint", None):
                lat = float(location["geoLocationPoint"]["pointLatitude"])
                lon = float(location["geoLocationPoint"]["pointLongitude"])
                spatial["as_wkt"].append(f"POINT({lon} {lat})")
            if location.get("geoLocationBox", None):
                west_lon = float(location["geoLocationBox"]["westBoundLongitude"])
                east_lon = float(location["geoLocationBox"]["eastBoundLongitude"])
                north_lat = float(location["geoLocationBox"]["northBoundLatitude"])
                south_lat = float(location["geoLocationBox"]["southBoundLatitude"])
                spatial["as_wkt"].append(
                    f"POLYGON(({west_lon} {north_lat}, {east_lon} {north_lat}, "
                    f"{east_lon} {south_lat}, {west_lon} {south_lat}, {west_lon} {north_lat}))"
                )
            if not spatial["as_wkt"]:
                del spatial["as_wkt"]
            spatials.append(spatial)

    def _map_other_identifier(self, identifiers: List) -> None:
        """Map alternateIdentifiers.

        :param identifiers: Alternate identifiers data from datacite
        """
        LOG.info("Mapping alternate identifiers")
        LOG.debug(identifiers)

        other_identifier: Dict[str, Any] = {
            "type": {
                "identifier": "",
                "in_scheme": "http://uri.suomi.fi/codelist/fairdata/identifier_type",
            },
            "notation": "",
        }
        other_identifiers = self.research_dataset["other_identifier"] = []
        for identifier in identifiers:
            other_identifier["notation"] = identifier["alternateIdentifier"]
            identifier_type = self.identifier_types[identifier["alternateIdentifierType"].lower()]
            other_identifier["type"]["identifier"] = identifier_type
            other_identifiers.append(other_identifier)

    def _map_field_of_science(self, subjects: List) -> None:
        """Map subjects to field of science.

        :param subjects: Subjects data from datacite
        :raises: Custom SubjectNotFoundException if subject cannot be mapped to metax field of science
        """
        LOG.info("Mapping subjects")
        LOG.debug(subjects)

        fos: Dict[str, Any] = {
            "in_scheme": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
            "identifier": "",
            "pref_label": {},
        }
        field_of_science = self.research_dataset["field_of_science"] = []
        for subject in subjects:
            try:
                subject_code = subject["subject"].split(" - ")[0]
                code = [i for i in self.fields_of_science if i == f"ta{subject_code}"]
                fos["identifier"] = self.fields_of_science[code[0]]["uri"]
                fos["pref_label"] = self.fields_of_science[code[0]]["label"]
            except IndexError as exc:
                raise SubjectNotFoundException from exc

            field_of_science.append(fos)

    def _map_relations(self, datasets: List) -> None:
        """Map datasets for study as a relation.

        :param datasets: Datasets identifiers object
        """
        LOG.info("Mapping datasets related to study")
        LOG.debug(datasets)

        relation = {
            "entity": {
                "identifier": "",
                "type": {
                    "in_scheme": "http://uri.suomi.fi/codelist/fairdata/resource_type",
                    "identifier": "http://uri.suomi.fi/codelist/fairdata/resource_type/code/dataset",
                    "pref_label": {"en": "Dataset", "fi": "Tutkimusaineisto", "und": "Tutkimusaineisto"},
                },
            },
            "relation_type": {
                "identifier": "http://purl.org/dc/terms/relation",
                "pref_label": {"en": "Related dataset", "fi": "Liittyvä aineisto", "und": "Liittyvä aineisto"},
            },
        }

        relations = self.research_dataset["relation"] = []

        for dataset in datasets:
            rel = deepcopy(relation)
            rel["entity"]["identifier"] = dataset["url"]
            relations.append(rel)

    def _map_is_output_of(self, study: Dict) -> None:
        """Map study for datasets as a output of.

        :param study: Study identifier object
        """
        LOG.info("Mapping study for related datasets")
        LOG.debug(study)

        for obj in self.datacite_data["metadataObjects"]:
            if obj["schema"] == "study":
                name = obj["tags"]["displayTitle"]

        self.research_dataset["is_output_of"] = [
            {
                "name": {"en": name},
                "identifier": study["url"],
                "source_organization": self.affiliations,
            }
        ]


class SubjectNotFoundException(Exception):
    """Custom exception to be raised when subject cannot be mapped to metax field of science."""

    def __init__(self) -> None:
        """Set up exception message."""
        Exception.__init__(self, "The provided subject does not correspond with any of the possible subject names.")
