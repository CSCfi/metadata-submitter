"""Create taxonomy name file from a database dump file."""

import os
import sys

tax_dir = os.path.dirname(__file__)
prj_dir = os.path.join(tax_dir, "..", "..")
sys.path.append(prj_dir)

import metadata_backend.conf.taxonomy_files.taxonomy_conf as conf  # noqa: E402
import scripts.taxonomy.taxonomy as taxonomy  # noqa: E402

tax = taxonomy.Taxonomy(conf.TAXONOMY_NAME_DUMP, conf.TAXONOMY_NAME_FILE)
created_file = tax.create_name_taxonomy()

if created_file is None:
    raise RuntimeError("Failed to create taxonomy name file from taxonomy dump file.")
