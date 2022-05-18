#!/usr/bin/env bash

SCRIPT="$(realpath $0)"
SCRIPT_ROOT=$(dirname "$SCRIPT")
SCRIPTS=$(dirname "$SCRIPT_ROOT")
ROOT=$(dirname "$SCRIPTS")

SWAGGER_ROOT="${ROOT}"/metadata_backend/swagger

mkdir -p "${SWAGGER_ROOT}"
python3 "${SCRIPT_ROOT}"/yaml-to-html.py < "${ROOT}"/docs/specification.yml > "${SWAGGER_ROOT}"/index.html
