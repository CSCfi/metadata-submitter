# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Integration with Metax service
  - Adds new local container for testing against mocked Metax API
  - Introduces new env vars: METAX_USER, METAX_PASS, METAX_URL
  - Adds new key metaxIdentifier to Study and Dataset collections with dict {identifier: <metax_id>, status: "draft"|"published"}
  - Adds new handler MetaxServiceHandler to take care of mapping Submitter metadata to Metax metadata and to connect to Metax API
- Add patching of folders after object save and update operations
  - Object is added or updated to folder(submission) where it belongs with it's accession ID, schema, submission type, title and filename in the case of CSV and XML upload
  - Adds configuration for mypy linting to VScode devcontainer setup
- Templates API #256
  - use `ujson` as default json library
- Creating draft Datacite DOI for folders #257
  - created a mock web app, which would act similarly to DataCite REST API
  - altered `publish_folder` endpoint so that `extraInfo` containing the DOI data is added upon publishing
  - added `datePublished` key to folders which takes in the date/time, when folder is published
- VScode Dev environment #287
  - Add VS Code development container
  - Update docker for development
- Docker-compose and docker-compose-tls files changed to use variables from .env file. #301
- Add folder querying by name #305
  - Add indexing on database initialization
  - Add new field text_name to folder collection
  - Python scripts for database operations. `mongo_indexes.py` for collections and indexes creation to be run if the database is destroyed and `clean_db.py` script with new functionality to only delete documents from collections
  - update github actions
- Add folder querying by date #308
- Add description to JSON schemas #323
  - add JSON schema spelling checker to pyspelling github action
  - optimise wordlist by adding regex ignore patterns
  - added pyspelling to pre-commit hooks (fixed syntax for scripts according to https://github.com/koalaman/shellcheck )
  - enum are sorted alphabetically, with the exception of other and unspecified values which are left at the end of the list
  - allow for accession key in `referenceAlignment` & `process sequence` as array, previously all accession keys were converted to `accessionId` which is not correct
  - add default `gender` as `unknown`


### Changed

- Refactor auth.py package by removing custom OIDC code and replacing it with https://github.com/IdentityPython/JWTConnect-Python-OidcRP. #315
  - New mandatory ENV `OIDC_URL`
  - New optional ENVs `OIDC_SCOPE`, `AUTH_METHOD`
  - Added oidcrp dependency
- Use node 16+ #345
- VScode Dev environment #287
  - Adds requirements-dev.in/txt files. Now pip dependencies can be managed with pip-tools
  - README updated with tox command, development build instructions, and prettify Dockerfile.
- Update ENA XML and JSON schemas #299
- Github actions changed the use of https://git.io/misspell to rojopolis/spellcheck-github-actions #316
- Separated most of the handlers to own files inside the handlers folder #319

### Fixed

- Coveralls report #267
- Typos for functions and tests #279
- Fix spelling mistakes for JSON schemas #323
- Oidcrp does not allow empty values, prefill them in mockauth so front-end can start #333
- Fix development environment #336
  - Add env vars OIDC_URL and OIDC_URL_TEST to mock auth container
  - Adds logging configs for mock auth
  - Updates mock auth api's token endpoint with expiration configs
  - Adds config .pre-commit-config.yaml file required by pre-commit library
  - Redirect url in docker-compose is now default
  - Adds logging for doi mock api

### Removed

- Removed `Authlib` dependency #315

### Deprecated

- Deprecated ENVs `ISS_URL`, `AUTH_URL`, `AUTH_REFERER`, `JWK_URL` #315

## [0.11.0] - 2021-08-31

### Changed

- Package updates

### Added

- Feature/sort folders #249
- Include DOI information in the folder schema #246


## [0.10.0] - 2021-08-12

### Added

- Add integration tests for misses in dataset, experiment, policy

### Changed

- Package updates
- EGA XML schemas version:1.8.0
- Refactor analysis and experiment schemas to adhere to XML schema

### Fixed

- Fix misses for DAC, experiment and policy processing of XML
- Fix misses in JSON Schema

## [0.9.0] - 2021-03-22

### Added

- Use dependabot
- Support simultaneous sessions

### Changed

- Refactor JSON schema Links
- Refactor handlers to be more streamlined
- Validate patch requests for JSON content
- Switch to python 3.8

## [0.8.1] - 2021-02-15

### Fixed

- Bugfix for error pages #202

## [0.8.0] - 2021-02-12

### Added

- TLS support
- Use `sub` as alternative to `eppn` to identify users
- `PATCH` for objects and `PUT` for XML objects enabled
- Delete folders and objects associated to user on user delete

### Changed

- Redirect to error pages
- Extended integration tests

### Fixed

- Fix replace on json patch
- General bug and fixes

## [0.7.1] - 2021-01-19

### Fixed

- Hotfix release #176
  - added check_object_exists to check object exists and fail early with 404 before checking it belongs to user
  - refactor and added more check_folder_exists to check folder exists before doing anything
  - integration test to check objects are deleted properly

### Changes

- Check objects and folders exist before any operation
- Integration check to see if deleted object or folder are still registered in db

## [0.7.0] - 2021-01-06

### Added 

- CodeQL github action #162
- `/health` endpoint #173

- Map `users` to `folders` with `_handle_check_ownedby_user` #158
  - querying for objects is restricted to only the objects that belong to user 
  - return folders owned by user or published
  - added a few db operators some used (aggregate, remove)
  - process json patch to mongo query so that there is addition and replace instead of full rewrite of the document causing race condition
  - standardise raises description and general improvements and fixes of logs and descriptions

### Changed
- Verify `/publish` endpoint #163
- Restrict endpoints to logged in users #151
- Updated documentation #165
- Switch to using uuids for accession ids #168
- Integration tests and increase unit test coverage #166

### Fixed

- Fixes for idp and location headers redirects #150
- Fix race condition in db operations #158
- Fix handling of draft deletion by removing redundant deletion #164, #169 and #172

## [0.6.1] - 2020-11-23

### Added 

- CSRF session #142

### Changed

- Refactor draft `/folder` #144
- Refactor gh actions #140
- Patch publish #141

### Fixed

- Bugfixes for login redirect #139

## [0.6.0] - 2020-10-08

### Added 

- Authentication with OIDC  #133
- Only 3.7 support going further #134
- More submission actions `ADD` and `MODIFY` #137


## [0.5.3] - 2020-08-21

### Changed

- Updated OpenAPI specifications #127
- Python modules, project description and instructions to documentation sources #128
- Added integration tests #129
- Updated documentation #130


## [0.5.2] - 2020-08-14

### Fixes

- Fix mimetype for SVG image and package data

## [0.5.1] - 2020-08-14

### Added

- Add folder POST JSON schema
- Added `/user` endpoint with support for GET, PATCH and DELETE

### Fixes

- Dockerfile build fixes #115
- Fix JSON Schema details #117 
- Missing env from github actions #119
- Typo fixes #120
- Await responses #122


## [0.5.0] - 2020-08-06

### Added

- Centralized status message handler #83
- Alert dialog component #81
- `/folders` endpoint
- `/drafts` endpoint
- JSON validation
- XML better parsing
- Auth middleware
- Pagination

### Changed

- Improved current naming conventions #82
- Login flow with new routes for Home & Login #76, #79, #80
- Change from pymongo to motor

## [0.2.0] - 2020-07-01

### Added

- Added integration tests
- Switched to github actions
- Added base docs folder
- Added more refined XML parsing
- Integration tests added
- Refactor unit tests

### Changed

- Refactor API endpoints and responses
  - error using https://tools.ietf.org/html/rfc7807
  - `objects` and `schemas` endpoints added

## [0.1.0] - 2020-06-08

### Added

- RESTful API for metadata XML files, making it possible to Submit, List and Query files
- Files are also validated during submission process.


[unreleased]: https://github.com/CSCfi/metadata-submitter/compare/v0.11.0...HEAD
[0.11.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/CSCfi/metadata-submitter/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/CSCfi/metadata-submitter/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/CSCfi/metadata-submitter/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/CSCfi/metadata-submitter/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/CSCfi/metadata-submitter/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/CSCfi/metadata-submitter/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.2.0...v0.5.0
[0.3.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/CSCfi/metadata-submitter/releases/tag/v0.1.0
