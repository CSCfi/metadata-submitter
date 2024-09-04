"""Class to create taxonomy name file from a database dump file."""

import json
from pathlib import Path
from typing import Any, Iterator


class Taxonomy:
    """Create taxonomy with ids and names from a database dump file."""

    def __init__(self, input_file: Path, output_file: Path) -> None:
        """Define input (dump) and output (json) files."""
        self.input_file = input_file
        self.output_file = output_file

    def _parse_file(self, file_path: Path) -> Iterator[list[str]]:
        """Dump file line iterator.

        param file_path: path to dump file
        returns: yields of listed column items
        """
        with file_path.open("r") as file:
            for row in file:
                row_items = row.split("|")
                row_items.pop()
                yield [item.strip() for item in row_items]

    def create_name_taxonomy(self) -> Path:
        """Create a Taxonomy from the NCBI taxonomy database dump file.

        names.dmp (https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/)

        From taxdump_readme.txt:
        ---------
        Taxonomy names file has these fields:

            tax_id					-- the id of node associated with this name
            name_txt				-- name itself
            unique name				-- the unique variant of this name if name not unique
            name class	            -- (synonym, common name, ...)

        returns: created taxonomy file path
        """
        # Create taxonomy file
        data: dict[str, Any] = {}

        # Use genbank common name as the common name if it the latter does not exist
        genbank = "genbank common name"
        name_classes = ["scientific name", "common name"]

        for line in self._parse_file(self.input_file):
            tax_id, name, _, name_class = line
            # add scientific and common name
            if name_class in name_classes:
                name_class = name_class.replace(" ", "_")
                if tax_id in data:
                    data[tax_id][name_class] = name
                else:
                    data[tax_id] = {name_class: name}

            # add genbank common name. Will be overwritten with common name if available
            elif name_class == genbank:
                common = name_classes[1].replace(" ", "_")
                if tax_id in data:
                    if common not in data[tax_id]:
                        data[tax_id][common] = name
                else:
                    data[tax_id] = {common: name}
        created_file = self._create_file(data)
        return created_file

    def _create_file(self, data: dict[str, Any]) -> Path:
        """Write given data to a file.

        param data: data to write
        returns: file path of created file or None
        """
        try:
            file = self.output_file.open("w")
            file.write(json.dumps(data))
            file.close()
            return self.output_file
        except Exception:
            return None
