.. _`deploy`:

Build and Deployment
====================

Development Deployment
----------------------

For integration testing and local development we recommend ``docker-compose``,
which can be installed using ``pip install docker-compose``.

Deploying Backend
~~~~~~~~~~~~~~~~~

Check out `backend repository <https://github.com/CSCfi/metadata-submitter>`_.

For quick testing, launch both server and database with Docker by running ``docker-compose up --build``
(add ``-d`` flag to run containers in background). Server can then be found from ``http://localhost:5430``.

This will launch a version without the frontend.

Deploying Frontend
~~~~~~~~~~~~~~~~~~

Check out `frontend repository <https://github.com/CSCfi/metadata-submitter-frontend>`_.

For quick testing run ``docker-compose up --build`` (add ``-d`` flag to run container in the background).
By default, frontend tries to connect to docker container running the backend. Feel free to modify ``docker-compose.yml`` if you want to use some other setup.


Integrating Frontend and Backend
********************************

With backend running as container and frontend with ``npm``:

1. check out metadata submitter backend repository
2. un-commented line 24 from ``docker-compose.yml``
3. ``docker-compose up -d --build`` backend repository root directory
4. check out metadata submitter frontend repository
5. ``npm start``  frontend repository root directory


With backend and frontend running in containers:

1. check out metadata submitter backend repository
2. un-commented line 24 from ``docker-compose.yml`` and modify to ``http://frontend:3000``
3. ``docker-compose up -d --build`` backend repository root directory
4. check out metadata submitter frontend repository
5. ``docker-compose up -d --build`` frontend repository root directory


Production Deployment
---------------------

To ease production deployment Frontend is built and added as static files to backend while building the Docker image.
The production image can be built and run with following docker commands:

.. code-block:: console

    docker build --no-cache . -t cscfi/metadata-submitter
    docker run -p 5430:5430 cscfi/metadata-submitter

.. important:: Requires running MongoDB and consider setting the environment variables as pointed out in :ref:`backend`.

Kubernetes Deployment
~~~~~~~~~~~~~~~~~~~~~

For deploying the application as part of Kubernetes us the helm charts from: https://github.com/CSCfi/metadata-submitter-helm/
