XML Validation CLI
==================

A command-line interface for validating any given XML file against a specific XSD Schema has also been implemented.
The tool can be found and installed from `this separate repository <https://github.com/CSCfi/metadata-submitter-tools>`_.

Usage
-----

After the package has been installed, the validation tool is used by by executing ``xml-validate`` in a terminal with specified options/arguments followingly:

.. code-block:: console

    $ xml-validate <option> <xml-file> <schema-file>

The ``<xml-file>`` and ``<schema-file>`` arguments need to be the correct filenames (including path) of a local XML file and the corresponding XSD file.
The ``<option>`` can be ``--help`` for showing help and ``-v`` or ``--verbose`` for delivering a detailed validation error message.

Below is a terminal demonstration of the usage of this tool, which displays the different outputs the CLI will produce:

.. raw:: html

  <script id="asciicast-FWYs48FhJ1mTFEFsWsNUbP43g" src="https://asciinema.org/a/FWYs48FhJ1mTFEFsWsNUbP43g.js" async></script>
