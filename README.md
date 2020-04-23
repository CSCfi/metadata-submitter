## Metadata submission backend

Minimum viable product that:
- Accepts HTTP POST submissions of EGA metadata XML files 
- Validates XML files against EGA XSD metadata models 
- Saves XML files to database

## Install and Run

Clone project and install it by running: `pip install .`

Server expects to find mongodb instance running at localhost in port 27017. Instance can be started with `docker-compose up -d` after setting up following environmental variables to .env file:

```
MONGO_INITDB_ROOT_USERNAME=metadata_backend_admin
MONGO_INITDB_ROOT_PASSWORD=metadata_backend_admin_pass
MONGO_PORT=27017
```
Paste lines above to .env file on projects root foleder or use env_example file.

After installing and setting up database, server can be launched with `metadata_backend`.


## Tests

Tests, flake8 style checks and bandit security checks can be run with tox automation: just run `tox` on project root (remember to install it first with `pip install tox`.
