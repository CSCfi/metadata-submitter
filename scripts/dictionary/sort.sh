#!/usr/bin/env bash

file="docs/dictionary/wordlist.txt"

# Sorts dictionary, converts to lower case, and remove duplicates
export LC_ALL=C
sort "${file}" | tr "[:upper:]" "[:lower:]" | sort -u -o "${file}"
