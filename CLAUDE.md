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

  # Sync dependencies and activate virtualenv. uv downloads from Artifactory (pyproject.toml), which
# needs the UV_* credentials in .env; uv does not read .env itself, and without them it fails with a 401.
set -a; eval "$(grep '^UV_' .env)"; set +a
uv sync --dev
source .venv/bin/activate

# Integration tests exactly as CI runs them: inside the runner container, with its environment
docker compose -f docker-compose.yml --env-file tests/integration/.env --profile ci run --build integration-test-runner

# Re-encrypt every stored metadata object with the configured OPENBAO_* key and method
python -m metadata_backend.scripts.reencrypt_objects

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

Server listens on `localhost:5430` (CSC) or `localhost:5431` (NBIS) by default; `SERVER_PORT` overrides the port.

## Architecture

### Dual-deployment design

The app has two deployment modes controlled by the `DEPLOYMENT` env var: `CSC` (default) and `NBIS`. Each has a profile in `deployment.py` (`CscDeploymentProfile`, `NbisDeploymentProfile`, looked up with `deployment_profile()`) that holds its default server port, the flags for the endpoints it serves, and the factory for its services and service handlers. `server.py:create_app()` wires the app from the profile rather than checking the deployment. Key differences:

- **CSC**: OIDC login/logout routes, Keystone (OpenStack), Metax, PID, S3/Allas file provider, API key management, submission CRUD.
- **NBIS**: DataCite DOIs, SDA Admin API, S3-Inbox file provider, background ingest scanner task (`SDAIngestService`), no OIDC login routes.

Each submission workflow (SD, FEGA, Bigpicture) likewise has a profile in `api/services/workflow.py`, looked up with `workflow_profile()`, which holds its workflow-specific submission, publishing and metadata object behaviour. A deployment's workflow is `Deployment.workflow` (`conf/deployment.py`), kept off the profile so that `dependencies.py` need not import every service. A deployment accepts only submissions of its own workflow (`dependencies.py:get_workflow`).

When working on CSC-side infrastructure (Allas/S3, Rahti, Pouta, Slurm), the `csc-docs` MCP server (configured in `.mcp.json`) can search `docs.csc.fi` for relevant reference material.

### Layered structure inside `metadata_backend/`

```
deployment.py # Deployment profiles: per-deployment workflow, port, endpoints and services
conf/         # Pydantic-settings config classes, one per external service
services/     # HTTP client wrappers for external services (ServiceHandler base class)
api/
  handlers/   # FastAPI route handlers (thin: validate, delegate, return)
  services/   # Business logic called by handlers
  models/     # Pydantic request/response models
  processors/ # XML parsing/generation (FEGA, Bigpicture, DataCite)
  middlewares.py  # ASGI: AuditMiddleware (audit log) + SessionMiddleware (DB txn) + AuthMiddleware (JWT/cookie)
database/
  postgres/
    models.py         # SQLAlchemy ORM models
    repositories/     # DB access (one file per domain entity)
    services/         # DB-level business logic wrapping repositories
    repository.py     # Engine/session factory, context variable for sessions
    alembic/          # Migration scripts
```

### Request lifecycle

1. `AuditMiddleware` writes one audit record per `/v1/...` request (see *Audit log*). It is the outermost middleware, so that it records the status the client received.
2. `SessionMiddleware` opens a SQLAlchemy async transaction for `/v1/...` and `/sync/...` requests and stores it in a `ContextVar`; commits or rolls back when the response starts. It wraps `AuthMiddleware` (`middlewares.py:add_middlewares`), so that the session exists when an API key is validated. If the commit fails, the transaction is rolled back, the route's response is dropped and the client receives a 500 error response instead. Sending that response does not commit or roll back the transaction again.
3. `AuthMiddleware` validates a JWT bearer token, session cookie or API key on every `/v1/...` request. Paths outside `/v1` — `/health`, the OIDC login routes, `/openapi.json`, `/sync/...` — are passed through and authorize themselves, or not at all.
4. FastAPI dispatches to a handler in `api/handlers/`. Handlers call `api/services/` for business logic and `services/` for external service calls.
5. Repositories retrieve the session from the `ContextVar` directly — they never manage transactions themselves. The one exception is `committed_session()` (`database/postgres/repository.py`), described under *Publishing*.

### Logging

`LOG_FORMAT` (`TEXT` by default, or `JSON`) sets the format of every log. Every log except the audit
log is written by the root logger's handler: uvicorn is started with `log_config=None`, so it
configures no logging of its own. The root logger is at WARNING, so libraries, uvicorn included,
inherit its level and log only problems, even at `LOG_LEVEL=DEBUG`. Uvicorn's request (access) log
and startup lines are INFO, so they are not written: every `/v1` request is in the audit log instead,
and no client IP address is logged. `LOG_LEVEL` sets the level of the `server` logger only. To debug a
library, set its own logger's level. `LOG_FORMAT` and `LOG_LEVEL` are read by
`conf/log.py:LogConfig` when `helpers/logger.py` is imported, unlike the other configs, since logging
is set up before anything logs. Both are matched case-insensitively, and `LOG_LEVEL` also accepts
`WARN` and `FATAL`, as the logging module does. An invalid value fails at startup. In JSON every line
is one python-json-logger object. Both formats write the time in UTC, as ISO 8601 with milliseconds
and `Z` (`2026-10-26T17:42:31.123Z`). The text format escapes control characters in a message (C0,
C1, and U+2028 and U+2029), such as a newline from a decoded `%0A` in a path, and indents the lines
of a traceback or stack, so that request data cannot start a forged log line; JSON escapes them
anyway.

### Audit log

The `audit` logger (`helpers/logger.py`) records who did what. Its level is fixed and it does not
propagate, so it is written whatever `LOG_LEVEL` is. A record has a machine-readable `action`, a readable
`message` and the user's `user_id` (`User.user_id`). In the JSON log format it is one
python-json-logger line; in the text format its fields follow as `key=value`, with the values and the
message quoted as JSON and the message last, so that request data in it, such as a path, cannot add
fields ahead of the real ones. In both formats an audit record is identified by its level, shown as
`AUDIT` although the record's own level is INFO, and it has no logger, process, function or line. Every
text line, audit or not, starts with the time and level; every JSON line has `levelname` and `time`. `AuditMiddleware` writes an `http.request` record
for every `/v1` request, including those that fail authentication (`user_id` is null); its `status` is null if
the app sent no response, for example if it raised before the response started. Other actions are
recorded with `audit_event(action, message, **details)`, which takes the user from the
current request: `AuditMiddleware` sets the `audit_state` context variable to an `AuditState` for each
request, and `AuthMiddleware` sets its `user_id` once the user is authenticated. Details are snake_case. They
are passed to logging as one `details` field, so that no name clashes with a log record attribute, and
the audit formatters write them at the top level of the line. A detail named after a field of the audit
line (`levelname`, `message`, `time`, `action`, `user_id`) is written with `_` appended, so that it does
not replace the field. Never log tokens, API keys, the authentication method, client IP addresses,
query strings or request bodies.

### Sync endpoints

For clients mirroring published metadata. `/sync` lists the submissions published within a
period, most recently published last; `/sync/{submissionId}` serves one submission's metadata
objects as a zip, with `FILES/files.json` listing its file accessions. A listed submission
carries `ingested` once SDA has released its dataset, since publication comes first. Documented
in `docs/BP_sync.md`.

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

### Publishing

A publish registers the submission in external services (DOI, Metax, REMS) before the request
transaction commits, so a failure after any one registration would roll back an identifier that
already exists outside. `RegistrationService` therefore writes each step inside
`committed_session()`, a separate transaction on its own connection that commits when the block
exits. A failed publish keeps what it registered, and a retry resumes from the stored registration
rather than registering again.

A retry also brings the registrations up to date with the submission, which may have changed
since the failure: Metax's title and description, the DataCite metadata (sent again without the
`publish` event once the DOI is findable, `make_findable`), and the REMS catalogue item's title.
An imported dataset's catalogue item may predate this service and is left unchanged.

`publish_submission` checks access, then locks the submission row with `FOR NO KEY UPDATE NOWAIT`,
then checks again that it is unpublished. A concurrent publish fails at once with 409 rather than
waiting. The lock must stay `NO KEY`: the committed transactions insert registrations that
reference the submission, which needs `KEY SHARE`, and `FOR UPDATE` would block them.

`committed_session()`:

- holds a second connection while the request still holds its own, so the request transaction
  must never lock a row that a committed step needs. Postgres cannot detect that deadlock, so
  `SET LOCAL lock_timeout` turns it into an error after 10 seconds.
- raises without the session factory that `SessionMiddleware` sets in `session_factory_context`.
  The unit-test `session` fixture sets `allow_no_committed_session`, so the block runs in the test
  transaction instead. Tests of the real behaviour use a temporary SQLite database
  (`tests/unit/database/postgres/test_repository.py`, and `_transactional_client` in
  `tests/unit/api/handlers/test_publish.py`). The lock is tested against Postgres in
  `tests/integration/test_submission_lock.py`.

### Encryption

Stored metadata objects are encrypted with OpenBao (`api/services/openbao.py`) when `OPENBAO_URL`
is set. OpenBao authenticates with exactly one of `OPENBAO_TOKEN` and `OPENBAO_KUBERNETES_ROLE`.
Files uploaded to the NBIS inbox are Crypt4GH-encrypted (`api/services/crypt.py`).

GitLab rejects any pushed file ending in `.key` or `.pem`, so test keys are named `*_private.txt`.

### XML processing

Submissions are sent as multipart form data containing XML. `api/processors/processors.py` dispatches to format-specific processors under `api/processors/xml/` (FEGA, Bigpicture, DataCite). Processors parse/validate XML and return typed models used downstream.

### Configuration

All config classes live in `conf/` and inherit from Pydantic `BaseSettings` (env vars loaded lazily via factory functions, not at import time). `conf/deployment.py` is the top-level switch; individual service configs (e.g., `conf/datacite.py`, `conf/metax.py`) are loaded only when those service handlers are instantiated.

A config built with constructor arguments still reads the environment for every other field. On the host,
pytest's environment holds no service settings: `tests/integration/.env` is read only by `docker compose`,
and `tests/integration/conf.py` falls back to defaults. In CI, the `integration-test-runner` service's
`environment:` list sets real variables, for example `OPENBAO_TOKEN`. So a test choosing one of two
exclusive settings must `monkeypatch.delenv` the other, or it passes locally and fails in CI.
