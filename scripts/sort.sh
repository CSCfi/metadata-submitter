#!/usr/bin/env bash

file="docs/dictionary/wordlist.txt"

# Sorts dictionary, converts to lower case, and remove duplicates
sort "${file}" | tr "[:upper:]" "[:lower:]" | sort -u -o "${file}"
