Metadata Submitter
==================

Install and run
---------------

.. note:: Requirements:

  - Python 3.6+
  - Mongodb
  - Docker + docker-compose

For quick testing, launch both server and database with Docker by running ``docker-compose up --build`` (add ``-d`` flag to run containers in background). Server can then be found from ``http://localhost:5430``.

For more detailed setup, do following:

- Install project by running: ``pip install .`` in project root
- Setup mongodb and env variables via desired way, details:

  - Server expects to find mongodb instance running, spesified with following environmental variables:

    - ``MONGO_INITDB_ROOT_USERNAME`` (username for admin user to mondogb instance)
    - ``MONGO_INITDB_ROOT_PASSWORD`` (password for admin user to mondogb instance)
    - ``MONGODB_HOST`` (host and port for mongodb instancem, e.g. `localhost:27017`)

  - Out of the box, metadata submitter is configured with default values from MongoDB Docker image
  - Suitable mongodb instance can be launched with Docker by running: ``docker-compose up database``

- After installing and setting up database, server can be launched with: ``metadata_submitter``

If you also need frontend for development, check out `frontend repository <https://github.com/CSCfi/metadata-submitter-frontend/>`_.

Tests
-----

Tests can be run with tox automation: just run ``tox`` on project root (remember to install it first with ``pip install tox``).

Build and deploy
----------------

Production version can be built and run with following docker commands:

.. code-block:: console

    docker build --no-cache . -t metadata-submitter
    docker run -p 5430:5430 metadata-submitter

Frontend is built and added as static files to backend while building.
