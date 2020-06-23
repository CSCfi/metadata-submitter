## Metadata submission service for SDA

[![Build Status](https://travis-ci.org/CSCfi/metadata-submitter.svg?branch=master)](https://travis-ci.org/CSCfi/metadata-submitter)
[![Coverage Status](https://coveralls.io/repos/github/CSCfi/metadata-submitter/badge.svg?branch=master)](https://coveralls.io/github/CSCfi/metadata-submitter?branch=master)

Metadata submission service to handle submissions of EGA metadata, either as XML files or via form submissions. Submissions through graphical frontend and POST are supported.
Service also validates submissions against EGA XSD metadata models and saves submissions to database.

## Install and run

Requirements:
- Python 3.6+
- Mongodb
- Docker + docker-compose

For quick testing, server and database can be started with Docker by running `docker-compose up  --build` (add `-d` flag to run containers in background). Server can then be found from `http://localhost:5430`.

For more detailed setup, do following:
- Install project by running: `pip install .`
- Setup mongodb
  - Server expects to find mongodb instance running, spesified with following environmental variables:
    - `MONGO_INITDB_ROOT_USERNAME`, username for admin user to mondogb instance
    - `MONGO_INITDB_ROOT_PASSWORD`, password for admin user to mondogb instance
    - `MONGODB_HOST`, host and port for mongodb instance (e.g. `localhost:27017`)
  - Server looks for current environmental variables first and if needed variables aren't found, it uses MongoDB Docker images default values.
  - Suitable mongodb instance can be launched with Docker by running `docker-compose up` in `mongodb` folder
- After installing and setting up database, server can be launched with `metadata_submitter`.

If you also need frontend for development, check out [frontend repository](https://github.com/CSCfi/metadata-submitter-frontend/).

## Tests

Tests and flake8 style checks can be run with tox automation: just run `tox` on project root (remember to install it first with `pip install tox`).

## Build and deploy

Production version can be built and run with following docker commands:
```
docker build . -t metadata-submitter
docker run -p 5430:5430 metadata-submitter
```

Frontend is built and added as static files to backend while building. 

## License

Metadata submission interface is released under `MIT`, see [LICENSE](LICENSE).

## Contibuting

If you want to contribute to a project and make it better, your help is very welcome. For more info about how to contribute, see [CONTRIBUTING](CONTRIBUTING.md).
