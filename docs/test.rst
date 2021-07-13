Testing
=======

.. note:: Unit tests and integration tests are automatically executed with every PR to
          for both frontend and backend in their respective repositories.

Backend Testing
---------------

Tests can be run with tox automation: just run ``tox`` on project root (remember to install it first with ``pip install tox``).

Unit Testing
~~~~~~~~~~~~

In order to run the unit tests, security checks with `bandit <https://github.com/PyCQA/bandit>`_,
Sphinx documentation check for links consistency and HTML output
and `flake8 <http://flake8.pycqa.org/en/latest/>`_ (coding style guide)
`tox <http://tox.readthedocs.io/>`_. To run the unit tests in parallel use:

.. code-block:: console

    $ tox -p auto

To run environments seprately use:

.. code-block:: console

    $ # list environments
    $ tox -l
    $ # run flake8
    $ tox -e flake8
    $ # run bandit
    $ tox -e bandit
    $ # run docs
    $ tox -e docs


Integration Testing
~~~~~~~~~~~~~~~~~~~

Integration tests required a running backend, follow the instructions in :ref:`deploy` for development setup of backend.
After the backend has been successfully set up, run the following in the backend repository root directory: ``python tests/integration/run_tests.py``.
This command will run a series of integration tests.

Performance Testing
~~~~~~~~~~~~~~~~~~~

Performance tests utilize Locust load testing framework (install it first with ``pip install locust``).
Performance tests also require a running backend, similar to integration tests. After the backend has been set up,
running the following commands in the repository root directory will run different performance related tests in headless mode (all test data printed to terminal).

.. code-block:: console

    $ # run tests that post objects/folders
    $ locust --tags post
    $ # run tests that query for objects/folders
    $ locust --tags query

The configuration values for running performance tests are predefined in the ``locust.conf`` file in the repository root directory.
All configuration options (`as defined here <https://docs.locust.io/en/stable/configuration.html#all-available-configuration-options>`_)
can be overriden and new options can be added by either editing the current ``locust.conf`` file or running the test with additional tags, e.g.:

.. code-block:: console

    $ # this will run the post test for 30 seconds
    $ locust --tags post --run-time 30s


Frontend Testing
----------------

Run Jest-based tests with ``npm test``. Check code formatting and style errors with ``npm run lint:check`` and fix them with ``npm run lint``.
Respectively for formatting errors in ``json/yaml/css/md`` -files, use ``npm run format:check`` or ``npm run format``.
Possible type errors can be checked with ``npm run flow``.

We're following recommended settings from ``eslint``, ``react`` and ``prettier`` - packages witha a couple of exceptions,
which can be found in ``.eslintrc`` and ``.prettierrc``.
Linting, formatting and testing are also configured for you as a git pre-commit, which is recommended to use to avoid fails on CI pipeline.


End to End testing
~~~~~~~~~~~~~~~~~~~

End-to-end tests can be run on local host with ``npx cypress open`` in frontend repository.
These tests required a running backend, follow the instructions in :ref:`deploy` for development setup of backend.

If the frontend is started with ``npm start`` no changes required in the setup.
