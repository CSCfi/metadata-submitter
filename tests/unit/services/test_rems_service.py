"""Tests for finding a REMS license to reuse."""

import pytest
from typing_extensions import override

from metadata_backend.api.models.rems import (
    RemsLicense,
    RemsLicenseLocalization,
    RemsOrganization,
)
from metadata_backend.services.rems_service import (
    REMS_LICENSE_TYPE_TEXT,
    RemsServiceHandler,
)

ORG_ID = "org-1"
OTHER_ORG_ID = "org-2"

LICENSE_ID = 1
OTHER_LICENSE_ID = 2

# The id the mock REMS gives a license it is asked to create.
CREATED_LICENSE_ID = 3

TITLE = "Terms"
TEXT_CONTENT = "You agree."


def _localisations(
    title: str = TITLE, text_content: str = TEXT_CONTENT, *, language: str = "en"
) -> dict[str, RemsLicenseLocalization]:
    return {language: RemsLicenseLocalization(title=title, textcontent=text_content)}


def _license(
    license_id: int,
    organisation_id: str,
    localisations: dict[str, RemsLicenseLocalization],
    *,
    licensetype: str = REMS_LICENSE_TYPE_TEXT,
) -> RemsLicense:
    return RemsLicense(
        id=license_id,
        licensetype=licensetype,
        localizations=localisations,
        organization=RemsOrganization(
            id=organisation_id,
            name={"en": "name"},
            short_name={"en": "short"},
        ),
    )


class _MockRemsServiceHandler(RemsServiceHandler):
    def __init__(self, licenses: list[RemsLicense]) -> None:
        self.gets = 0
        self.creates = 0
        self.licenses = licenses
        self._license_cache = self.new_license_cache()

    @override
    async def get_licenses(self) -> list[RemsLicense]:
        self.gets += 1
        return list(self.licenses)

    @override
    async def create_license(self, organization_id: str, localizations: dict[str, RemsLicenseLocalization]) -> int:
        self.creates += 1
        created = _license(CREATED_LICENSE_ID, organization_id, localizations)
        self.licenses.append(created)
        return created.id


@pytest.mark.parametrize(
    "existing_licenses,new_localisations",
    [
        ([_license(LICENSE_ID, ORG_ID, _localisations())], _localisations()),
        (
            [_license(OTHER_LICENSE_ID, ORG_ID, _localisations()), _license(LICENSE_ID, ORG_ID, _localisations())],
            _localisations(),
        ),
        (
            [_license(LICENSE_ID, ORG_ID, _localisations() | _localisations(language="fi"))],
            _localisations(language="fi") | _localisations(),
        ),
    ],
    ids=[
        "one existing license with one localisation",
        "one existing licence with one localisation for the organisation",
        "one existing license with two localisations",
    ],
)
@pytest.mark.asyncio
async def test_get_or_create_license_existing(
    existing_licenses: list[RemsLicense], new_localisations: dict[str, RemsLicenseLocalization]
):
    rems = _MockRemsServiceHandler(existing_licenses)

    assert await rems.get_or_create_license(ORG_ID, new_localisations) == LICENSE_ID
    assert rems.creates == 0


@pytest.mark.parametrize(
    "existing_licenses,organisation_id,new_localisations",
    [
        ([], ORG_ID, _localisations()),
        ([_license(LICENSE_ID, ORG_ID, _localisations())], OTHER_ORG_ID, _localisations()),
        ([_license(LICENSE_ID, ORG_ID, _localisations())], ORG_ID, _localisations(text_content="Other")),
        ([_license(LICENSE_ID, ORG_ID, _localisations())], ORG_ID, _localisations(title="Other")),
        ([_license(LICENSE_ID, ORG_ID, _localisations())], ORG_ID, _localisations(language="fi")),
        ([_license(LICENSE_ID, ORG_ID, _localisations())], ORG_ID, _localisations() | _localisations(language="fi")),
        ([_license(LICENSE_ID, ORG_ID, _localisations(), licensetype="link")], ORG_ID, _localisations()),
    ],
    ids=[
        "no existing licenses",
        "no existing licenses for the organisation",
        "different text",
        "different title",
        "different language",
        "additional language",
        "not a text license",
    ],
)
@pytest.mark.asyncio
async def test_get_or_create_license_new(
    existing_licenses: list[RemsLicense],
    organisation_id: str,
    new_localisations: dict[str, RemsLicenseLocalization],
):
    rems = _MockRemsServiceHandler(existing_licenses)

    assert await rems.get_or_create_license(organisation_id, new_localisations) == CREATED_LICENSE_ID
    assert rems.creates == 1


@pytest.mark.parametrize(
    "existing_licenses,license_id,creates",
    [
        ([_license(LICENSE_ID, ORG_ID, _localisations())], LICENSE_ID, 0),
        ([], CREATED_LICENSE_ID, 1),
    ],
    ids=[
        "an existing license",
        "a new license",
    ],
)
@pytest.mark.asyncio
async def test_get_or_create_license_cache(existing_licenses: list[RemsLicense], license_id: int, creates: int):
    rems = _MockRemsServiceHandler(existing_licenses)

    assert await rems.get_or_create_license(ORG_ID, _localisations()) == license_id
    assert await rems.get_or_create_license(ORG_ID, _localisations()) == license_id
    assert rems.creates == creates
    # The first call gets the licenses from REMS, the second is served from the cache.
    assert rems.gets == 1


@pytest.mark.asyncio
async def test_get_or_create_license_cache_refresh():
    rems = _MockRemsServiceHandler([])

    # Process a new license, any existing licenses are retrieved from REMS.
    # No existing licenses exist in this test. A new license is created
    # in REMS and cached.
    await rems.get_or_create_license(ORG_ID, _localisations("Other terms"))
    assert rems.gets == 1
    assert rems.creates == 1

    # Something else adds a second license to REMS. The cache does not
    # know about it.
    rems.licenses.append(_license(LICENSE_ID, ORG_ID, _localisations()))

    # Process the second license. The cache does not contain it so any
    # existing licenses are retrieved from REMS. The first and second
    # licenses are retrieved from REMS and cached. The second license
    # is found from cache.
    assert await rems.get_or_create_license(ORG_ID, _localisations()) == LICENSE_ID
    assert rems.gets == 2
    assert rems.creates == 1
