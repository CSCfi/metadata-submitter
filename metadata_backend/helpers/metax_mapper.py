"""Class for mapping Submitter metadata to Metax metadata."""
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List

from ..conf.conf import metax_reference_data
from .logger import LOG


class MetaDataMapper:
    """Methods for mapping submitter's metadata to METAX service metadata.

    This helpper class maps data from datacite, study and dataset schemas to Metax research_dataset
    schema:
    https://raw.githubusercontent.com/CSCfi/metax-api/master/src/metax_api/api/rest/v2/schemas/att_dataset_schema.json
    """

    {
        "Person": {
            "properties": {
                "@type": {"type": "string", "enum": ["Person"]},
                "identifier": {
                    "description": "An unambiguous reference to the resource within a given context.",
                    "type": "string",
                    "format": "uri",
                    "example": ["http://orcid.org/0000-0002-1825-0097"],
                },
                "name": {
                    "title": "Name",
                    "description": (
                        "This property contains a name of the agent. This property can be repeated for different "
                        "versions of the name (e.g. the name in different languages)"
                    ),
                    "type": "string",
                },
                "member_of": {
                    "description": (
                        "Indicates that a person is a member of the Organization with no indication of the "
                        "nature of that membership or the role played."
                    ),
                    "type": "object",
                    "$ref": "#/definitions/Organization",
                },
                "contributor_type": {
                    "description": "Contributor type of the Agent. Reference data from DataCite.",
                    "type": "array",
                    "items": {"type": "object", "$ref": "#/definitions/Concept"},
                },
            },
            "required": ["@type", "name", "member_of"],
        },
    }
    {
        "Organization": {
            "description": "An organization.",
            "type": "object",
            "properties": {
                "@type": {"type": "string", "enum": ["Organization"]},
                "identifier": {
                    "type": "string",
                    "format": "uri",
                    "example": ["http://orcid.org/0000-0002-1825-0097"],
                },
                "name": {
                    "type": "object",
                    "$ref": "#/definitions/langString",
                },
                "contributor_type": {
                    "@id": "http://uri.suomi.fi/datamodel/ns/mrd#contributorType",
                    "description": (
                        "Contributor type of the Organization. Based on the subset of the DataCite reference data."
                    ),
                    "type": "array",
                    "items": {"type": "object", "$ref": "#/definitions/Concept"},
                },
            },
            "required": ["@type"],
        }
    }
    {
        "Concept": {
            "description": "An idea or notion; a unit of thought.",
            "type": "object",
            "properties": {
                "identifier": {
                    "description": "This is the IRI identifier for the concept",
                    "type": "string",
                    "format": "uri",
                },
                "pref_label": {
                    "description": (
                        "The preferred lexical label for a resource, in a given language. A resource has no more than "
                        "one value of skos:prefLabel per language tag, and no more than one value of skos:prefLabel "
                        "without language tag. The range of skos:prefLabel is the class of RDF plain literals. "
                        "skos:prefLabel, skos:altLabel and skos:hiddenLabel are pairwise disjoint properties."
                    ),
                    "type": "object",
                    "$ref": "#/definitions/langString",
                },
                "definition": {
                    "description": "A statement or formal explanation of the meaning of a concept.",
                    "type": "object",
                    "$ref": "#/definitions/langString",
                },
                "in_scheme": {
                    "description": (
                        "Relates a resource (for example a concept) to a concept scheme in which it is included."
                    ),
                    "type": "string",  # "uri": "http://uri.suomi.fi/codelist/fairdata/identifier_type/code/doi",
                    "format": "uri",
                },
                "required": ["identifier"],
            },
        }
    }
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
            # TODO: need more info
            # the only field with FUNDER, study
            "is_output_of": {
                "title": "Producer project",
                "description": "A project that has caused the dataset to be created",
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/Project"},
            },
            # contributor - Rights Holder
            # can this be also organisation?
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
            # cannot be mapped to Metax unless we take Lexvo schema in to use
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
                                "to a formal identification system. \n\nAn unambiguous reference to the resource "
                                "within a given context."
                            ),
                            "type": "string",
                            "format": "uri",
                        },
                    },
                },
            },
            # geoLocations
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
            # dataset from same folder/submission ?
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
            # subject Yrjö Leino
            "field_of_science": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/Concept"},
            },
            # TODO: Needs clarification
            "remote_resources": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/WebResource"},
            },
            # restricted - ask Metax team for a link to REMS
            "access_rights": {
                "type": "object",
                "$ref": "#/definitions/RightsStatement",
            },
            # contributors - Data Curator
            "curator": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/ResearchAgent"},
            },
            # sizes field need either some indication on incomming type of data or MUST be in bytes
            # Though now dates schema is array so maybe data type is better solution for multiple object inputs
            "total_remote_resources_byte_size": {
                "type": "integer",
            },
        }
    }

    def __init__(self, metax_data: Dict, data: Dict) -> None:
        """Set variables.

        :param metax_data: Metax research_dataset metadata
        """
        self.research_dataset = metax_data
        self.datacite_data = data
        self.identifier_types = metax_reference_data["identifier_types"]
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
        LOG.debug("Data incomming for mapping: ", self.datacite_data)
        for key, value in self.datacite_data.items():
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
            # Metax schema accepts only one identifier per creator
            # so we take first one
            else:
                del metax_creator["member_of"]
            if creator.get("nameIdentifiers", None) and creator["nameIdentifiers"][0].get("nameIdentifier", None):
                metax_creator["identifier"] = creator["nameIdentifiers"][0]["nameIdentifier"]
            else:
                del metax_creator["identifier"]
            self.research_dataset["creator"].append(metax_creator)

    def _map_contributors(self, contributors: List) -> None:
        """Map contributors.

        contributors (other then Rights Holder,  Data Curator, Distributor)
                                   -> contributor
        contributors Rights Holder -> rights_holder
        contributors Data Curator  -> curator

        :param submitter_data: Contributors data from
        """
        LOG.info("Mapping contributors")
        LOG.debug(contributors)
        self.research_dataset["contributor"] = []
        self.research_dataset["rights_holder"] = []
        self.research_dataset["curator"] = []

        for contributor in contributors:
            metax_contributor = deepcopy(self.person)
            metax_contributor["name"] = contributor["name"]
            # Metax schema accepts only one affiliation per creator
            # so we take first one
            if contributor.get("affiliation", None):
                affiliation = contributor["affiliation"][0]
                metax_contributor["member_of"]["name"]["en"] = affiliation["name"]
                if affiliation.get("affiliationIdentifier"):
                    metax_contributor["member_of"]["identifier"] = affiliation["affiliationIdentifier"]
            else:
                del metax_contributor["member_of"]
            # Metax schema accepts only one identifier per creator
            # so we take first one
            if contributor.get("nameIdentifiers", None) and contributor["nameIdentifiers"][0].get(
                "nameIdentifier", None
            ):
                metax_contributor["identifier"] = contributor["nameIdentifiers"][0]["nameIdentifier"]
            else:
                del metax_contributor["identifier"]

            if contributor.get("contributorType", None):
                if contributor["contributorType"] == "DataCurator":
                    self.research_dataset["curator"].append(metax_contributor)
                elif contributor["contributorType"] == "RightsHolder":
                    self.research_dataset["rights_holder"].append(metax_contributor)
                else:
                    self.research_dataset["contributor"].append(metax_contributor)

        if not self.research_dataset["rights_holder"]:
            del self.research_dataset["rights_holder"]
        if not self.research_dataset["curator"]:
            del self.research_dataset["curator"]

    def _map_dates(self, dates: List) -> None:
        """Map dates.

        dates Updated  -> modified
        dates Issued    -> issued
        dates Collected -> temporal

        :param submitter_data: Dates data from datacite
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
        Inputs should be in degrees as geographic coordinate system (GCS) is used here.

        :param location: GeoLocations data from datacite
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

        :param location: Alternate identifiers data from datacite
        """
        LOG.info("Mapping alternate identifiers")
        LOG.debug(identifiers)
        self.research_dataset["other_identifier"] = []
        other_identifier: Dict[str, Any] = {
            "type": {
                "identifier": "",
                "in_scheme": "http://uri.suomi.fi/codelist/fairdata/identifier_type",
            },
            "notation": "",
        }
        for identifier in identifiers:
            other_identifier["notation"] = identifier["alternateIdentifier"]

            type = self.identifier_types[identifier["alternateIdentifierType"].lower()]

            other_identifier["type"]["identifier"] = type

        self.research_dataset["other_identifier"].append(other_identifier)
