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
    - `MONGO_USERNAME`, username for connecting to mongodb instance
    - `MONGO_PASSWORD`, password for connecting to mongodb instance
    - `MONGO_HOST`, host and port for mongodb instance (e.g. `localhost:27017`)
    - `MONGO_DATABASE`, If a specific database is to be used, set the name here. 
    - `MONGO_AUTHDB`, if `MONGO_DATABASE` is set and the user doesn't exists in the database, set this to the database where the user exists (e.g. `admin`)
  - Out of the box, metadata submitter is configured with default values from MongoDB Docker image
  - Suitable mongodb instance can be launched with Docker by running `docker-compose up database`
- After installing and setting up database, server can be launched with `metadata_submitter`

If you also need frontend for development, check out [frontend repository](https://github.com/CSCfi/metadata-submitter-frontend/). You will also need to uncomment `REDIRECT_URL` environment variable from .env file.

## Tests

Tests can be run with tox automation: just run `tox -p auto` on project root (remember to install it first with `pip install tox`).

## Developing

Clone the repository
```bash
git clone -b develop git@github.com:CSCfi/metadata-submitter.git
cd metadata-submitter
```

Git hooks are activated inside the local development environment which will run tox tests before pushing. To ignore them for fast updates use `git` with the flag `--no-verify`.

Below we provide two alternative ways of developing, with _VS Code dev containers_ or with _Python virtual environment using a Procfile_.

### Developing with VS Code

VS Code provides functionality to develop inside the docker container. This mitigates the need to install a development environment and difficulties to make things work with different OSs. Also developing inside a container gives you the ability to see code changes on the fly. 

To start using the VS Code devcontainer:
- install extension Remote - Containers
- with CTRL+SHIFT P choose Remote-Container: Reopen in Container
- to run application and debug F5

#### Docker setup

Docker is utilizing the Buildkit builder toolkit. To activate it you might need to update your docker configurations with `{ "features": { "buildkit": true } }` inside the /etc/docker/daemon.json.

If the above is not enough, try:
```bash
$ wget https://github.com/docker/buildx/releases/download/v0.7.0/buildx-v0.7.0.linux-amd64
$ mkdir -p ~/.docker/cli-plugins
$ cp ~/Downloads/buildx-v0.7.0.linux-amd64 ~/.docker/cli-plugins/docker-buildx
$ chmod +x ~/.docker/cli-plugins/docker-buildx
```
and add `{ "experimental": "enabled" }` inside the /etc/docker/daemon.json.

### Developing with Python virtual environment

Install python dependencies, optionally in a virtual environment.

```bash
$ python3 -m venv venv --prompt submitter  # Optional step, creates python virtual environment
$ source venv/bin/activate  # activates virtual environment
$ pip install -U pip
$ pip install -Ue .
$ pip install -r requirements-dev.txt

# generate references for metax integration
$ scripts/metax_mappings/fetch_refs.sh
```

Copy `.env` file and set up the environment variables.
The example file has hostnames for development with VS Code dev containers. You will have to change the hostnames to `localhost`. 

```bash
$ cp .env.example .env  # Make any changes you need to the file
```

Start the servers with code reloading enabled, so any code changes restarts the servers automatically.

```bash
$ honcho start
```

Now you should be able to access the development server at `localhost:5430`.
If it doesn't work right away, check your settings in `.env` and restart the servers manually if you make changes to `.env` file.

**Note**: This approach uses Docker to run MongoDB. You can comment it out in the `Procfile` if you don't want to use Docker.

### Keeping Python requirements up to date

1. Install `pip-tools`:
    * `pip install pip-tools`
    * if using docker-compose pip-tools are installed automatically

2. Add new packages to `requirements.in` or `requirements-dev.in`

3. Update `.txt` file for the changed requirements file:
    * `pip-compile requirements.in`
    * `pip-compile requirements-dev.in`

4. If you want to update all dependencies to their newest versions, run:
    * `pip-compile --upgrade requirements.in`

5. To install Python requirements run:
    * `pip-sync requirements.txt`


## Build and deploy

Production version can be built and run with following docker commands:
```bash
$ docker build --no-cache . -t metadata-submitter
$ docker run -p 5430:5430 metadata-submitter
```

Frontend is built and added as static files to backend while building. 

## License

Metadata submission interface is released under `MIT`, see [LICENSE](LICENSE).

## Contributing

If you want to contribute to a project and make it better, your help is very welcome. For more info about how to contribute, see [CONTRIBUTING](CONTRIBUTING.md).
