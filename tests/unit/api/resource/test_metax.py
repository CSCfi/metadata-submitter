"""Test Metax mapping resource files."""

from unittest.mock import patch

from pydantic import TypeAdapter

from metadata_backend.api.resource.metax import (
    METAX_MAPPING_GEO_LOCATIONS,
    METAX_MAPPING_LANGUAGES,
    MetaxMappingGeoLocations,
    MetaxMappingLanguages,
    MetaxMappingResourceType,
    write_metax_mapping_geo_locations,
    write_metax_mapping_languages,
)


def test_read_write_metax_mapping_languages(tmp_path):
    with patch("metadata_backend.api.resource.metax._resource_file") as mock_resource_file:
        tmp_file = tmp_path / "languages.json"

        mock_resource_file.return_value = tmp_file

        # Write existing data to a tmp file.
        write_metax_mapping_languages(MetaxMappingResourceType.METAX_MAPPING_LANGUAGES, METAX_MAPPING_LANGUAGES)

        assert tmp_file.exists()

        # Read data from tmp file.
        languages = TypeAdapter(MetaxMappingLanguages).validate_json(tmp_file.read_text(encoding="utf-8"))
        assert languages == METAX_MAPPING_LANGUAGES


def test_read_write_metax_mapping_geo_locations(tmp_path):
    with patch("metadata_backend.api.resource.metax._resource_file") as mock_resource_file:
        tmp_file = tmp_path / "geo_locations.json"

        mock_resource_file.return_value = tmp_file

        # Write existing data to a tmp file.
        write_metax_mapping_geo_locations(
            MetaxMappingResourceType.METAX_MAPPING_GEO_LOCATIONS, METAX_MAPPING_GEO_LOCATIONS
        )

        assert tmp_file.exists()

        # Read data from tmp file.
        json = tmp_file.read_text(encoding="utf-8")
        locations = TypeAdapter(MetaxMappingGeoLocations).validate_json(json)
        assert locations == METAX_MAPPING_GEO_LOCATIONS
