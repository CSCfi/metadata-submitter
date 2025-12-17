"""Metax models"""

import re
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# Metax V3 API: https://metax.fairdata.fi/v3/swagger/
# Metax dataset: https://metax.fairdata.fi/v3/docs/user-guide/datasets-api/

DATA_CATALOG = "urn:nbn:fi:att:data-catalog-sd"
ACCESS_TYPE_URL = "http://uri.suomi.fi/codelist/fairdata/access_type/code/restricted"
LICENSE_URL = "http://uri.suomi.fi/codelist/fairdata/license/code/notspecified"
RESTRICTION_GROUND_URL = "http://uri.suomi.fi/codelist/fairdata/restriction_grounds/code/personal_data"


class Url(BaseModel):
    url: str


class Organization(BaseModel):
    pref_label: dict[str, str] | None = None
    external_identifier: str | None = None

    @model_validator(mode="after")
    def check_at_least_one(self) -> "Organization":
        if self.pref_label is None and self.external_identifier is None:
            raise ValueError("At least one of 'pref_label' or 'external_identifier' must be provided.")
        return self

    @field_validator("pref_label", mode="before")
    def convert_pref_label(cls: type["Organization"], value: str | dict[str, str]) -> dict[str, str]:
        """Convert pref_label to dict."""
        return convert_to_dict(value)


class Person(BaseModel):
    name: str
    external_identifier: str | None = None


class AccessType(Url):
    url: str = Field(default=ACCESS_TYPE_URL)


class License(Url):
    url: str = Field(default=LICENSE_URL)


class RestrictionGround(Url):
    url: str = Field(default=RESTRICTION_GROUND_URL)


class AccessRights(BaseModel):
    access_type: AccessType = Field(default_factory=AccessType)
    license: list[License] = Field(default_factory=lambda: [License()])
    restriction_grounds: list[RestrictionGround] = Field(default_factory=lambda: [RestrictionGround()])


class Roles(str, Enum):
    creator = "creator"
    publisher = "publisher"
    contributor = "contributor"


class Actor(BaseModel):
    organization: Organization
    roles: list[Roles]
    person: Person | None = None


class FieldOfScience(Url):
    pass


class Date(BaseModel):
    date: str

    @field_validator("date")
    def validate_date_format(cls: type["Date"], val: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
            raise ValueError(f"date must be YYYY-MM-DD, got {val}")
        return val


class Language(Url):
    pass


class Funder(BaseModel):
    organization: Organization


class Funding(BaseModel):
    funder: Funder | None = None
    funding_identifier: str | None = None


class Project(BaseModel):
    participating_organizations: list[Organization]
    funding: list[Funding] | None = None


class ReferenceLocation(Url):
    pass


class Spatial(BaseModel):
    geographic_name: str | None = None
    reference: ReferenceLocation | None = None
    custom_wkt: list[str] | None = None


class Temporal(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


class EntityType(Url):
    pass


class Entity(BaseModel):
    title: dict[str, str] | None = None
    entity_identifier: str
    type: EntityType | None = None


class RelationType(Url):
    pass


class Relation(BaseModel):
    entity: Entity
    relation_type: RelationType


class Theme(Url):
    pass


class DraftMetax(BaseModel):
    """Required fields for Metax draft version."""

    # required fields
    data_catalog: str = Field(default=DATA_CATALOG)
    title: dict[str, str]
    description: dict[str, str]
    persistent_identifier: str

    @field_validator("title", "description", mode="before")
    def convert_to_dict(cls: type["DraftMetax"], value: str | dict[str, str]) -> dict[str, str]:
        """Convert title and description to dict."""
        return convert_to_dict(value)


class MetaxFields(DraftMetax):
    """
    Metax fields.
    There are other additional Metax fields that are not mentioned here
    as they are extra info in Metax response body or not applicable to our case.
    """

    model_config = ConfigDict(extra="allow")

    # required fields
    access_rights: AccessRights = Field(default_factory=AccessRights)
    actors: list[Actor]
    keyword: list[str]
    # optional fields
    field_of_science: list[FieldOfScience] | None = None
    issued: str | None = None
    language: list[Language] | None = None
    projects: list[Project] | None = None
    spatial: list[Spatial] | None = None
    temporal: list[Temporal] | None = None
    # postpone for MVP
    relation: list[Relation] | None = None
    theme: list[Theme] | None = None


def convert_to_dict(value: str | dict[str, str]) -> dict[str, str]:
    """Convert value to a dict of string as {'en': value}."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"en": value}
    raise ValueError("Value must be a dict or a string.")
