## Metadata submission backend

Minimum viable product that:
- Accepts HTTP POST submissions of EGA metadata XML files 
- Validates XML files against EGA XSD metadata models 
- Saves XML files to database

## TODO
- Write tests
- Write middlewares
- Handle authentication via oauth token 

## Install and Run

```
$ pip install .
```

After install the application can be started with: `$ `

## Tests and Documentation

In order to run the tests: `$ tox` in the root directory of the git project. Install tox with pip, if not already in system

To build documentation locally:
```
$ cd docs
$ make html
```
