.. _`backend`:

Metadata Submitter Backend
==========================

.. note:: Requirements:

  - Python 3.7+
  - MongoDB
  

Environment Setup
-----------------

The application requires some environmental arguments in order to run properly, these are illustrated in
the table below.

+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ENV                            | Default                       | Description                                                                       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_HOST``                 | ``localhost:27017``           | Mongodb server hostname, with port specified if needed.                           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_AUTHDB``               | ``-``                         | Mongodb authentication database.                                                  |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_INITDB_ROOT_USERNAME`` | ``admin``                     | Admin username for mongodb.                                                       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``MONGO_INITDB_ROOT_PASSWORD`` | ``admin``                     | Admin password for mongodb.                                                       |
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
| ``AUTH_REFERER``               | ``-``                         | OIDC AUTH endpoint that redirects the request to the application.                 |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``BASE_URL``                   | ``http://localhost:5430``     | base URL of the metadata submitter.                                               |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``ISS_URL``                    | ``-``                         | OIDC claim issuer URL.                                                            |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``AUTH_URL``                   | ``-``                         | Set if a special OID authorize URL is required.                                   |
|                                |                               | otherwise use ``"OIDC_URL"/authorize``.                                           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``OIDC_URL``                   | ``-``                         | OIDC base URL for constructing OIDC protocol endpoint calls.                      |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``REDIRECT_URL``               | ``-``                         | Enable this for working with front-end on ``localhost`` or change to              |
|                                |                               | ``http://frontend:3000`` if started using ``docker-compose`` (see :ref:`deploy`). |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``JWL_URL``                    | ``-``                         | JWK OIDC URL for retrieving key for validating ID token.                          |
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

Install and run
---------------

For installing ``metadata-submitter`` backend do the following:

.. code-block:: console

    $ git clone https://github.com/CSCfi/metadata-submitter
    $ pip install .

.. hint:: Before running the application have MongoDB running.

    MongoDB Server expects to find mongodb instance running, spesified with following environmental variables:

    - ``MONGO_INITDB_ROOT_USERNAME`` (username for admin user to mondogdb instance)
    - ``MONGO_INITDB_ROOT_PASSWORD`` (password for admin user to mondogdb instance)
    - ``MONGO_HOST`` (host and port for mongodb instancem, e.g. `localhost:27017`)

To run the backend from command line use:

.. code-block:: console

    $ metadata_submitter

.. hint:: For a setup that requires also frontend follow the instructions in :ref:`deploy`.


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