"""Class for mapping Submitter metadata to Metax metadata."""
from copy import deepcopy
from typing import Any, Dict, List

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

    def __init__(self, metax_data: Dict, data: Dict) -> None:
        """Set variables.

        :param metax_data: Metax research_dataset metadata
        """
        self.person: Dict[str, Any] = {
            "name": "",
            "@type": "Person",
            "member_of": {"name": {"en": ""}, "@type": "Organization"},
            "identifier": "",
        }
        self.research_dataset = metax_data
        self.datacite_data = data

    def map_metadata(self) -> Dict[str, Any]:
        """Public class for actual mapping of metadata fields.

        :returns: Research dataset
        """
        LOG.info("Mapping datasite data to Metax metadata")
        LOG.debug("Data incomming for mapping: ", self.datacite_data)
        for key, value in self.datacite_data.items():
            if key == "creators":
                self._map_creators(value)
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
