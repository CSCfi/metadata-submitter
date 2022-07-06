#!/usr/bin/env bash

SCRIPT="$(realpath $0)"
SCRIPT_ROOT=$(dirname "$SCRIPT")
SCRIPTS=$(dirname "$SCRIPT_ROOT")
ROOT=$(dirname "$SCRIPTS")

MAPPING_FILES_ROOT="${ROOT}"/metadata_backend/conf/metax_references

mkdir -p "${MAPPING_FILES_ROOT}"
python3 "${SCRIPT_ROOT}"/create_metax_references.py > "${MAPPING_FILES_ROOT}"/metax_references.json
