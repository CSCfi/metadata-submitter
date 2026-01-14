"""Resource data for Metax mapping."""

import asyncio
import json
from enum import Enum
from pathlib import Path
from typing import Any, cast

from aiohttp import ClientSession
from pydantic import BaseModel, TypeAdapter
from rdflib import Graph, Literal, Namespace

from metadata_backend.helpers.logger import LOG

METAX_RESOURCE_ROOT = Path(__file__).parent.parent.parent / "resource" / "metax"


class MetaxMappingResourceType(Enum):
    """Metax mapping resource type."""

    METAX_MAPPING_LANGUAGES = "languages.json"
    METAX_MAPPING_GEO_LOCATIONS = "geo_locations.json"


class MetaxMappingLanguage(BaseModel):
    """Languages for Metax mapping."""

    label: str
    uri: str


class MetaxMappingGeoLocation(BaseModel):
    """Geolocations for Metax mapping."""

    pref_label: dict[str, str]
    uri: str


MetaxMappingLanguages = dict[str, MetaxMappingLanguage]
MetaxMappingGeoLocations = list[MetaxMappingGeoLocation]


async def fetch_metax_mapping_languages() -> MetaxMappingLanguages:
    """Fetch languages for Metax mapping."""

    langs = {}
    iso_langs = {}

    # Parsing ISO 639-1, ISO 639-2 and ISO 639-3 language format
    lexvo_urls = [
        "http://www.lexvo.org/resources/lexvo-iso639-3.tsv",
        "http://www.lexvo.org/resources/lexvo-iso639-2.tsv",
        "http://www.lexvo.org/resources/lexvo-iso639-1.tsv",
    ]
    async with ClientSession() as session:
        for url in lexvo_urls:
            async with session.get(url) as resp:
                resp.raise_for_status()
                lexvo_text = await resp.text()
                lexvo_list = [lang.split("\t") for lang in lexvo_text.split("\n")]
                lexvo_dict = {lang[0]: lang[1] for lang in lexvo_list[:-1]}

            # The keys are language codes of 2 and 3 chars, and values are URLs
            iso_langs.update(lexvo_dict)

        # Parsing languages and their sub-tags
        iana_url = "https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry"
        async with session.get(iana_url) as resp:
            resp.raise_for_status()
            lang_text = await resp.text()
            lang_list = [lang.split("\n") for lang in lang_text.split("\n%%\n")]

    # Filter languages by "type: language" to reduce noise
    # We get keys that are language codes (subtag field), and values are language names (description field)
    lang_dict = {
        lang[1].split(": ")[1]: lang[2].split(": ")[1]
        for lang in lang_list[1:]
        if lang[0].split(": ")[1] in {"language"}
    }

    n_matches = 0
    no_matches = 0
    for k, v in lang_dict.items():
        v = v.lower()
        try:
            langs[k] = {
                "label": v,
                "uri": iso_langs[k],
            }
            n_matches += 1
        except KeyError:
            # We expect that not all languages will match.
            LOG.error("No language match for %r and %r", k, v)
            no_matches += 1
            pass
    LOG.error("%i languages matched, and %i didn't", n_matches, no_matches)

    return TypeAdapter(MetaxMappingLanguages).validate_python(langs)


async def fetch_metax_mapping_geo_locations() -> MetaxMappingGeoLocations:
    """Fetch geolocations for Metax mapping."""

    location_url = "https://api.finto.fi/rest/v1/yso-paikat/data?format=text/turtle"
    skos = Namespace("http://www.w3.org/2004/02/skos/core#")
    yso_namespace = "http://www.yso.fi/onto/yso"

    async with ClientSession() as session:
        async with session.get(location_url) as resp:
            resp.raise_for_status()
            data = await resp.text()

    g = Graph()
    await asyncio.to_thread(lambda: g.parse(data=data, format="turtle"))

    locations: list[dict[str, Any]] = []

    for subject in g.subjects(predicate=skos.prefLabel):
        uri_str = str(subject)

        if not uri_str.startswith(yso_namespace):
            continue

        pref_labels = {}

        for object in g.objects(subject=subject, predicate=skos.prefLabel):
            if cast(Literal, object).language is not None:
                lang = cast(Literal, object).language
                pref_labels[lang] = str(object)

        if not any([loc["uri"] == uri_str for loc in locations]):
            locations.append({"pref_label": pref_labels, "uri": uri_str})

    return TypeAdapter(MetaxMappingGeoLocations).validate_python(locations)


def _resource_file(data_type: MetaxMappingResourceType) -> Path:
    return METAX_RESOURCE_ROOT / data_type.value


def _read_resource_file(data_type: MetaxMappingResourceType) -> str:
    return _resource_file(data_type).read_text(encoding="utf-8")


def _read_metax_mapping_languages() -> MetaxMappingLanguages:
    data = _read_resource_file(MetaxMappingResourceType.METAX_MAPPING_LANGUAGES)
    return TypeAdapter(MetaxMappingLanguages).validate_python(json.loads(data))


def _read_metax_mapping_geo_locations() -> MetaxMappingGeoLocations:
    data = _read_resource_file(MetaxMappingResourceType.METAX_MAPPING_GEO_LOCATIONS)
    return TypeAdapter(MetaxMappingGeoLocations).validate_python(json.loads(data))


METAX_MAPPING_LANGUAGES = _read_metax_mapping_languages()
METAX_MAPPING_GEO_LOCATIONS = _read_metax_mapping_geo_locations()


def _write_resource_file(data_type: MetaxMappingResourceType, data: Any) -> None:
    text = json.dumps(data, indent=4, sort_keys=True, ensure_ascii=False) + "\n"
    _resource_file(data_type).write_text(text, encoding="utf-8")


def write_metax_mapping_languages(data_type: MetaxMappingResourceType, languages: MetaxMappingLanguages) -> None:
    _write_resource_file(data_type, {k: v.model_dump() for k, v in languages.items()})


def write_metax_mapping_geo_locations(data_type: MetaxMappingResourceType, locations: MetaxMappingGeoLocations) -> None:
    _write_resource_file(data_type, [m.model_dump() for m in locations])
