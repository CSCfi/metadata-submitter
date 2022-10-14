.. Metadata Submitter documentation master file, created by
   sphinx-quickstart on Tue Jun 16 22:48:21 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Metadata Submitter
==================

Metadata Submission service to handle submissions of metadata, either as JSON, XML files or via form submissions via the
Single Page Application frontend.

Metadata Submitter is divided intro :ref:`backend` and :ref:`frontend`, both of them coming together in a Single Page Application
that aims to streamline  working with metadata and providing a submission process through which researchers can submit and publish metadata.

The application's intended use is with `NeIC SDA (Sensitive Data Archive) <https://neic-sda.readthedocs.io/>`_ stand-alone version, and it
consists out of the box includes the `ENA (European Nucleotide Archive) <https://ena-docs.readthedocs.io>`_ metadata model,
model which is used also by the  `European Genome-phenome Archive (EGA) <https://ega-archive.org/>`_.

.. image:: /_static/metadata-app.svg
   :alt: Metadata Submitter Architecture and Metadata Overview

Out of the box the ``metadata-submitter`` offers:

* flexible REST API for working with metadata;
* validating metadata objects against ENA XSD metadata models and their respective JSON schema;
* asynchronous web server;
* OIDC authentication;
* dynamic forms based on JSON schemas and workflows;
* simple wizard for submitting metadata.

A command-line interface for validating any given XML file against a specific XSD Schema has also been implemented
see :ref:`validate`.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   Backend <submitter>
   Frontend <frontend>
   Metadata <metadata>
   Deployment <deploy>
   Testing  <test>
   Validator CLI Tool <validator>


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
