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

+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ENV                            | Default                       | Description                                                                       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_HOST``                 | ``localhost:27017``           | MongoDB server hostname, with port specified if needed.                           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_AUTHDB``               | ``-``                         | MongoDB authentication database.                                                  |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_DATABASE``             | ``default``                   | MongoDB default database, will be used as authentication database if              |
|                                |                               | ``MONGO_AUTHDB`` is not set.                                                      |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_USERNAME``             | ``admin``                     | Admin username for MongoDB.                                                       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_PASSWORD``             | ``admin``                     | Admin password for MongoDB.                                                       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_SSL``                  | ``-``                         | Set to True to enable MONGO TLS connection url.                                   |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_SSL_CA``               | ``-``                         | Path to CA file, required if ``MONGO_SSL`` enabled.                               |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_SSL_CLIENT_KEY``       | ``-``                         | Path to contains client's TLS/SSL X.509 key,required if ``MONGO_SSL`` enabled.    |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_SSL_CLIENT_CERT``      | ``-``                         | Path to contains client's TLS/SSL X.509 cert,required if ``MONGO_SSL`` enabled.   |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AAI_CLIENT_SECRET``          | ``public```                   | OIDC client secret.                                                               |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AAI_CLIENT_ID``              | ``secret``                    | OIDC client ID.                                                                   |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AUTH_REFERER``               | ``-``                         | OIDC Provider url that redirects the request to the application.                  |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``BASE_URL``                   | ``http://localhost:5430``     | base URL of the metadata submitter.                                               |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``ISS_URL``                    | ``-``                         | OIDC claim issuer URL.                                                            |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AUTH_URL``                   | ``-``                         | Set if a special OIDC authorize URL is required.                                  |
|                                |                               | otherwise use ``"OIDC_URL"/authorize``.                                           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``OIDC_URL``                   | ``-``                         | OIDC base URL for constructing OIDC provider endpoint calls.                      |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``REDIRECT_URL``               | ``-``                         | Required only for testing with front-end on ``localhost`` or change to            |
|                                |                               | ``http://frontend:3000`` if started using ``docker-compose`` (see :ref:`deploy`). |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``JWK_URL``                    | ``-``                         | JWK OIDC URL for retrieving key for validating ID token.                          |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``LOG_LEVEL``                  | ``INFO``                      | Set logging level, uppercase.                                                     |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``SERVE_KEY``                  | ``-``                         | Keyfile used for TLS.                                                             |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``SERVE_CERT``                 | ``-``                         | Certificate used for TLS.                                                         |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``SERVE_CA``                   | ``-``                         | CA file used for TLS.                                                             |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``SERVE_SLLVERSION``           | ``-``                         | Version used for TLS, see `the gunicorn documentation for ssl_version             |
|                                |                               | <https://docs.gunicorn.org/en/stable/settings.html#ssl-version>`_                 |
|                                |                               | for more information.                                                             |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``SERVE_CIPHERS``              | ``-``                         | Ciphers used for TLS, see `the gunicorn documentation for ciphers                 |
|                                |                               | <https://docs.gunicorn.org/en/stable/settings.html#ciphers>`_                     |
|                                |                               | for more information.                                                             |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``SERVE_CERTREQS``             | ``-``                         | Client certificate requirement used for TLS, see `the gunicorn documentation for  |
|                                |                               | cert_reqs <https://docs.gunicorn.org/en/stable/settings.html#cert-reqs>`_         |
|                                |                               | for more information.                                                             |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+


.. note:: If just ``MONGO_DATABASE`` is specified it will autenticate the user against it.
          If just ``MONGO_AUTHDB`` is specified it will autenticate the user against it.
          If both ``MONGO_DATABASE`` and ``MONGO_AUTHDB`` are specified, the client will attempt to authenticate the specified user to the MONGO_AUTHDB database.
          If both ``MONGO_DATABASE`` and ``MONGO_AUTHDB`` are unspecified, the client will attempt to authenticate the specified user to the admin database.

Install and run
---------------

For installing ``metadata-submitter`` backend do the following:

.. code-block:: console

    $ git clone https://github.com/CSCfi/metadata-submitter
    $ pip install .

.. hint:: Before running the application have MongoDB running.

    MongoDB Server expects to find MongoDB instance running, spesified with following environmental variables:

    - ``MONGO_INITDB_ROOT_USERNAME`` (username for admin user to mondogdb instance)
    - ``MONGO_INITDB_ROOT_PASSWORD`` (password for admin user to mondogdb instance)
    - ``MONGO_HOST`` (host and port for MongoDB instance, e.g. `localhost:27017`)

To run the backend from command line use:

.. code-block:: console

    $ metadata_submitter

.. hint:: For a setup that requires also frontend follow the instructions in :ref:`deploy`.

Authentication
--------------

The Authentication follows the `OIDC Specification <https://openid.net/specs/openid-connect-core-1_0.html>`_.

We follow the steps of the OpenID Connect protocol.

- The RP (Client) sends a request to the OpenID Provider (OP),
  for this we require ``AAI_CLIENT_SECRET``, ``AAI_CLIENT_ID``, ``OIDC_URL``, a callback url constructed from ``BASE_URL`` and
  ``AUTH_URL`` if required.
- The OP authenticates the End-User and obtains authorization.
- The OP responds with an ID Token and usually an Access Token,
  we validate the ID Token for which we need ``JWK_URL`` to get the key and ``ISS_URL`` to check the claims issuer is correct.
- The RP can send a request with the Access Token to the UserInfo Endpoint.
- The UserInfo Endpoint returns Claims about the End-User, use use some claims ``sub`` and ``eppn`` to identify the user and start a session.

Information related to the OpenID Provider (OP) that needs to be configured is displayed in the table below.
Most of the information can be retrieved from `OIDC Provider <https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderMetadata>`_ metadata
endpoint ``https://<provider_url>/.well-known/openid-configuration``.

+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ENV                            | Default                       | Description                                                                       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AAI_CLIENT_SECRET``          | ``public```                   | OIDC client secret.                                                               |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AAI_CLIENT_ID``              | ``secret``                    | OIDC client ID.                                                                   |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AUTH_REFERER``               | ``-``                         | OIDC Provider url that redirects the request to the application.                  |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``BASE_URL``                   | ``http://localhost:5430``     | base URL of the metadata submitter.                                               |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``ISS_URL``                    | ``-``                         | OIDC claim issuer URL.                                                            |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AUTH_URL``                   | ``-``                         | Set if a special OIDC authorize URL is required.                                  |
|                                |                               | otherwise use ``"OIDC_URL"/authorize``.                                           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``OIDC_URL``                   | ``-``                         | OIDC base URL for constructing OIDC provider endpoint calls.                      |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``REDIRECT_URL``               | ``-``                         | Required only for testing with front-end on ``localhost`` or change to            |
|                                |                               | ``http://frontend:3000`` if started using ``docker-compose`` (see :ref:`deploy`). |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``JWK_URL``                    | ``-``                         | JWK OIDC URL for retrieving key for validating ID token.                          |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+


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
