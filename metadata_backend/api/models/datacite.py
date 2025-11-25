"""Datacite models."""

from __future__ import annotations

from typing import Iterable, Literal, Optional

from pydantic import Field, model_validator
from pydantic_string_url import AnyUrl

from .base import StrictBaseModel

# https://datacite-metadata-schema.readthedocs.io/en/4.5/properties/


# Controlled vocabularies
#

RelationType = Literal[
    "IsCitedBy",
    "Cites",
    "IsSupplementTo",
    "IsSupplementedBy",
    "IsContinuedBy",
    "Continues",
    "IsNewVersionOf",
    "IsPreviousVersionOf",
    "IsPartOf",
    "HasPart",
    "IsPublishedIn",
    "HasPublication",
    "IsReferencedBy",
    "References",
    "IsDocumentedBy",
    "Documents",
    "IsCompiledBy",
    "Compiles",
    "IsVariantFormOf",
    "IsOriginalFormOf",
    "IsIdenticalTo",
    "IsReviewedBy",
    "Reviews",
    "IsDerivedFrom",
    "IsSourceOf",
    "IsRequiredBy",
    "Requires",
    "IsObsoletedBy",
    "Obsoletes",
]

ContributorType = Literal[
    "ContactPerson",
    "DataCollector",
    "DataCurator",
    "DataManager",
    "Distributor",
    "Editor",
    "HostingInstitution",
    "Other",
    "Producer",
    "ProjectLeader",
    "ProjectManager",
    "ProjectMember",
    "RegistrationAgency",
    "RegistrationAuthority",
    "RelatedPerson",
    "Researcher",
    "ResearchGroup",
    "RightsHolder",
    "Supervisor",
    "Sponsor",
    "WorkPackageLeader",
]

NameType = Literal["Personal", "Organizational"]

IdentifierType = Literal["DOI"]

RelatedIdentifierType = Literal[
    "ARK",
    "arXiv",
    "bibcode",
    "DOI",
    "EAN13",
    "EISSN",
    "Handle",
    "IGSN",
    "ISBN",
    "ISSN",
    "ISTC",
    "LISSN",
    "LSID",
    "PMID",
    "PURL",
    "UPC",
    "URL",
    "URN",
    "w3id",
]

DescriptionType = Literal["Abstract", "Methods", "SeriesInformation", "TableOfContents", "TechnicalInfo", "Other"]

ResourceTypeGeneral = Literal[
    "Audiovisual",
    "Book",
    "BookChapter",
    "Collection",
    "ComputationalNotebook",
    "ConferencePaper",
    "ConferenceProceeding",
    "DataPaper",
    "Dataset",
    "Dissertation",
    "Event",
    "Image",
    "InteractiveResource",
    "Instrument",
    "Journal",
    "JournalArticle",
    "Model",
    "OutputManagementPlan",
    "PeerReview",
    "PhysicalObject",
    "Preprint",
    "Report",
    "Service",
    "Software",
    "Sound",
    "Standard",
    "StudyRegistration",
    "Text",
    "Workflow",
    "Other",
]

FunderIdentifierType = Literal["Crossref Funder ID", "GRID", "ISNI", "ROR", "Other"]

DateType = Literal[
    "Accepted",
    "Available",
    "Copyrighted",
    "Collected",
    "Created",
    "Issued",
    "Submitted",
    "Updated",
    "Valid",
    "Withdrawn",
    "Other",
]


# Utilities
#


def _remove_whitespace(values: dict, fields: Iterable[str]) -> dict:  # type: ignore
    """
    Remove whitespace from the specified fields in a dictionary of model values.

    :param fields: Iterable of field names to clean
    :param values: Dictionary of model field values
    :return: The model values with whitespace removed from the specified fields
    """
    for field in fields:
        if field in values and values[field] is not None:
            val = values[field]
            if any(c.isspace() for c in val):
                # Remove whitespace.
                values[field] = "".join(val.split())
    return values


# Models
#


class NameIdentifier(StrictBaseModel):
    """
    Datacite unique identifier for a creator or contributor in a standard scheme.

    Attributes:
    nameIdentifier: The identifier value, usually given as a URI.
        Example: "https://orcid.org/0000-0002-1825-0097".
    nameIdentifierScheme: The name of the identifier scheme.
        Example: "ORCID", "ISNI", "ROR".
    schemeUri: The URI of the identifier scheme.
        Example: "https://orcid.org".
    """

    nameIdentifier: str
    nameIdentifierScheme: str
    schemeUri: AnyUrl | None = None


class Affiliation(StrictBaseModel):
    """Datacite affiliation."""

    name: str
    affiliationIdentifier: str | None = None
    affiliationIdentifierScheme: str | None = None
    schemeUri: AnyUrl | None = None


class Creator(StrictBaseModel):
    """Datacite creator."""

    name: str
    nameType: NameType | None = None
    givenName: str | None = None
    familyName: str | None = None
    nameIdentifiers: list[NameIdentifier] | None = None
    affiliation: list[Affiliation] | None = None

    @model_validator(mode="before")
    @classmethod
    def _model_validator_name(cls: type["Creator"], values: dict) -> dict:  # type: ignore
        """Set name and nameType if familyName and givenName are provided."""
        given = values.get("givenName")
        family = values.get("familyName")

        if given and family:
            values["name"] = f"{family}, {given}"
            values["nameType"] = "Personal"
        return values


class Publisher(StrictBaseModel):
    name: str
    publisherIdentifier: AnyUrl | None = None
    publisherIdentifierScheme: str | None = None
    schemeUri: AnyUrl | None = None


class Contributor(StrictBaseModel):
    """Datacite contributor."""

    name: str
    contributorType: ContributorType
    nameType: NameType | None = None
    givenName: str | None = None
    familyName: str | None = None
    nameIdentifiers: list[NameIdentifier] | None = None
    affiliation: list[Affiliation] | None = None

    @model_validator(mode="before")
    @classmethod
    def _model_validator_name(cls: type["Contributor"], values: dict) -> dict:  # type: ignore
        """Set name and nameType if familyName and givenName are provided."""
        given = values.get("givenName")
        family = values.get("familyName")

        if given and family:
            values["name"] = f"{family}, {given}"
            values["nameType"] = "Personal"
        return values


class Title(StrictBaseModel):
    """Datacite title."""

    title: str
    titleType: str | None = None


class Subject(StrictBaseModel):
    """Datacite subject."""

    subject: str
    subjectScheme: str | None = None
    schemeUri: AnyUrl | None = None
    valueUri: AnyUrl | None = None
    classificationCode: str | None = None


class Date(StrictBaseModel):
    """Datacite date."""

    date: str
    dateType: DateType
    dateInformation: str | None = None


class Identifier(StrictBaseModel):
    """Datacite identifier."""

    identifier: str
    identifierType: IdentifierType


class RelatedIdentifier(StrictBaseModel):
    """Datacite related identifier."""

    relatedIdentifier: str
    relatedIdentifierType: RelatedIdentifierType
    relationType: RelationType
    relatedMetadataScheme: str | None = None
    schemeUri: AnyUrl | None = None
    schemeType: str | None = None
    resourceTypeGeneral: ResourceTypeGeneral | None = None

    @model_validator(mode="before")
    @classmethod
    def model_validator_remove_whitespace(cls: type["RelatedIdentifier"], values: dict) -> dict:  # type: ignore
        """Remove whitespace from relationType and resourceTypeGeneral before validation."""
        return _remove_whitespace(values, ["relationType", "resourceTypeGeneral"])


class AlternateIdentifier(StrictBaseModel):
    """Datacite alternative identifier."""

    alternateIdentifier: str
    alternateIdentifierType: str


class Rights(StrictBaseModel):
    """Datacite rights."""

    rights: str
    rightsUri: AnyUrl | None = None
    rightsIdentifier: str | None = None
    rightsIdentifierScheme: str | None = None
    schemeUri: AnyUrl | None = None


class Description(StrictBaseModel):
    """Datacite description."""

    description: str
    descriptionType: DescriptionType | None = None
    lang: str | None = None

    @model_validator(mode="before")
    @classmethod
    def model_validator_remove_whitespace(cls: type["Description"], values: dict) -> dict:  # type: ignore
        """Remove whitespace from descriptionType before validation."""
        return _remove_whitespace(values, ["descriptionType"])


class GeoLocationPoint(StrictBaseModel):
    """Datacite geographic location point."""

    pointLatitude: float
    pointLongitude: float


class GeoLocationBox(StrictBaseModel):
    """Datacite geographic location box."""

    westBoundLongitude: float
    eastBoundLongitude: float
    southBoundLatitude: float
    northBoundLatitude: float


class GeoLocationPolygonPoint(StrictBaseModel):
    """Datacite geographic polygon."""

    polygonPoint: GeoLocationPoint | None = None
    inPolygonPoint: GeoLocationPoint | None = None

    @model_validator(mode="after")
    def check_lne_exists(self) -> "GeoLocationPolygonPoint":
        if (self.polygonPoint is None and self.inPolygonPoint is None) or (
            self.polygonPoint is not None and self.inPolygonPoint is not None
        ):
            raise ValueError("Exactly one of 'polygonPoint' or 'inPolygonPoint' must be provided")
        return self


class GeoLocation(StrictBaseModel):
    """Datacite geographic location."""

    geoLocationPlace: str | None = None
    geoLocationPoint: GeoLocationPoint | None = None
    geoLocationBox: GeoLocationBox | None = None
    geoLocationPolygon: list[GeoLocationPolygonPoint] | None = None


class FundingReference(StrictBaseModel):
    """Datacite funding reference."""

    funderName: str
    funderIdentifier: str | None = None
    funderIdentifierType: FunderIdentifierType | None = None
    schemeUri: AnyUrl | None = None
    awardNumber: str | None = None
    awardUri: AnyUrl | None = None
    awardTitle: str | None = None


class ResourceType(StrictBaseModel):
    """Resource type."""

    resourceTypeGeneral: ResourceTypeGeneral = Field(default="Dataset")
    resourceType: Optional[str] = None

    @model_validator(mode="after")
    def model_validator_default_resource_type(self) -> "ResourceType":
        """Set default resource type to match general resource type."""
        if self.resourceType is None:
            self.resourceType = self.resourceTypeGeneral
        return self


class DataCiteMetadata(StrictBaseModel):
    """Datacite metadata."""

    identifiers: list[Identifier] | None = None  # Supported but ignored
    titles: list[Title] | None = None  # TODO(improve): Override default title during processing.
    creators: list[Creator]
    publisher: Publisher
    publicationYear: int | None = None  # Supported but ignored
    version: str | None = None
    rightsList: list[Rights] | None = None
    types: ResourceType = ResourceType(resourceTypeGeneral="Dataset")
    contributors: list[Contributor] | None = None
    subjects: list[Subject] | None = None
    dates: list[Date] | None = None
    language: str | None = None
    relatedIdentifiers: list[RelatedIdentifier] | None = None
    alternateIdentifiers: list[AlternateIdentifier] | None = None
    sizes: list[str] | None = None
    formats: list[str] | None = None
    descriptions: list[Description] | None = None
    geoLocations: list[GeoLocation] | None = None
    fundingReferences: list[FundingReference] | None = None
