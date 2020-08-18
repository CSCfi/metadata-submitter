------------------------
Metadata Backend Modules
------------------------

.. automodule:: metadata_backend
   :synopsis: The metadata_backend package contains code for Beacon API.

.. autosummary::

    metadata_backend.api
    metadata_backend.conf
    metadata_backend.database
    metadata_backend.helpers
    metadata_backend.server


********************
Metadata Backend API
********************

.. automodule:: metadata_backend.api

.. autosummary::
   :toctree: metadata_backend.api

    metadata_backend.api.handlers
    metadata_backend.api.middlewares
    metadata_backend.api.operators

*******************
Database Operations
*******************

.. automodule:: metadata_backend.database

.. autosummary::
   :toctree: metadata_backend.database

    metadata_backend.database.db_service

*****************
Utility Functions
*****************

.. automodule:: metadata_backend.helpers

.. autosummary::
   :toctree: metadata_backend.helpers

    metadata_backend.helpers.logger
    metadata_backend.helpers.parser
    metadata_backend.helpers.schema_loader
    metadata_backend.helpers.validator

*************
Configuration
*************

.. automodule:: metadata_backend.conf
    

.. autosummary::
   :toctree: metadata_backend.conf
   

   metadata_backend.conf.conf

******
Server
******

.. automodule:: metadata_backend.server
    :members:


:ref:`genindex` | :ref:`modindex`
