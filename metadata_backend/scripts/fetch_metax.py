#!/usr/bin/env python3
import asyncio

from metadata_backend.api.resource.metax import (
    MetaxMappingResourceType,
    fetch_metax_mapping_geo_locations,
    fetch_metax_mapping_languages,
    write_metax_mapping_geo_locations,
    write_metax_mapping_languages,
)
from metadata_backend.helpers.logger import LOG


async def main() -> None:
    LOG.info("Fetching latest Metax mapping languages.")
    languages = await fetch_metax_mapping_languages()
    LOG.info(f"Fetched {len(languages)} languages")

    LOG.info("Fetching latest Metax mapping geo locations.")
    locations = await fetch_metax_mapping_geo_locations()
    LOG.info(f"Fetched {len(locations)} geo locations")

    LOG.info("Updating languages.json file.")
    write_metax_mapping_languages(MetaxMappingResourceType.METAX_MAPPING_LANGUAGES, languages)

    LOG.info("Writing geo_locations.json.")
    write_metax_mapping_geo_locations(MetaxMappingResourceType.METAX_MAPPING_GEO_LOCATIONS, locations)


if __name__ == "__main__":
    asyncio.run(main())
