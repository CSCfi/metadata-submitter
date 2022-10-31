#!/usr/bin/env bash

file="docs/dictionary/wordlist.txt"

# Sorts dictionary, converts to lower case, and remove duplicates
sort "${file}" | tr "[:upper:]" "[:lower:]" | sort -u -o "${file}"

# Remove unused words
# Uses `ripgrep` to look for each word in the repository, and removes them with `sed` when no match is found
if ! command -v rg > /dev/null 2>&1; then
    echo "ripgrep not installed, skipping removing unused words"
    exit 0
fi

while read -r line; do
  if ! output="$(rg --hidden -g '!docs/dictionary' -i "${line}" .)" ; then
    echo $line
    sed -i "/${line}/d" "$file"
  fi
done <"${file}"
