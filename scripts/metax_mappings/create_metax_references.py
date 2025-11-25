#!/usr/bin/env python3
"""Script for fetching references for mapping metadata for Metax integration.

Resources are fetched from external URI and parsed for submitter use in metax_mapper class.
"""
import aiohttp
import asyncio
import json
import logging
import sys

import requests
from math import ceil
from rdflib import Graph, Namespace


log = logging.getLogger("metax")
log.setLevel(logging.DEBUG)


def get_identifier_types() -> None:
    """Parse codes for mapping identifier types."""

    id_types = {}
    codes_url = (
        "https://koodistot.suomi.fi/codelist-api/api/v1/coderegistries/fairdata/codeschemes/identifier_type/"
        "?format=json&embedCodes=true&downloadFile=true&pretty"
    )
    codes_json = requests.get(codes_url).json()["codes"]
    for code in codes_json:
        id_types[code["uri"].split("/")[-1]] = code["uri"]


def get_languages() -> None:
    """Parse languages to build mapper for submitter used language descriptions as ENUM.

    Metax uses ISO 639-3 system which are 3-letter codes with URI as identifiers.
    """

    langs = {}
    ISO_langs = {}

    # Parsing ISO 639-1, ISO 639-2 and ISO 639-3 language format
    lexvo_urls = [
        "http://www.lexvo.org/resources/lexvo-iso639-3.tsv",
        "http://www.lexvo.org/resources/lexvo-iso639-2.tsv",
        "http://www.lexvo.org/resources/lexvo-iso639-1.tsv",
    ]
    for url in lexvo_urls:
        lexvo_text = requests.get(url).text
        lexvo_list = [lang.split("\t") for lang in lexvo_text.split("\n")]
        lexvo_dict = {lang[0]: lang[1] for lang in lexvo_list[:-1]}

        # The keys are language codes of 2 and 3 chars, and values are URLs
        ISO_langs.update(lexvo_dict)

    # Parsing languages and their sub-tags
    iana_url = "https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry"
    lang_text = requests.get(iana_url).text
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
                "uri": ISO_langs[k],
            }
            n_matches += 1
        except KeyError:
            # We expect that not all languages will match.
            log.exception("No language match for %r and %r", k, v)
            no_matches += 1
            pass
    log.error("%i languages matched, and %i didn't", n_matches, no_matches)


def get_fields_of_science() -> None:
    """Parse codes and identifiers for mapping fields of science."""

    fields = {}
    fos_codes_url = "https://metax.demo.fairdata.fi/es/reference_data/field_of_science/_search?size=100"
    fos_codes_json = requests.get(fos_codes_url).json()["hits"]["hits"]
    for fos in fos_codes_json:
        fields[fos["_source"]["code"]] = {
            "uri": fos["_source"]["uri"],
            "label": fos["_source"]["label"],
        }


def get_geo_locations() -> None:
    """Parse geo_location's uri and pref_label for mapping spatial."""

    location_url = "https://api.finto.fi/rest/v1/yso-paikat/data?format=text/turtle"
    SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
    yso_namespace= "http://www.yso.fi/onto/yso"

    g = Graph()
    g.parse(location_url, format="turtle")

    locations = []

    for subject in g.subjects(predicate=SKOS.prefLabel):
        uri_str = str(subject)

        if not uri_str.startswith(yso_namespace):
            continue

        pref_labels = {}

        for object in g.objects(subject=subject, predicate=SKOS.prefLabel):
            if object.language is not None:
                lang = object.language
                pref_labels[lang] = str(object)

        if not any([loc["uri"] == uri_str for loc in locations]):
            locations.append({
                "pref_label": pref_labels,
                "uri": uri_str
            })


async def get_ror_organizations():
    """Parse ROR organizations for mapping Metax's organizations.

    There are 3 types of organizations that suit our case: education, funder, healthcare.
    """

    ror_url = "https://api.ror.org/organizations"
    filter = "types:education,types:funder,types:healthcare"
    concurrent_requests = 10
    orgs = []

    async def fetch_page(session, page):
        params = {"filter": filter, "page": page}
        async with session.get(ror_url, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("items", [])


    async with aiohttp.ClientSession() as session:
        params = {"filter": filter, "page": 1}
        async with session.get(ror_url, params=params) as resp:
            resp.raise_for_status()
            first_page_data = await resp.json()

        orgs = first_page_data.get("items")
        total_items = first_page_data.get("number_of_results", 0)
        total_pages = ceil(total_items / 20) # ROR by default returns max. 20 items per page

        remaining_pages = list(range(2, total_pages + 1))

        def page_chunks(pages, number_of_requests):
            for n in range(0, len(pages), number_of_requests):
                yield pages[n:n+number_of_requests]

        for request_pages in page_chunks(remaining_pages, concurrent_requests):
            tasks = [fetch_page(session, page) for page in request_pages]
            results = await asyncio.gather(*tasks)
            for res in results:
                orgs.extend(res)
            await asyncio.sleep(0.5)

    filtered_orgs = {}
    for org in orgs:
        org_name = next((name["value"] for name in org.get("names") if "ror_display" in name.get("types")), None)
        if org_name:
            filtered_orgs[org_name.lower()] = {
                "name": org_name,
                "id": org.get("id")
            }

    return filtered_orgs


if __name__ == "__main__":
    func_name = sys.argv[1]
    func = globals()[func_name]

    if asyncio.iscoroutinefunction(func):
        result = asyncio.run(func())
    else:
        result = func()

    # Print to console, so the script caller should output it to the correct file
    print(json.dumps(result, indent=4, sort_keys=True, ensure_ascii=False))
