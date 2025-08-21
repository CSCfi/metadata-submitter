# SD Submit API

![Python Unit Tests](https://github.com/CSCfi/metadata-submitter/workflows/Python%20Unit%20Tests/badge.svg)
![Integration Tests](https://github.com/CSCfi/metadata-submitter/workflows/Integration%20Tests/badge.svg)
![Documentation Checks](https://github.com/CSCfi/metadata-submitter/workflows/Documentation%20Checks/badge.svg)
![Python style check](https://github.com/CSCfi/metadata-submitter/workflows/Python%20style%20check/badge.svg)
[![Coverage Status](https://coveralls.io/repos/github/CSCfi/metadata-submitter/badge.svg?branch=main)](https://coveralls.io/github/CSCfi/metadata-submitter?branch=main)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![linting: pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/PyCQA/pylint)

SD Submit API to support submissions of sensitive data. A submission consists of a
generic submission JSON document, associated data files, and workflow specific metadata
objects. The submissions are stored in a PostgreSQL relational database. The file processing
is done using NeIC SRA ingest pipelines. The submission is registered to workflow specific
services including DataCite, Metax, and REMS.

SD Submit UI frontend is implemented here: [metadata-submitter-frontend](https://github.com/CSCfi/metadata-submitter-frontend).

SD Submit API uses the following external services via their respective API:
- SD Connect ([source code](https://github.com/CSCfi/swift-browser-ui))
- Imaging Beacon ([source code](https://github.com/CSCfi/imaging-beacon))
- NeIC Sensitive Data Archive ([docs](https://neic-sda.readthedocs.io/en/latest/))
- REMS ([source code](https://github.com/CSCfi/rems))
- Metax ([docs](https://metax.fairdata.fi/docs/))
- DataCite ([docs](https://support.datacite.org/))
- CSC PID

```mermaid
flowchart LR
    SD-Connect(SD Connect) -->|Information about files| SD-Submit[SD Submit API]
    SD-Submit -->|Bigpicture metadata| Bigpicture-Discovery(Imaging Beacon)
    SD-Submit <-->|Ingestion pipeline actions| NEIC-SDA(NEIC SDA)
    REMS -->|Workflows/Licenses/Organizations| SD-Submit -->|Resources/Catalogue items| REMS(REMS)
    SD-Submit -->|EGA/SDSX metadata| Metax(Metax API)
    Metax --> Fairdata-Etsin(FairData Etsin)
    SD-Submit <-->|DOI for Bigpicture| DataCite(DataCite)
    SD-Submit <-->|DOI for EGA/SDSX| PID(PID) <--> DataCite
```

## 💻 Development

<details><summary>Click to expand</summary>

### Prerequisites

- `Docker`
- `Aspell` for spell checking:
  - Mac: `brew install aspell`
  - Ubuntu/Debian: `sudo apt-get install aspell`
- [`Vault CLI`](https://developer.hashicorp.com/vault/docs/get-vault)
- [`Git LFS`](https://git-lfs.com/)

Git LFS is required to checkout the `metadata_backend/conf/taxonomy_files/names.json` file.
This file can be generated from NCBI taxonomy using the following command:

```bash
scripts/taxonomy/generate_name_taxonomy.sh
```

### Initialise the project for development and testing

Clone the repository and go to the project directory:

```bash
git clone
cd metadata-submitter
```

The project is managed by `uv` that creates a virtual environment in `.venv` directory
using the python version defined in the `.python-version`. The  `uv` also installs the
depencies defined in `uv.lock` file. The `uv.lock` file captures the exact versions of
all direct and transitive dependencies specified in the `pyproject.toml` file. Tox
depencies are managed in the `test` optional dependency group.  Dependencies are added and
removed using the `uv add` and `uv remove` commands or by directly editing
the `pyproject.toml` file. In the latter case run `uv sync` or `uv sync --dev` to update
the `uv.lock` file.

Create and activate the virtual environment, install the dependencies and the tox and
pre-commit tools:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install tox --with tox-uv
uv tool install pre-commit --with pre-commit-uv
uv sync --dev
pre-commit install
```

### Configure environmental variables

Copy the contents of `.env.example` file to `.env` file and edit it as needed:

```bash
cp .env.example .env
```

Additionally, secrets for live services can be inserted into the `.env` file automatically with:

```bash
export VAULT_ADDR=  # Define URL address for a Vault instance
make get_env  # This will prompt a login in the web browser
```

### Run the web service and database locally

Launch both server and database with Docker by running: `docker compose up --build` (add `-d` flag to the command to run containers in the background).

Server can then be found from `http://localhost:5430`.

> **If you also need to initiate the graphical UI for developing the API**, check out [metadata-submitter-frontend](https://github.com/CSCfi/metadata-submitter-frontend/) repository and follow its development instructions. You will then also need to set the `REDIRECT_URL` environment variable to the UI address (e.g. add `REDIRECT_URL=http://localhost:3000` into the `.env` file) and relaunch the development environment as specified above.

Alternatively, there is a more convenient method for developing the SD Submit API via a _**Python virtual environment using a Procfile**_, which is described here below.

### Developing with Python virtual environment

Please use `uv` to create the virtual environment for development and testing as instructed above. Then follows these instructions:

```bash
# Optional: update references for metax integration
scripts/metax_mappings/fetch_refs.sh

# Optional: update taxonomy names for taxonomy search endpoint
# However, this is a NECESSARY step if you have not installed Git LFS
scripts/taxonomy/generate_name_taxonomy.sh
```

Then copy `.env` file and set up the environment variables.
The example file has hostnames for development with Docker network (via `docker compose`).
You will have to change the hostnames to `localhost`.

```bash
cp .env.example .env  # Make any changes you need to the file
```

Secrets, which are used for testing against other services are fetched from Vault and added to the `.env` file with the following:

```bash
export VAULT_ADDR=  # Add correct URL here
make get_env  # This will prompt a login in the web browser
```

Finally, start the servers with code reloading enabled, so any code changes restarts the servers automatically:

```bash
uv run honcho start
```

The development server should now be accessible at `localhost:5430`.
If it doesn't work right away, check your settings in `.env` and restart the servers manually if you make changes to `.env` file.

### OpenAPI Specification docs with Swagger

Swagger UI for viewing the API specs is already available in the production docker image. During development, you can enable it by executing: `bash scripts/swagger/generate.sh`.

Restart the server, and the swagger docs will be available at http://localhost:5430/swagger.

**Swagger docs requirements:**
- `bash`
- `Python 3.13+`
- `PyYaml` (installed via the development dependencies)
- `realpath` (default Linux terminal command)

### Keeping Python requirements up to date

The project Python package dependencies are automatically being kept up to date with [renovatebot](https://github.com/renovatebot/renovate).

Dependencies are added and removed to the project using the `uv` commands or by directly editing the `pyproject.toml` file. In the latter case run `uv sync` or `uv sync --dev` to update the `uv.lock` file.

</details>

## 🛠️ Contributing

<details><summary>Click to expand</summary>

Development team members should check internal [contributing guidelines for Gitlab](https://gitlab.ci.csc.fi/groups/sds-dev/-/wikis/Guides/Contributing).

If you are not part of CSC and our development team, your help is nevertheless very welcome. Please see [contributing guidelines for Github](CONTRIBUTING.md).

</details>

## 🧪 Testing

<details><summary>Click to expand</summary>

Majority of the automated tests (such as unit tests, code style checks etc.) can be run with [`tox`](https://tox.wiki/en/4.24.2/) automation. Integration tests are run separately with [`pytest`](https://docs.pytest.org/en/stable/) as they require the full test environment to be running with a local database instance and all the mocked versions of related external services.

Please use `uv` to create the virtual environment for development and testing as instructed above. Then follows the minimal instructions below for executing the automated tests of this project locally. Run the below commands in the project root:

```bash
# Unit tests, linting, etc.
tox -p auto

# Integration tests
docker compose --env-file .env.example up --build -d
pytest tests/integration
```

Additionally, we use pre-commit hooks in the CI/CD pipeline for automated tests in every merge/pull request. The pre-commit hooks include some extra tests such as spellchecking so installing pre-commit hooks locally (with `pre-commit install`) is also useful.

</details>

## 🚀 Deployment

<details><summary>Click to expand</summary>

Production version can be built and run with following docker commands:
```bash
docker build --no-cache -f dockerfiles/Dockerfile -t cscfi/metadata-submitter .
docker run -p 5430:5430 cscfi/metadata-submitter
```

The [frontend](https://github.com/CSCfi/metadata-submitter-frontend) is built and added as static files to the backend deployment with this method.

> Helm charts for a kubernetes cluster deployment will also be available soon™️.

</details>

## 📜 License

<details><summary>Click to expand</summary>

Metadata submission interface is released under `MIT`, see [LICENSE](LICENSE).

</details>
