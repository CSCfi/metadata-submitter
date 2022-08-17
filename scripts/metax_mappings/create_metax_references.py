#!/usr/bin/env python3
"""Script for fetching references for mapping metadata for Metax integration."""
import json
import logging

import requests

log = logging.getLogger("metax")
log.setLevel(logging.DEBUG)

# Create helper dictionaries for mapping metadata to Metax model
# Resources are fetched from external URI and parsed for submitter use in metax_mapper class

# parsing codes for mapping identifier types
metax_ref = {"identifier_types": {}, "languages": {}, "fields_of_science": {}}
codes_url = (
    "https://koodistot.suomi.fi/codelist-api/api/v1/coderegistries/fairdata/codeschemes/identifier_type/"
    "?format=json&embedCodes=true&downloadFile=true&pretty"
)
codes_json = requests.get(codes_url).json()["codes"]
for code in codes_json:
    metax_ref["identifier_types"][code["uri"].split("/")[-1]] = code["uri"]


# parsing ISO 639-1, ISO 639-2 and ISO 639-3 format languages to build mapper
# for submitter used language descriptions as ENUM.
# Metax uses ISO 639-3 system which are 3-letter codes with URI as identifiers.

ISO_langs = {}

# parsing ISO 639-1, ISO 639-2 and ISO 639-3 language format
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


# parsing languages and their sub-tags
iana_url = "https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry"
lang_text = requests.get(iana_url).text
lang_list = [lang.split("\n") for lang in lang_text.split("\n%%\n")]

# Filter languages by "type: language" to reduce noise
# We get keys that are language names (description field), and values are language codes

lang_dict = {
    lang[2].split(": ")[1]: lang[1].split(": ")[1] for lang in lang_list[1:] if lang[0].split(": ")[1] in {"language"}
}

n_matches = 0
no_matches = 0
for k, v in lang_dict.items():
    v = v.lower()
    try:
        metax_ref["languages"][k] = ISO_langs[v]
        n_matches += 1
    except KeyError:
        # We expect that not all languages will match.
        log.error(f"No language match for '{k}' and '{v}'")
        no_matches += 1
        pass
log.error(f"{n_matches} languages matched, and {no_matches} didn't")


# parsing codes and identifiers for mapping fields of science
fos_codes_url = "https://metax.demo.fairdata.fi/es/reference_data/field_of_science/_search?size=100"
fos_codes_json = requests.get(fos_codes_url).json()["hits"]["hits"]
for fos in fos_codes_json:
    metax_ref["fields_of_science"][fos["_source"]["code"]] = {
        "uri": fos["_source"]["uri"],
        "label": fos["_source"]["label"],
    }

# print to console, so the script caller should output it to the correct file
print(json.dumps(metax_ref))
