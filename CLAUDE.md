# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all checks in parallel (ruff, mypy, vulture, pytest, docs)
tox -p auto

# Individual checks
tox -e ruff     # format and lint
tox -e mypy     # type check
tox -e vulture  # dead code detection (min-confidence 100)
tox -e pytest   # unit tests with coverage

# Run a single test
.venv/bin/pytest tests/unit/path/to/test_file.py::test_name -x

# Sync dependencies and activate virtualenv
uv sync --dev
source .venv/bin/activate

# Run the API server (dev, via Procfile with hot reload)
honcho start

# Or via Docker (server + database together)
docker compose --profile dev up --build

# Database migrations
make db_upgrade         # apply all pending Alembic migrations
make db_stamp revision=head  # stamp existing schema without running migrations

# Fetch Vault secrets into .env
export VAULT_ADDR=https://...
make get_env
```

Server listens on `localhost:5430` (CSC) or `localhost:5431` (NBIS).

## Architecture

### Dual-deployment design

The app has two deployment modes controlled by the `DEPLOYMENT` env var: `CSC` (default) and `NBIS`. `server.py:create_app()` conditionally wires different services, routes, and behaviours depending on the deployment. Key differences:

- **CSC**: OIDC login/logout routes, Keystone (OpenStack), Metax, PID, S3/Allas file provider, API key management, submission CRUD.
- **NBIS**: DataCite DOIs, SDA Admin API, S3-Inbox file provider, background ingest scanner task (`SDAIngestService`), no OIDC login routes.

### Layered structure inside `metadata_backend/`

```
conf/         # Pydantic-settings config classes, one per external service
services/     # HTTP client wrappers for external services (ServiceHandler base class)
api/
  handlers/   # FastAPI route handlers (thin: validate, delegate, return)
  services/   # Business logic called by handlers
  models/     # Pydantic request/response models
  processors/ # XML parsing/generation (FEGA, Bigpicture, DataCite)
  middlewares.py  # ASGI: SessionMiddleware (DB txn) + AuthMiddleware (JWT/cookie)
database/
  postgres/
    models.py         # SQLAlchemy ORM models
    repositories/     # DB access (one file per domain entity)
    services/         # DB-level business logic wrapping repositories
    repository.py     # Engine/session factory, context variable for sessions
    alembic/          # Migration scripts
```

### Request lifecycle

1. `AuthMiddleware` validates JWT bearer token or session cookie on every `/v1/...` request.
2. `SessionMiddleware` opens a SQLAlchemy async transaction and stores it in a `ContextVar`; commits or rolls back after the response.
3. FastAPI dispatches to a handler in `api/handlers/`. Handlers call `api/services/` for business logic and `services/` for external service calls.
4. Repositories retrieve the session from the `ContextVar` directly — they never manage transactions themselves.

### XML processing

Submissions are sent as multipart form data containing XML. `api/processors/processors.py` dispatches to format-specific processors under `api/processors/xml/` (FEGA, Bigpicture, DataCite). Processors parse/validate XML and return typed models used downstream.

### Configuration

All config classes live in `conf/` and inherit from Pydantic `BaseSettings` (env vars loaded lazily via factory functions, not at import time). `conf/deployment.py` is the top-level switch; individual service configs (e.g., `conf/datacite.py`, `conf/metax.py`) are loaded only when those service handlers are instantiated.
