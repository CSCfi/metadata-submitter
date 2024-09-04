#!/usr/bin/env bash

SCRIPT="$(realpath $0)"
SCRIPT_ROOT=$(dirname "$SCRIPT")

DUMP_ROOT="${SCRIPT_ROOT}"/dump_files

TAR=new_taxdump.tar.gz
NAMES_DUMP=names.dmp

# get and extract names.dmp
mkdir -p "${DUMP_ROOT}"
cd "${DUMP_ROOT}"
curl -o $TAR https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/new_taxdump.tar.gz
tar -xf $TAR $NAMES_DUMP

# create json file
cd "${SCRIPT_ROOT}"
python3 create_names_json.py

# explicitly remove temp files
rm "${DUMP_ROOT}/${TAR}"
rm "${DUMP_ROOT}/${NAMES_DUMP}"
rmdir "${DUMP_ROOT}"
