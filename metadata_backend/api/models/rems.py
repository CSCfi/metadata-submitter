"""REMS models."""

from typing import TypeAlias

from pydantic import AliasChoices, BaseModel, Field

# REMS models used in the REMS API.
#


class RemsLicenseLocalization(BaseModel):
    """REMS license localisation."""

    title: str
    textcontent: str


class RemsCatalogueItemLocalization(BaseModel):
    """REMS catalogue item localisation."""

    model_config = {"populate_by_name": True}

    title: str
    discovery_url: str = Field(alias="infourl")


class RemsOrganization(BaseModel):
    """REMS organisation."""

    model_config = {"populate_by_name": True}

    id: str = Field(alias="organization/id")
    name: dict[str, str] = Field(alias="organization/name")  # language, string
    short_name: dict[str, str] = Field(alias="organization/short-name")  # language, string


class RemsLicense(BaseModel):
    """REMS license."""

    model_config = {"populate_by_name": True}

    id: int = Field(validation_alias=AliasChoices("license/id", "id"))
    licensetype: str
    localizations: dict[str, RemsLicenseLocalization]  # language, localization
    organization: RemsOrganization
    archived: bool
    enabled: bool


class RemsWorkflowDetails(BaseModel):
    """REMS workflow."""

    type: str
    licenses: list[RemsLicense]


class RemsWorkflow(BaseModel):
    """REMS workflows."""

    id: int
    title: str
    organization: RemsOrganization
    workflow: RemsWorkflowDetails
    archived: bool
    enabled: bool


class RemsResource(BaseModel):
    """REMS resource."""

    id: int
    resid: str
    organization: RemsOrganization
    licenses: list[RemsLicense]
    archived: bool
    enabled: bool


class RemsCatalogueItem(BaseModel):
    """REMS catalogue item."""

    model_config = {"populate_by_name": True}

    id: int
    resource_id: int = Field(alias="resource-id")
    resid: str
    organization: RemsOrganization
    localizations: dict[str, RemsCatalogueItemLocalization]  # language, localization
    archived: bool
    enabled: bool
    expired: bool


# REMS models used in the SD Submit API.
#


class License(BaseModel):
    """REMS license."""

    id: int
    title: str
    textcontent: str


class Workflow(BaseModel):
    """REMS workflow."""

    id: int
    title: str
    licenses: list[License]


class Organization(BaseModel):
    """REMS organisation."""

    id: str
    name: str
    workflows: list[Workflow]
    licenses: list[License]


OrganizationsMap: TypeAlias = dict[str, Organization]
Organizations: TypeAlias = list[Organization]
