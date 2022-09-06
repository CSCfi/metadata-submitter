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
`tox <https://tox.wiki/en/latest/>`_. To run the unit tests in parallel use:

.. code-block:: console

    $ tox -p auto

To run environments separately use:

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

Integration tests are executed with ``pytest``, and require a running backend.
Follow the instructions in :ref:`deploy` for development setup of backend. Install

- aiofiles
- aiohttp
- motor
- pytest
- pytest-asyncio

After the backend has been successfully set up, run the following in the backend repository root directory: ``pytest tests/integration``.
This command will run a series of integration tests.

**Pytest fixtures**

Be sure to familiarize yourself with `pytest fixtures <https://docs.pytest.org/en/6.2.x/fixture.html>`_ and their scope.
They are pure magic.

Fixtures are defined in ``tests/integration/conftest.py``.

Basically, a fixture is run before a new module/class/function/<fixture scope here>
is executed, according to its defined ``scope``. Statements before a ``yield`` statement function as a ``Setup``, and
statements after are ``Teardown``. When there's no ``yield``, there's no teardown either, only setup.

Debugging tests
~~~~~~~~~~~~~~~

Depending on your setup, there are different ways to debug tests run with `pytest <https://docs.pytest.org/en/6.2.x/usage.html>`_.
Without covering the possibilities that IDEs offer, here are the possibilities with the CLI and
`the Python debugger (PDB) <https://docs.python.org/3/library/pdb.html#debugger-commands>`_.

- Run a single test with ``pytest tests/integration/test_module.py::TestClass::test_method``.
  Or remove the method name to run a single class test.

- Follow `pytest docs <https://docs.pytest.org/en/6.2.x/usage.html#dropping-to-pdb-python-debugger-on-failures>`_,
  and run tests with ``pytest -x --pdb tests/integration`` to drop to the PDB on
  the first error.


- Similarly, you can use ``ipdb`` to use the more feature-full pdb, using IPython.

::

    $ pip install ipdb
    $ pytest -x --pdb -pdbcls=IPython.terminal.debugger:TerminalPdb tests/integration

- Together with ``--pdb``, call ``breakpoint()`` in the code to pause the test execution at a predefined point.


Performance Testing
~~~~~~~~~~~~~~~~~~~

Performance tests utilize Locust load testing framework (install it first with ``pip install locust``).
Performance tests also require a running backend, similar to integration tests. After the backend has been set up,
running the following commands in the repository root directory will run different performance related tests in headless mode (all test data printed to terminal).

.. code-block:: console

    $ # run tests that post objects/submissions
    $ locust --tags post
    $ # run tests that query for objects/submissions
    $ locust --tags query

The configuration values for running performance tests are predefined in the ``locust.conf`` file in the repository root directory.
All configuration options (`as defined here <https://docs.locust.io/en/stable/configuration.html#all-available-configuration-options>`_)
can be overridden and new options can be added by either editing the current ``locust.conf`` file or running the test with additional tags, e.g.:

.. code-block:: console

    $ # this will run the post test for 30 seconds
    $ locust --tags post --run-time 30s


Frontend Testing
----------------

Run Jest-based tests with ``npm test``. Check code formatting and style errors with ``npm run lint:check`` and fix them with ``npm run lint``.
Respectively for formatting errors in ``json/yaml/css/md`` -files, use ``npm run format:check`` or ``npm run format``.
Possible type errors can be checked with ``npm run flow``.

We're following recommended settings from ``eslint``, ``react`` and ``prettier`` - packages with a couple of exceptions,
which can be found in ``.eslintrc`` and ``.prettierrc``.
Linting, formatting and testing are also configured for you as a git pre-commit, which is recommended to use to avoid fails on CI pipeline.


End to End testing
~~~~~~~~~~~~~~~~~~~

End-to-end tests can be run on local host with ``npx cypress open`` in frontend repository.
These tests required a running backend, follow the instructions in :ref:`deploy` for development setup of backend.

If the frontend is started with ``npm start`` no changes required in the setup.
