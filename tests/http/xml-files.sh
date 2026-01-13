#!/bin/bash
BOUNDARY="WebKitFormBoundary"
OUTPUT="tests/http/xml-files.txt"
FILES=(
    "annotation"
    "datacite"
    "dataset"
    "image"
    "landing_page"
    "observation"
    "observer"
    "organisation"
    "policy"
    "rems"
    "sample"
    "staining"
)

{
    for file in "${FILES[@]}"; do
        echo "--$BOUNDARY"
        echo "Content-Disposition: form-data; name=\"$file\"; filename=\"$file.xml\""
        echo "Content-Type: text/xml"
        echo
        cat "tests/test_files/xml/bigpicture/$file.xml"
        echo
    done
    echo "--$BOUNDARY--"
} | sed 's/$/\r/' > "$OUTPUT"

# Same dataset but with updated image metadata
OUTPUT="tests/http/xml-files-update.txt"
FILES=(
    "annotation"
    "datacite"
    "dataset"
    "landing_page"
    "observation"
    "observer"
    "organisation"
    "policy"
    "rems"
    "sample"
    "staining"
)

{
    for file in "${FILES[@]}"; do
        echo "--$BOUNDARY"
        echo "Content-Disposition: form-data; name=\"$file\"; filename=\"$file.xml\""
        echo "Content-Type: text/xml"
        echo
        cat "tests/test_files/xml/bigpicture/$file.xml"
        echo
    done
    echo "--$BOUNDARY"
    echo "Content-Disposition: form-data; name=\"image\"; filename=\"image.xml\""
    echo "Content-Type: text/xml"
    echo
    cat "tests/test_files/xml/bigpicture/update/image.xml"
    echo
    echo "--$BOUNDARY--"
} | sed 's/$/\r/' > "$OUTPUT"
