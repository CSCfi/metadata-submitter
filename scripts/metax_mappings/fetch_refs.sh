#!/usr/bin/env bash

SCRIPT="$(realpath $0)"
SCRIPT_ROOT=$(dirname "$SCRIPT")
SCRIPTS=$(dirname "$SCRIPT_ROOT")
ROOT=$(dirname "$SCRIPTS")

MAPPING_FILES_ROOT="${ROOT}"/metadata_backend/conf/metax_references

mkdir -p "${MAPPING_FILES_ROOT}"
python3 "${SCRIPT_ROOT}"/create_metax_references.py get_languages> "${MAPPING_FILES_ROOT}"/languages.json
python3 "${SCRIPT_ROOT}"/create_metax_references.py get_fields_of_science> "${MAPPING_FILES_ROOT}"/fields_of_science.json
python3 "${SCRIPT_ROOT}"/create_metax_references.py get_geo_locations> "${MAPPING_FILES_ROOT}"/geo_locations.json
python3 "${SCRIPT_ROOT}"/create_metax_references.py get_ror_organizations> "${MAPPING_FILES_ROOT}"/ror_organizations.json
