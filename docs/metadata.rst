Metadata Model
==============

ENA Metadata Model
------------------

The object schemas that are used for rendering the forms and validating the information submitted
to the application are based on the `ENA (European Nucleotide Archive) Metadata Model <https://ena-docs.readthedocs.io/en/latest/submit/general-guide/metadata.html>`_.

The source XML schemas are from `ENA Sequence Github repository <https://github.com/enasequence/schema/tree/master/src/main/resources/uk/ac/ebi/ena/sra/schema>`_.
The XML schemas are converted to JSON Schemas so that they can be both validate the submitted data as well as be rendered as forms in the User Interface.
For this reason the translation from XML Schema to JSON schema is not a 1-1 mapping, but an interpretation.

.. image:: /_static/metadata-model.svg
   :alt: Metadata ENA Model

The ENA model consists of the following objects:

- ``Study``: A study groups together data submitted to the archive. A study accession is typically used when citing data submitted to ENA. Note that all associated data and other objects are made public when the study is released.
- ``Project``: A project groups together data submitted to the archive. A project accession is typically used when citing data submitted to ENA. Note that all associated data and other objects are made public when the project is released.
- ``Sample``: A sample contains information about the sequenced source material. Samples are typically associated with checklists, which define the fields used to annotate the samples.
- ``Experiment``: An experiment contain information about a sequencing experiment including library and instrument details.
- ``Run``: A run is part of an experiment and refers to data files containing sequence reads.
- ``Analysis``: An analysis contains secondary analysis results derived from sequence reads (e.g. a genome assembly).
- ``DAC``: An European Genome-phenome Archive (EGA) data access committee (DAC) is required for authorized access submissions.
- ``Policy``: An European Genome-phenome Archive (EGA) data access policy is required for authorized access submissions.
- ``Dataset``: An European Genome-phenome Archive (EGA) data set is required for authorized access submissions.

Relationships between objects
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each of the objects are connected between each other by references, usually in the form of an ``accessionId``.
Some of the relationships are illustrated in the Metadata ENA Model figure, however in more detail they are connected as follows:

- ``Study`` - usually other objects point to it, as it represents one of the main objects of a ``Submission``;
- ``Analysis`` - contains references to:
    
    - parent ``Study`` (not mandatory);
    - zero or more references to objects of type: ``Sample``, ``Experiment``, ``Run``;
  
- ``Experiment`` - contains references to exactly one parent ``Study``. It can also contain a reference to ``Sample`` as an individual or a Pool;
- ``Run`` - contains reference to exactly one parent ``Experiment``;
- ``Policy`` - contains reference to exactly one parent ``DAC``;
- ``Dataset`` - contains references to:
    
    - exactly one ``Policy``;
    - zero or more references to objects of type: ``Analysis`` and ``Run``.
  

EGA/ENA Metadata submission Guides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Related guides for metadata submission:

- EGA Metadata guides:

    - `Submitting array based metadata <https://ega-archive.org/submission/array_based/metadata>`_
    - `Submitting sequence and phenotype data <https://ega-archive.org/submission/tools/submitter-portal>`_

- ENA Data Submission `general Guide  <https://ena-docs.readthedocs.io/en/latest/submit/general-guide.html>`_
