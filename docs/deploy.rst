.. _`deploy`:

Build and Deployment
====================

Development Deployment
----------------------

For integration testing and local development we recommend ``docker-compose``,
which can be installed using ``pip install docker-compose``.


Deploying Frontend
~~~~~~~~~~~~~~~~~~

Check out `frontend repository <https://github.com/CSCfi/metadata-submitter-frontend>`_.

For quick testing run ``docker compose up --build`` (add ``-d`` flag to run container in the background).
By default, frontend tries to connect to docker container running the backend. Feel free to modify ``docker-compose.yml`` if you want to use some other setup.


Integrating Frontend and Backend
********************************

With backend running as container and frontend with ``pnpm``:

1. check out metadata submitter backend repository
2. un-commented line 24 from ``docker-compose.yml``
3. ``docker compose up -d --build`` backend repository root directory
4. check out metadata submitter frontend repository
5. ``pnpm start``  frontend repository root directory


With backend and frontend running in containers:

1. check out metadata submitter backend repository
2. un-commented line 24 from ``docker-compose.yml`` and modify to ``http://frontend:3000``
3. ``docker compose up -d --build`` backend repository root directory
4. check out metadata submitter frontend repository
5. ``docker compose up -d --build`` frontend repository root directory


Kubernetes Deployment
~~~~~~~~~~~~~~~~~~~~~

For deploying the application as part of Kubernetes us the helm charts from: https://github.com/CSCfi/metadata-submitter-helm/
