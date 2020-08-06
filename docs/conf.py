"""Configuration file for the Sphinx documentation builder."""

import datetime
from typing import Callable

# -- Project information -----------------------------------------------------

current_year = str(datetime.date.today().year)
project = "Metadata Submitter"
copyright = f"{current_year}, CSC Developers"
author = "CSC Developers"

# The full version, including alpha/beta/rc tags
release = "0.2.0"


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.coverage",
    "sphinx.ext.ifconfig",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",
    "sphinx.ext.todo",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

master_doc = "index"

autosummary_generate = True


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "collapse_navigation": True,
    "sticky_navigation": True,
    "display_version": True,
    "prev_next_buttons_location": "bottom",
}


# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]


def setup(app: Callable) -> None:
    """Add custom stylesheet."""
    app.add_css_file("custom.css")


htmlhelp_basename = "metadata-submitter"
man_pages = [(master_doc, "metadata-submitter", [author], 1)]
texinfo_documents = [(master_doc, "metadata-submitter", author, "Miscellaneous")]
