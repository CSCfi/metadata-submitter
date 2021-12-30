.. _`backend`:

Metadata Submitter Backend
==========================

.. note:: Requirements:

  - Python 3.8+
  - MongoDB
  

Environment Setup
-----------------

The application requires some environmental arguments in order to run properly, these are illustrated in
the table below.

+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ENV                            | Default                       | Description                                                                       | Mandatory |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_HOST``                 | ``localhost:27017``           | MongoDB server hostname, with port specified if needed.                           | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_AUTHDB``               | ``-``                         | MongoDB authentication database.                                                  | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_DATABASE``             | ``default``                   | MongoDB default database, will be used as authentication database if              | No        |
|                                |                               | ``MONGO_AUTHDB`` is not set.                                                      |           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_USERNAME``             | ``admin``                     | Admin username for MongoDB.                                                       | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_PASSWORD``             | ``admin``                     | Admin password for MongoDB.                                                       | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_SSL``                  | ``-``                         | Set to True to enable MongoDB TLS connection url.                                 | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_SSL_CA``               | ``-``                         | Path to CA file, required if ``MONGO_SSL`` enabled.                               | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_SSL_CLIENT_KEY``       | ``-``                         | Path to contains client's TLS/SSL X.509 key,required if ``MONGO_SSL`` enabled.    | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``MONGO_SSL_CLIENT_CERT``      | ``-``                         | Path to contains client's TLS/SSL X.509 cert,required if ``MONGO_SSL`` enabled.   | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``AAI_CLIENT_SECRET``          | ``public```                   | OIDC client secret.                                                               | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``AAI_CLIENT_ID``              | ``secret``                    | OIDC client ID.                                                                   | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``BASE_URL``                   | ``http://localhost:5430``     | base URL of the metadata submitter.                                               | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``AUTH_METHOD``                | ``code``                      | OIDC Authentication method to use.                                                | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``OIDC_URL``                   | ``-``                         | OIDC URL base URL, MUST resolve to configuration endpoint when appended with      | Yes       |
|                                |                               | /.well-known/openid-configuration                                                 |           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``OIDC_SCOPE``                 | ``openid profile email``      | Claims to request from AAI                                                        | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``REDIRECT_URL``               | ``-``                         | Required only for testing with front-end on ``localhost`` or change to            | No        |
|                                |                               | ``http://frontend:3000`` if started using ``docker-compose`` (see :ref:`deploy`). |           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``LOG_LEVEL``                  | ``INFO``                      | Set logging level, uppercase.                                                     | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``SERVE_KEY``                  | ``-``                         | Keyfile used for TLS.                                                             | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``SERVE_CERT``                 | ``-``                         | Certificate used for TLS.                                                         | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``SERVE_CA``                   | ``-``                         | CA file used for TLS.                                                             | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``SERVE_SLLVERSION``           | ``-``                         | Version used for TLS, see `the gunicorn documentation for ssl_version             |           |
|                                |                               | <https://docs.gunicorn.org/en/stable/settings.html#ssl-version>`_                 | No        |
|                                |                               | for more information.                                                             |           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``SERVE_CIPHERS``              | ``-``                         | Ciphers used for TLS, see `the gunicorn documentation for ciphers                 |           |
|                                |                               | <https://docs.gunicorn.org/en/stable/settings.html#ciphers>`_                     | No        |
|                                |                               | for more information.                                                             |           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``SERVE_CERTREQS``             | ``-``                         | Client certificate requirement used for TLS, see `the gunicorn documentation for  |           |
|                                |                               | cert_reqs <https://docs.gunicorn.org/en/stable/settings.html#cert-reqs>`_         | No        |
|                                |                               | for more information.                                                             |           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+


.. note:: If just ``MONGO_DATABASE`` is specified it will authenticate the user against it.
          If just ``MONGO_AUTHDB`` is specified it will authenticate the user against it.
          If both ``MONGO_DATABASE`` and ``MONGO_AUTHDB`` are specified, the client will attempt to authenticate the specified user to the MONGO_AUTHDB database.
          If both ``MONGO_DATABASE`` and ``MONGO_AUTHDB`` are unspecified, the client will attempt to authenticate the specified user to the admin database.

Install and run
---------------

For installing ``metadata-submitter`` backend do the following:

.. code-block:: console

    $ git clone https://github.com/CSCfi/metadata-submitter
    $ pip install .

.. hint:: Before running the application have MongoDB running.

    MongoDB Server expects to find MongoDB instance running, specified with following environmental variables:

    - ``MONGO_INITDB_ROOT_USERNAME`` (username for admin user to mongodb instance)
    - ``MONGO_INITDB_ROOT_PASSWORD`` (password for admin user to mongodb instance)
    - ``MONGO_HOST`` (host and port for MongoDB instance, e.g. `localhost:27017`)

To run the backend from command line set the environment variables required and use:

.. code-block:: console

    $ metadata_submitter

.. hint:: For a setup that requires also frontend follow the instructions in :ref:`deploy`.

Authentication
--------------

The Authentication follows the `OIDC Specification <https://openid.net/specs/openid-connect-core-1_0.html>`_.

We follow the steps of the OpenID Connect protocol.

- The RP (Client) sends a request to the OpenID Provider (OP),
  for this we require ``AAI_CLIENT_SECRET``, ``AAI_CLIENT_ID``, ``OIDC_URL`` and a callback url constructed from ``BASE_URL``.
- The OP authenticates the End-User and obtains authorization.
- The OP responds with an ID Token and usually an Access Token, which are validated with configuration provided by ``OIDC_URL``.
- The RP can send a request with the Access Token to the UserInfo Endpoint.
- The UserInfo Endpoint returns Claims about the End-User, use claims ``sub``, ``CSCUserName`` or ``remoteUserIdentifier`` to identify the user and start a session.

Information related to the OpenID Provider (OP) that needs to be configured is displayed in the table below.
Most of the information can be retrieved from `OIDC Provider <https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderMetadata>`_ metadata
endpoint ``https://<provider_url>/.well-known/openid-configuration``.

+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ENV                            | Default                       | Description                                                                       | Mandatory |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``AAI_CLIENT_SECRET``          | ``public```                   | OIDC client secret.                                                               | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``AAI_CLIENT_ID``              | ``secret``                    | OIDC client ID.                                                                   | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``BASE_URL``                   | ``http://localhost:5430``     | base URL of the metadata submitter.                                               | Yes       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``AUTH_METHOD``                | ``code``                      | OIDC Authentication method to use.                                                | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``OIDC_URL``                   | ``-``                         | OIDC URL base URL, MUST resolve to configuration endpoint when appended with      | Yes       |
|                                |                               | /.well-known/openid-configuration                                                 |           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``OIDC_SCOPE``                 | ``openid profile email``      | Claims to request from AAI                                                        | No        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+

REST API
--------

View `metadata submitter API <https://editor.swagger.io/?url=https://raw.githubusercontent.com/CSCfi/metadata-submitter/master/docs/specification.yml>`_
in swagger editor.

The REST API is structured as follows:

- `Submission Endpoints` used in submitting data, mostly ``POST`` endpoints;
- `Query Endpoints` used for data retrieval (``folders``, ``objects``, ``users``) uses HTTP ``GET``;
- `Management Endpoints` used for handling data updates and deletion, makes use of HTTP ``PUT``, ``PATCH`` and ``DELETE``.

.. important:: A logged in user can only perform operations on the data it has associated.
               The information for the current user can be retrieved at ``/users/current`` (the user ID is ``current``), and
               any additional operations on other users are rejected.


.. include:: code.rst
