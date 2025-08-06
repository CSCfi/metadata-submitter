"""API models."""

import enum
from datetime import datetime
from typing import Any, ClassVar, List, Optional

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class SubmissionWorkflow(enum.Enum):
    """Submission workflow."""

    FEGA = "FEGA"
    BP = "Bigpicture"
    SDS = "SDSX"


class JsonModel(BaseModel):
    """Model that uses PEP8 snake case and serializes JSON using camel case."""

    model_config: ClassVar[ConfigDict] = {"populate_by_name": True}

    def json_dump(self) -> dict[str, Any]:
        """
        Serialize the model to a dictionary for JSON using camel case and excluding None fields.

        :return: A dictionary representation of the model for JSON.
        """
        return super().model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )


class ApiKey(BaseModel):
    """An API key."""

    key_id: str
    created_at: datetime | None = None


class User(BaseModel):
    """A user."""

    user_id: str
    user_name: str
    projects: list["Project"] = []


class Project(BaseModel):
    """A user project."""

    project_id: str


class Object(JsonModel):
    """A metadata object."""

    object_id: str = Field(..., alias="objectId")
    submission_id: str = Field(..., alias="submissionId")
    schema_type: str = Field(..., alias="schema")


class ChecksumType(enum.Enum):
    """File checksum type."""

    MD5 = "md5"
    SHA256 = "sha256"


class File(JsonModel):
    """A file associated with the submission."""

    file_id: Optional[str] = Field(None, alias="fileId")
    submission_id: Optional[str] = Field(None, alias="submissionId")
    object_id: Optional[str] = Field(None, alias="objectId")
    path: str
    bytes: Optional[int] = None
    unencrypted_checksum: Optional[str] = Field(None, alias="unencryptedChecksum")
    unencrypted_checksum_type: Optional[ChecksumType] = Field(None, alias="unencryptedChecksumType")
    encrypted_checksum: Optional[str] = Field(None, alias="encryptedChecksum")
    encrypted_checksum_type: Optional[ChecksumType] = Field(None, alias="encryptedChecksumType")


class Registration(JsonModel):
    """A registration entry to an external service."""

    submission_id: str = Field(None, alias="submissionId")
    object_id: Optional[str] = Field(None, alias="objectId")
    schema_type: Optional[str] = Field(None, alias="schema")
    title: str
    description: str
    doi: str
    metax_id: Optional[str] = Field(None, alias="metaxId")
    datacite_url: Optional[str] = Field(None, alias="dataciteUrl")
    rems_url: Optional[str] = Field(None, alias="remsUrl")
    rems_resource_id: Optional[str] = Field(None, alias="remsResourceId")
    rems_catalogue_id: Optional[str] = Field(None, alias="remsCatalogueId")


class Rems(JsonModel):
    """REMS information."""

    workflow_id: int = Field(..., alias="workflowId")
    organization_id: str = Field(..., alias="organizationId")
    licenses: List[int]


# Doi information stored in submission.json.
#


class AffiliationIdentifier(JsonModel):
    """Affiliation of the creator or contributor in the DOI metadata."""

    name: Optional[str] = None
    affiliation_identifier: Optional[str] = Field(None, alias="affiliationIdentifier")


class NameIdentifier(JsonModel):
    """Unique identifier of the creator or contributor in the DOI metadata."""

    name_identifier: Optional[str] = Field(None, alias="nameIdentifier")


class Creator(JsonModel):
    """An author listed as a creator in the DOI metadata."""

    given_name: str = Field(..., alias="givenName")
    family_name: str = Field(..., alias="familyName")
    affiliation: list[AffiliationIdentifier]
    name_identifiers: Optional[list[NameIdentifier]] = Field(None, alias="nameIdentifiers")


class Contributor(JsonModel):
    """An author listed as a contributor in the DOI metadata."""

    given_name: str = Field(..., alias="givenName")
    family_name: str = Field(..., alias="familyName")
    affiliation: List[AffiliationIdentifier]
    name_identifiers: Optional[List[NameIdentifier]] = Field(None, alias="nameIdentifiers")


class Subject(JsonModel):
    """The subject area in the DOI metadata."""

    subject: str


class DoiDate(JsonModel):
    """A date related to a publication in the DOI metadata."""

    date: str
    date_type: str = Field(..., alias="dateType")
    date_information: Optional[str] = Field(None, alias="dateInformation")


class DoiDescription(JsonModel):
    """Additional information associated with the DOI."""

    description: Optional[str] = None
    description_type: Optional[str] = Field(None, alias="descriptionType")
    lang: Optional[str] = None


class GeoLocationPoint(JsonModel):
    """A point in the geographic coordinate system."""

    point_longitude: Optional[str] = Field(None, alias="pointLongitude")
    point_latitude: Optional[str] = Field(None, alias="pointLatitude")


class GeoLocationBox(JsonModel):
    """A box in the geographic coordinate system."""

    west_bound_longitude: Optional[str] = Field(None, alias="westBoundLongitude")
    east_bound_longitude: Optional[str] = Field(None, alias="eastBoundLongitude")
    south_bound_latitude: Optional[str] = Field(None, alias="southBoundLatitude")
    north_bound_latitude: Optional[str] = Field(None, alias="northBoundLatitude")


class GeoLocationPolygonItem(JsonModel):
    """A polygon in the geographic coordinate system."""

    point_longitude: Optional[str] = Field(None, alias="pointLongitude")
    point_latitude: Optional[str] = Field(None, alias="pointLatitude")


class GeoLocation(JsonModel):
    """A location in the geographic coordinate system."""

    geo_location_place: Optional[str] = Field(None, alias="geoLocationPlace")
    geo_location_point: Optional[GeoLocationPoint] = Field(None, alias="geoLocationPoint")
    geo_location_box: Optional[GeoLocationBox] = Field(None, alias="geoLocationBox")
    geo_location_polygon: Optional[List[GeoLocationPolygonItem]] = Field(None, alias="geoLocationPolygon")


class RelatedIdentifier(JsonModel):
    """A related identifier associated with the DOI."""

    related_identifier: str = Field(..., alias="relatedIdentifier")
    related_identifier_type: str = Field(..., alias="relatedIdentifierType")
    relation_type: str = Field(..., alias="relationType")
    related_metadata_scheme: Optional[str] = Field(None, alias="relatedMetadataScheme")
    scheme_uri: Optional[str] = Field(None, alias="schemeUri")
    scheme_type: Optional[str] = Field(None, alias="schemeType")
    resource_type_general: Optional[str] = Field(None, alias="resourceTypeGeneral")


class AlternateIdentifier(JsonModel):
    """An alternative identifier associated with the DOI."""

    alternate_identifier: str = Field(..., alias="alternateIdentifier")
    alternate_identifier_type: str = Field(..., alias="alternateIdentifierType")


class FundingReference(JsonModel):
    """A funding reference associated with the DOI."""

    funder_name: str = Field(..., alias="funderName")
    funder_identifier: str = Field(..., alias="funderIdentifier")
    funder_identifier_type: str = Field(..., alias="funderIdentifierType")
    award_number: Optional[str] = Field(None, alias="awardNumber")
    award_title: Optional[str] = Field(None, alias="awardTitle")
    award_uri: Optional[str] = Field(None, alias="awardUri")


class DoiInfo(JsonModel):
    """DOI information."""

    creators: List[Creator]
    contributors: Optional[List[Contributor]] = Field(None)
    subjects: List[Subject] = Field(None)
    keywords: str
    dates: Optional[List[DoiDate]] = Field(None)
    descriptions: Optional[List[DoiDescription]] = Field(None)
    geo_locations: Optional[List[GeoLocation]] = Field(None, alias="geoLocations")
    language: Optional[str] = None
    related_identifiers: Optional[List[RelatedIdentifier]] = Field(None, alias="relatedIdentifiers")
    alternate_identifiers: Optional[List[AlternateIdentifier]] = Field(None, alias="alternateIdentifiers")
    sizes: Optional[List[str]] = None
    formats: Optional[List[str]] = None
    funding_references: Optional[List[FundingReference]] = Field(None, alias="fundingReferences")


# Submission
#


class Submission(JsonModel):
    """A submission that contains REMS and DOI information."""

    # Some submission document fields are only stored in table columns rather than in the
    # document. These fields are injected into the document only when it is retrieved. Some
    # submission document fields are stored both in the document and the table columns.

    project_id: str = Field(..., alias="projectId")  # Stored also in a database column.
    submission_id: Optional[str] = Field(None, alias="submissionId")  # Stored only in a database column.
    name: str  # Stored also as a database column.
    text_name: Optional[str] = None  # Not stored.
    title: str
    description: str
    workflow: str  # Stored also in a database column.
    date_created: Optional[int] = Field(None, alias="dateCreated")  # Stored only in a database column.
    date_published: Optional[int] = Field(None, alias="datePublished")  # Stored only in a database column.
    last_modified: Optional[int] = Field(None, alias="lastModified")  # Stored only in a database column.
    published: Optional[bool] = None  # Stored only in a database column.
    doi_info: Optional[DoiInfo] = Field(None, alias="doiInfo")
    rems: Optional[Rems] = None
    linked_folder: Optional[str] = Field(None, alias="linkedFolder")  # Stored only in a database column.
