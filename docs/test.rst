Testing
=======


Frontend Testing
----------------

Run Vitest-based tests with ``pnpm test``. Check code formatting and style errors with ``pnpm run lint:check`` and fix them with ``pnpm run lint``.
Respectively for formatting errors in ``json/yaml/css/md`` -files, use ``pnpm run format:check`` or ``pnpm run format``.
Possible type errors can be checked with ``pnpm run tsc``.

We're following recommended settings from ``eslint``, ``react`` and ``prettier`` - packages with a couple of exceptions,
which can be found in ``.eslintrc`` and ``.prettierrc``.
Linting, formatting and testing are also configured for you as a git pre-commit, which is recommended to use to avoid fails on CI pipeline.


End to End testing
~~~~~~~~~~~~~~~~~~~

End-to-end tests can be run on local host with ``pnpm cypress run`` or ``pnpm cypress open`` in frontend repository.
These tests required a running backend, follow the instructions in :ref:`deploy` for development setup of backend.

If the frontend is started with ``pnpm start`` no changes required in the setup.
