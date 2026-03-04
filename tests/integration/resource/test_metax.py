"""Test retrieving Metax mapping resource data."""

import pytest

from metadata_backend.api.resource.metax import (
    fetch_metax_mapping_geo_locations,
    fetch_metax_mapping_languages,
)


@pytest.mark.skip(reason="Test skipped because http://www.lexvo.org became very slow in March 2026")
async def test_fetch_metax_mapping_languages() -> None:
    languages = await fetch_metax_mapping_languages()
    assert len(languages) > 1


async def test_fetch_metax_mapping_geo_locations() -> None:
    geo_locations = await fetch_metax_mapping_geo_locations()
    assert len(geo_locations) > 1
