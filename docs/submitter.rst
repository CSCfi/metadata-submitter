.. _`backend`:

Metadata Submitter Backend
==========================

.. note:: Requirements:

  - Python 3.12+
  - Postgres


Environment Setup
-----------------

The application requires some environmental arguments in order to run properly, these are illustrated in
the table below.

+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ENV                            | Default                       | Description                                                                       | Mandatory |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+-----------+
| ``PG_DATABASE_URL``            |                               | Connection URL for the PostgreSQL database.                                       | Yes       |
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

Install and run
---------------

For installing ``metadata-submitter`` backend do the following:

.. code-block:: console

    $ git clone https://github.com/CSCfi/metadata-submitter
    $ pip install .

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

View `metadata submitter API <https://editor.swagger.io/?url=https://raw.githubusercontent.com/CSCfi/metadata-submitter/main/docs/openapi.yml>`_
in swagger editor.

The REST API is structured as follows:

- `Submission Endpoints` used in submitting data, mostly ``POST`` endpoints;
- `Query Endpoints` used for data retrieval (``submissions``, ``objects``, ``users``) uses HTTP ``GET``;
- `Management Endpoints` used for handling data updates and deletion, makes use of HTTP ``PUT``, ``PATCH`` and ``DELETE``.

The REST API is protected and can be accessed in two ways:

- Performing a successful login at frontend, which creates a session
- Using a ``Bearer`` token, which is issued by ``OIDC_URL``

.. important:: A logged in user can only perform operations on the data it has associated.
               The information for the current user can be retrieved at ``/v1/users/current`` (the user ID is ``current``), and
               any additional operations on other users are rejected.
