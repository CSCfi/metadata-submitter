## Submission interface backend

Currently minimum viable product that:
- accepts HTTP POST submissions of EGA metadata XML files 
- validates XML files against EGA XSD metadata models 
- saves XML files to Mondogb database

## Install and Run

Clone project and install it by running: `pip install .`

Server expects to find mongodb instance running, spesified by following environmental variables:
- `MONGO_INITDB_ROOT_USERNAME`, username for admin user to mondogb instance
- `MONGO_INITDB_ROOT_PASSWORD`, password for admin user to mondogb instance
- `MONGODB_HOST`, host and port for mongodb instance (e.g. `localhost:27017`)

Server looks for current environmental variables first and if needed variables aren't found, checks .env file. This allows running server without writing variables with .env file.

If wanted (e.g. when running locally), suitable mongodb instance can be launched with help of docker-compose file present in folder `deploy/mongodb`. Correct environmental variables for both docker-compose and server are set in .env -file present in project root.

After installing and setting up database, server can be launched with `metadata_submitter`.

## Tests

Tests and flake8 style checks can be run with tox automation: just run `tox` on project root (remember to install it first with `pip install tox`).

## Build and deploy

Install docker and [S2I (Source-To-Image)](https://github.com/openshift/source-to-image), and run
```
s2i build . centos/python-36-centos7 metadata_backend
docker run -p 5430:5430 -e APP_FILE=metadata_backend/server.py metadata_backend
```

## License

Metadata submission interface is released under `MIT`, see [LICENSE](LICENSE).

## Contibuting

If you want to contribute to a project and make it better, your help is very welcome. For more info about how to contribute, see [CONTRIBUTING](CONTRIBUTING.md).
