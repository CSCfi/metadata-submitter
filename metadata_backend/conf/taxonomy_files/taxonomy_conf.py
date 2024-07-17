"""Define absolute paths to taxonomy files."""

from pathlib import Path

prj_root = Path(__file__).parent.parent.parent.parent.resolve()

TAXONOMY_FILES_DIR = prj_root / "metadata_backend" / "conf" / "taxonomy_files"
TAXONOMY_NAME_FILE = TAXONOMY_FILES_DIR.joinpath("names.json")

TAXONOMY_DUMP_DIR = prj_root / "scripts" / "taxonomy" / "dump_files"
TAXONOMY_NAME_DUMP = TAXONOMY_DUMP_DIR.joinpath("names.dmp")  # noqa: F841
