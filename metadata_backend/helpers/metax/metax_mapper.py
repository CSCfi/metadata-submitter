"""Class for mapping Submitter metadata to Metax metadata."""
from typing import Any, Dict, List


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
                    "@id": "http://purl.org/dc/terms/identifier",
                    "title": "Identifier",
                    "description": "An unambiguous reference to the resource within a given context.",
                    "@type": "@id",
                    "minLength": 1,
                    "type": "string",
                    "format": "uri",
                    "example": ["http://orcid.org/0000-0002-1825-0097"],
                },
                "name": {
                    "@id": "http://xmlns.com/foaf/0.1/name",
                    "title": "Name",
                    "description": (
                        "This property contains a name of the agent. This property can be repeated for different "
                        "versions of the name (e.g. the name in different languages)"
                    ),
                    "@type": "http://www.w3.org/2001/XMLSchema#string",
                    "minLength": 1,
                    "type": "string",
                },
                "member_of": {
                    "@id": "http://www.w3.org/ns/org#memberOf",
                    "title": "Member of",
                    "description": (
                        "Indicates that a person is a member of the Organization with no indication of the "
                        "nature of that membership or the role played."
                    ),
                    "@type": "@id",
                    "type": "object",
                    "$ref": "#/definitions/Organization",
                },
                "contributor_type": {
                    "@id": "http://uri.suomi.fi/datamodel/ns/mrd#contributorType",
                    "title": "Contributor type",
                    "description": "Contributor type of the Agent. Reference data from DataCite.",
                    "@type": "@id",
                    "type": "array",
                    "items": {"type": "object", "$ref": "#/definitions/Concept"},
                },
            },
            "required": ["@type", "name", "member_of"],
        },
    }
    {
        "Organization": {
            "title": "Organization",
            "type": "object",
            "@id": "http://xmlns.com/foaf/0.1/Organization",
            "description": "An organization.",
            "minProperties": 1,
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
                    "title": "Contributor type",
                    "description": (
                        "Contributor type of the Organization. Based on the subset of the DataCite reference data."
                    ),
                    "@type": "@id",
                    "type": "array",
                    "items": {"type": "object", "$ref": "#/definitions/Concept"},
                },
            },
            "required": ["@type"],
        }
    }
    {
        "ResearchDataset": {
            # DOI
            "preferred_identifier": {
                "type": "string",
                "format": "uri",
            },
            # dates - Modified
            "modified": {
                "type": "string",
                "format": "date-time",
            },
            # dates - Issued
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
            # alternative id??
            "other_identifier": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/StructuredIdentifier"},
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
                "@type": "@id",
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/Project"},
            },
            # contributor - Rights Holder
            "rights_holder": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/ResearchAgent"},
            },
            # study/dataset type
            "theme": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/Concept"},
            },
            # language ?
            "language": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/langString"},
            },
            # geoLocations
            "spatial": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/Location"},
            },
            # dates - Collected ?
            "temporal": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/PeriodOfTime"},
            },
            # dataset from same folder/submission ?
            "relation": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/EntityRelation"},
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
            # contributors - Data Curator ??
            "curator": {
                "type": "array",
                "items": {"type": "object", "$ref": "#/definitions/ResearchAgent"},
            },
            # sizes - make standard to bytes
            "total_remote_resources_byte_size": {
                "type": "integer",
            },
        }
    }

    def __init__(self, metax_data: Dict, data: Dict) -> None:
        """Set variables.

        :param metax_data: Metax research_dataset metadata
        """
        #     self.study_data = data["study"]
        #     self.dataset_data = data["dataset"]
        self.research_dataset = metax_data
        self.datacite_data = data

    def map_metadata(self) -> Dict[str, Any]:
        """Public class for actual mapping of metadata fields.

        :returns: Research dataset
        """
        for key, value in self.datacite_data.items():
            if key == "creators":
                self._map_creators(value)
            # under discussion
            if key == "subjects":
                # self._map_field_of_science(value)
                pass
            if key == "keywords":
                self.research_dataset["keyword"] = {"en": value}
            if key == "contributors":
                # self._map_contributors(value)
                pass
            if key == "dates":
                # self._map_dates(value)
                pass
            if key == "geoLocation":
                # self._map_spatial(value)
                pass
            if key == "language":
                self.research_dataset["language"] = value
            if key == "alternateIdentifiers":
                # self._map_other_identifier(value)
                pass
            if key == "sizes":
                self.research_dataset["total_remote_resources_byte_size"] = int(value)
            if key == "type":
                # self._map_theme(value)
                pass
        return self.research_dataset

    def _map_creators(self, creators: List) -> None:
        """Map creators.

        :param creators: Creators data from datacite
        """
        self.research_dataset["creator"] = []
        for creator in creators:
            metax_creator: Dict[str, Any] = {
                "name": "",
                "@type": "Person",
                "member_of": {"name": {"en": ""}, "@type": "Organization"},
                "identifier": "",
            }
            metax_creator["name"] = creator["name"]
            # Metax schema accepts only one affiliation per creator
            # so we take first one
            if creator.get("affiliation", None):
                affiliation = creator["affiliation"][0]
                metax_creator["member_of"]["name"]["en"] = affiliation["name"]
                metax_creator["member_of"]["@type"] = "Organization"
                if affiliation.get("affiliationIdentifier"):
                    metax_creator["member_of"]["identifier"] = affiliation["affiliationIdentifier"]
            # Metax schema accepts only one identifier per creator
            # so we take first one
            else:
                metax_creator.pop("member_of")
            if creator.get("nameIdentifiers", None) and creator["nameIdentifiers"][0].get("nameIdentifier", None):
                metax_creator["identifier"] = creator["nameIdentifiers"][0]["nameIdentifier"]
            else:
                metax_creator.pop("identifier")
            self.research_dataset["creator"].append(metax_creator)
