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

1. `AuthMiddleware` validates JWT bearer token or session cookie on every `/v1/...` request. Paths outside `/v1` — `/health`, the OIDC login routes, `/openapi.json`, `/sync/...` — are passed through and authorize themselves, or not at all.
2. `SessionMiddleware` opens a SQLAlchemy async transaction and stores it in a `ContextVar`; commits or rolls back after the response.
3. FastAPI dispatches to a handler in `api/handlers/`. Handlers call `api/services/` for business logic and `services/` for external service calls.
4. Repositories retrieve the session from the `ContextVar` directly — they never manage transactions themselves.

### Sync endpoints

For clients mirroring published metadata. `/sync` lists the submissions published within a
period, most recently published last; `/sync/{submissionId}` serves one submission's metadata
objects as a zip. Documented in `docs/BP_sync.md`.

Mounted **outside `/v1`**, so `AuthMiddleware` ignores them and `dependencies.py:verify_sync`
verifies a **signed** bearer token instead. The dependency is on the **router**, so a route
added later cannot be left open, and nothing is mounted without `SYNC_CLIENTS`.

A syncing service signs a token per request with its private key and we hold only the public
key, so nothing configured here can issue a token this service would accept — which a shared
secret cannot say. `SYNC_CLIENTS` is a JSON array of `{iss, public_keys}`, and a key is verified
against *that* service's issuer alone, so `iss` names whoever signed rather than being a
self-asserted label. Nothing acts on `iss` yet beyond a debug log. `jti` is sent but neither
required nor remembered: a token lives a minute.

Three details carry the security:

- **`algorithms=["ES256"]` is an allowlist**, never the token's own `alg`. A verifier honouring
  the header would accept `HS256` signed with the public key it publishes.
- **`aud` is required**, so a token signed for another service, or one recorded in a log, does
  not authenticate here.
- **Every key of every service is tried**, since the token carries no `kid`. That is what lets a
  key be replaced with no moment when only one side has switched.

`conf/sync.py` requires `SYNC_AUDIENCE` and **parses** every key rather than only decoding it,
so one that cannot verify ES256 — not P-256, or a private key pasted by mistake — fails at
startup rather than rejecting every request.

The publication date is the only cursor: a published submission is immutable
(`check_submission_modifiable`), so `published` is stamped once and the client tracks it.
Nothing is paginated; a client narrows the period instead.

Packaging is per deployment through `SyncMetadataProvider` (`api/services/sync.py`), implemented
only by `BigpictureSyncMetadataProvider` and wired in `create_app` for NBIS. A deployment
without a provider does not serve the archive route at all.

Tested in `tests/unit/api/test_dependencies.py` (`verify_sync` against a synthetic `Request`)
and `tests/unit/api/handlers/test_sync.py` (that the dependency is on the router), both signing
through `tests/sync.py`.

### XML processing

Submissions are sent as multipart form data containing XML. `api/processors/processors.py` dispatches to format-specific processors under `api/processors/xml/` (FEGA, Bigpicture, DataCite). Processors parse/validate XML and return typed models used downstream.

### Configuration

All config classes live in `conf/` and inherit from Pydantic `BaseSettings` (env vars loaded lazily via factory functions, not at import time). `conf/deployment.py` is the top-level switch; individual service configs (e.g., `conf/datacite.py`, `conf/metax.py`) are loaded only when those service handlers are instantiated.
