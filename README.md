# SD Submit API

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

SD Submit API supports sensitive data submissions.

The SD Submit UI is implemented
here: [metadata-submitter-frontend](https://github.com/CSCfi/metadata-submitter-frontend).

SD Submit API integrates with the following external services:

- PostgreSQL database
- CSC LDAP service
- Keystone (OpenStack Identity API) ([docs](https://docs.openstack.org/api-ref/identity/v3/))
- S3 ([docs](https://docs.aws.amazon.com/AmazonS3/latest/API/Type_API_Reference.html))
- DataCite ([docs](https://support.datacite.org/docs/api))
- CSC PID
- Metax ([docs](https://metax.fairdata.fi/docs/))
- ROR ([docs](https://ror.readme.io/docs/rest-api))
- REMS ([source code](https://github.com/CSCfi/rems))
- NeIC Sensitive Data Archive ([docs](https://neic-sda.readthedocs.io/en/latest/))
- Imaging Beacon ([source code](https://github.com/CSCfi/imaging-beacon))

```mermaid
flowchart LR
    subgraph SD Submit
        UI(SD Submit UI) --> API(SD Submit API)
    end
    subgraph External services
        direction LR
        API -->|All database operations| Postgres(PostgreSQL DB)
        API -->|User project listing| LDAP(LDAP Service)
        API -->|EC2 credential handling| Keystone(Keystone) --> OS(Object storage)
        API -->|Bucket/object operations| Allas(S3 API) --> OS
        API -->|DOI creation for Bigpicture| DataCiteAPI(DataCite API) --> DataCite
        API -->|DOI creation for SD| PID(PID API) --> DataCite(DataCite)
        API -->|Discovery metadata mapping| Metax(Metax API) --> Fairdata-Etsin(FairData Etsin)
        API -->|Dataset access registeration| REMS(REMS API) --> Apply(SD Apply/REMS)
        API -->|Bigpicture file ingestion| Admin(Admin API) --> SDA(NEIC SDA)
        API -->|Bigpicture metadata| Beacon(Imaging Beacon API) --> BP-Discovery(Bigpicture Discovery)
    end
```

## 💻 Development

<details><summary>Click to expand</summary>

### Prerequisites

- `Docker`
- [`Vault CLI`](https://developer.hashicorp.com/vault/docs/get-vault)

### Initialise the project for development and testing

Clone the repository and go to the project directory:

```bash
git clone
cd metadata-submitter
```

Install `uv`, `tox` and `pre-commit` tools for development:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install tox --with tox-uv
uv tool install pre-commit --with pre-commit-uv
pre-commit install
```

The project is managed by [`uv`](https://docs.astral.sh/uv/) (Python package and project manager),
which creates a virtual Python environment in `.venv` directory using the version defined in the [`.python-version`](.python-version).
`uv` installs the dependencies in `uv.lock` file that are specified in the `pyproject.toml` file.

Whenever initiating a local development environment, it is a good idea to run the following commands:
```bash
uv self update  # update uv
uv sync --dev  # sync all python dependencies
source .venv/bin/activate  # activate the uv venv
```

### Configure environment variables

Copy the contents of `.env.example` file to `.env` file and edit it as needed:

```bash
cp tests/integration/.env.example .env
```

Additionally, secrets for live services can be inserted into the `.env` file automatically with:

```bash
export VAULT_ADDR=  # Define URL address for a Vault instance
make get_env  # This will prompt a login in the web browser
```

### Run the web service and database locally

Launch both server and database with Docker by running: `docker compose up --build` (add `-d` flag to the command to run
containers in the background).

Server can then be found from `http://localhost:5430`.

> **If you also need to initiate the graphical UI for developing the API**, check
> out [metadata-submitter-frontend](https://github.com/CSCfi/metadata-submitter-frontend/) repository and follow its
> development instructions. You will then also need to set the `REDIRECT_URL` environment variable to the UI address (e.g.
> add `REDIRECT_URL=http://localhost:3000` into the `.env` file) and relaunch the development environment as specified
> above.

Alternatively, there is a more convenient method for developing the SD Submit API via a
_**Python virtual environment using a Procfile**_, which is described here below.

### Developing with Python virtual environment

Use `uv` to create and activate the virtual environment for development and testing as [instructed above](#initialise-the-project-for-development-and-testing).

Then copy `.env` file and set up the environment variables.
The example file has hostnames for development with Docker network (via `docker compose`).
You will have to change the hostnames to `localhost`.

```bash
cp tests/integration/.env.example .env  # Make any changes you need to the file
```

Secrets, which are used for testing against other services are fetched from Vault and added to the `.env` file with the
following:

```bash
export VAULT_ADDR=  # Add correct URL here
make get_env  # This will prompt a login in the web browser
```

Finally, start the servers with code reloading enabled, so any code changes restarts the servers automatically:

```bash
honcho start
```

The development server should now be accessible at `localhost:5430`.
If it doesn't work right away, check your settings in `.env` and restart the servers manually if you make changes to
`.env` file.

### OpenAPI Specification docs with Swagger

Swagger UI for viewing the API specs is already available in the production docker image. During development, you can
enable it by executing: `bash scripts/swagger/generate.sh`.

Restart the server, and the swagger docs will be available at http://localhost:5430/swagger.

**Swagger docs requirements:**

- `bash`
- `Python 3.14+`
- `PyYaml` (installed via the development dependencies)
- `realpath` (default Linux terminal command)

### Keeping Python requirements up to date

The project Python package dependencies are automatically being kept up to date
with [renovatebot](https://github.com/renovatebot/renovate).

Dependencies are added and removed to the project using the `uv` commands or by directly editing the `pyproject.toml`
file. In the latter case run `uv sync` or `uv sync --dev` to update the `uv.lock` file.

</details>

## 🛠️ Contributing

<details><summary>Click to expand</summary>

Development team members should check
internal [contributing guidelines for Gitlab](https://gitlab.ci.csc.fi/groups/sds-dev/-/wikis/Guides/Contributing).

If you are not part of CSC and our development team, your help is nevertheless very welcome. Please
see [contributing guidelines for Github](CONTRIBUTING.md).

</details>

## 🧪 Testing

<details><summary>Click to expand</summary>

For local testing, see [above instructions](#initialise-the-project-for-development-and-testing)
for installing `uv` to create a virtual environment.

Install all testing dependencies in the virtual environment by running the following commands:
```bash
uv pip install ".[verify,test,docs]"
source .venv/bin/activate  # activate uv virtual env
```

A pre-commit hook will execute all linting and unit tests before each commit.
All tests are also run in the Gitlab CI/CD pipeline for every merge request.

### Linting and Unit tests

Majority of the automated tests (such as unit tests, code style checks etc.)
can be run with [`tox`](https://tox.wiki/en/4.24.2/) automation with the following command:

```bash
tox -p auto
```

### Integration tests

Integration tests are run separately with [`pytest`](https://docs.pytest.org/en/stable/)
after the containerized testing environment has been set up.

Integration tests can be run using mock services:

```bash
docker compose --env-file tests/integration/.env.example --profile dev up --build -d
pytest tests/integration
```

Or using external services configured with secrets:

```bash
make get_env
docker compose --env-file tests/integration/.env --profile dev up --build -d
pytest tests/integration
```

</details>

## 🚀 Deployment

<details><summary>Click to expand</summary>

### Resources

Two infrequently updated resource files used by Metax are stored in
metadata_backend/resource/metax directory:
- geo_locations,json
- languages.json

These files can be refreshed by running:

```bash
uv run metadata_backend/scripts/fetch_metax.py
```

### Dockerfile

The Docker image can be built using the Dockerfile located in dockerfiles directory:

```bash
docker build --no-cache -f dockerfiles/Dockerfile -t cscfi/metadata-submitter .
```

Once built, run the container with:

```bash
docker run -p 5430:5430 cscfi/metadata-submitter
```

### Helm charts

> Helm charts for a kubernetes cluster deployment will also be available soon™️.

</details>

## 📜 License

<details><summary>Click to expand</summary>

Metadata submission interface is released under `MIT`, see [LICENSE](LICENSE).

</details>
