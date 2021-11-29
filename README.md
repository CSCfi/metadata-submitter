## Metadata submission service for SDA

![Python Unit Tests](https://github.com/CSCfi/metadata-submitter/workflows/Python%20Unit%20Tests/badge.svg)
![Integration Tests](https://github.com/CSCfi/metadata-submitter/workflows/Integration%20Tests/badge.svg)
![Documentation Checks](https://github.com/CSCfi/metadata-submitter/workflows/Documentation%20Checks/badge.svg)
![Python style check](https://github.com/CSCfi/metadata-submitter/workflows/Python%20style%20check/badge.svg)
[![Coverage Status](https://coveralls.io/repos/github/CSCfi/metadata-submitter/badge.svg?branch=master)](https://coveralls.io/github/CSCfi/metadata-submitter?branch=master)

Metadata submission service to handle submissions of EGA metadata, either as XML files or via form submissions. Submissions through graphical frontend and POST are supported.
Service also validates submitted metadata objects against EGA XSD metadata models and saves objects to database.

## Install and run

### Requirements:
- Python 3.8+
- MongoDB
- Docker + docker-compose

### For quick testing:
- copy the contents of .env.example file to .env file
- launch both server and database with Docker by running `docker-compose up --build` (add `-d` flag to run containers in background).

Server can then be found from `http://localhost:5430`.

### For more detailed setup, do following:
- Install project by running: `pip install .` in project root
- Setup mongodb and env variables via desired way, details:
  - Server expects to find mongodb instance running, specified with following environment variables:
    - `MONGO_USERNAME`, username for connecting to mondogdb instance
    - `MONGO_PASSWORD`, password for connecting to mondogdb instance
    - `MONGO_HOST`, host and port for mongodb instance (e.g. `localhost:27017`)
    - `MONGO_DATABASE`, If a specific database is to be used, set the name here. 
    - `MONGO_AUTHDB`, if `MONGO_DATABASE` is set and the user doesn't exists in the database, set this to the database where the user exists (e.g. `admin`)
  - Out of the box, metadata submitter is configured with default values from MongoDB Docker image
  - Suitable mongodb instance can be launched with Docker by running `docker-compose up database`
- After installing and setting up database, server can be launched with `metadata_submitter`

If you also need frontend for development, check out [frontend repository](https://github.com/CSCfi/metadata-submitter-frontend/).

## Tests

Tests can be run with tox automation: just run `tox -p auto` on project root (remember to install it first with `pip install tox`).

## Developing

Docker is utilizing the Buildkit builder toolkit. To activate it you might need to update your docker configurations with `{ "features": { "buildkit": true } }` inside the /etc/docker/daemon.json.

If the above is not enough, try:
```
$ wget https://github.com/docker/buildx/releases/download/v0.7.0/buildx-v0.7.0.linux-amd64
$ mkdir -p ~/.docker/cli-plugins
$ cp ~/Downloads/buildx-v0.7.0.linux-amd64 ~/.docker/cli-plugins/docker-buildx
$ chmod +x ~/.docker/cli-plugins/docker-buildx
```
and add `{ "experimental": "enabled" }` inside the /etc/docker/daemon.json.

### Developing with VS Code

VS Code provides functionality to develop inside the docker container. This mitigates the need to install a development environment and difficulties to make things work with different OSs. Also developing inside a container gives you the ability to see code changes on the fly. 

To start using the VS Code devcontainer:
- install extension Remote - Containers
- with CTRL+SHIFT P choose Remote-Container: Reopen in Container
- to run application and debug F5

Git hooks are activated inside the local development environment which will run tox tests before pushing. To ignore them for fast updates use the flag `--no-verify`.

## Build and deploy

Production version can be built and run with following docker commands:
```
docker build --no-cache . -t metadata-submitter
docker run -p 5430:5430 metadata-submitter
```

Frontend is built and added as static files to backend while building. 

## License

Metadata submission interface is released under `MIT`, see [LICENSE](LICENSE).

## Contibuting

If you want to contribute to a project and make it better, your help is very welcome. For more info about how to contribute, see [CONTRIBUTING](CONTRIBUTING.md).
