# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `lastModified` to folder to keep track when a folder or the objects in a folder change and be able to filter via the `lastModified`
- connection checking and `retry`-mechanism for calls to Metax-service in case of server and connection errors
- Endpoint for submitting DOI information. #389
- Endpoint with swagger documentation `/swagger`
- added `aiohttp_session` as dependency and removed old way of handling cookies
- Create a new ServiceHandler class to share error handling, retry mechanism, custom request logic between service integrations.
- Integration with REMS #498
  - New rems service handler
  - New rems mock api service for integration tests
  - New API endpoint `/v1/rems` for the frontend to retrieve DAC and Policies
  - Submission now can have a new field, `dac` (changed to `rems` in #648), with `workflowId`, `organizationId`, and `licenses` (array of int)
  - Published datasets have a new field `dac` (changed to `rems` in #648) with `workflowId`, `organizationId`, `resourceId`, and `catalogueItemId`
- Pylint static checks
- Added mapping for languages between the submitter and Metax-service #514
- Added mapping for subjects from submission doi info to Metax field_of_science #556
- Run integration tests with pytest
  - run integration tests with `--nocleanup` option
- Support for LifeScience groups as a substitute to CSC projects #548
- Support for `Bearer` tokens, opening use of the API without frontend. Tokens are validated from the configured `OIDC_URL`
- Made [PKCE](https://oidcrp.readthedocs.io/en/latest/add_on/pkce.html) settings explicit in `oidcrp` client auth
- Added [DPOP](https://oidcrp.readthedocs.io/en/latest/add_on/dpop.html) placeholder settings for when AAI support has been implemented
- Add advanced health checks for Datacite, REMS and Metax and performance checks for API response #585
- pre-commit check to sort and remove duplicates in the dictionary
- [vulture](https://github.com/jendrikseipp/vulture) as a tox env and pre-commit hook.
- Add endpoint for fetching workflows #362
- Add checks so that submission conforms with the workflows #591
- Add new schema `file.json` to represent files which are linked to a submission #148
  - Add a corresponding field to `submission` that lists files attached to a submission #148
- Add `pytest-xdist` to run unit tests faster, in parallel #626
- add MessageBroker class with MQPublisher and MQConsumer separate classes functionality #148 #622
  - add cli tool for MQConsumer so that we can deploy multiple consumers independently of the web server
  - add message broker publishing to workflow
  - add rabbitmq + default config to integration tests
- File operator that does database operations for files #148
  - introduced `/v1/submissions/{submissionId}/files` to update and remove files in a submission #633
  - file flagged for deletion also removed from submission and check files have the status ready when being read from the submission #633
  - prevent publish if files have in submission have status added (added but no metadata object) or failed (failed in ingestion, completion, or for any other reason) #633
- Mongo indexes for `file` schema #148
- `/files` endpoint to retrieve files attached to a project #148 #627
- option to add additional members to `application/problem+json` #642
- Bigpicture sample, image and dataset XML schemas were added and JSON schemas for those objects were produced #445 #481 #491

### Changed
- schema loader now matches schema files by exact match with schema #481. This means that schema file naming in metadata_backend/helpers/schemas now have rules:
  - file name starts with schema provider separated with dot or underscore (e.g. EGA.policy.xsd, ena_policy.json) or
  - if schema is local then no schema provider needs to be added (e.g users.json)
  - schema name and mongo database collection name must be the same
- migrated to variables used by motor 3 for ssl https://motor.readthedocs.io/en/stable/migrate-to-motor-3.html?highlight=ssl_certfile#renamed-uri-options
  - env vars `MONGO_SSL_CLIENT_KEY` and `MONGO_SSL_CLIENT_CERT` are replaced with `MONGO_SSL_CLIENT_CERT_KEY`
- Refactor **folder** to **submission** #411
- HTTP PATCH for submissions has changed to only accept 'name' and 'description' in a flat JSON object.
- Better (metax) error handling #382
  - HTTPError exceptions return a response with JSON Problem instead of an HTML page #433
  - Make Metax errors visible to user #453
  - Catch unexpected errors and return a JSON Problem instead of server crashing #453
- Fix session and authorization issues
  - Prefix API endpoint with /v1
  - Refactor authentication checking, fixing issues from #421 and remove HTTPSeeOther from the API
- Recreate DB before integration tests run and cleanup after integration tests have run #448
- Make using of discovery service (METAX) optional #467
- Refactor api handlers to share a single instance of service handlers
- Refactor metadata creation methods to parse and add separate metadata objects to db from a single XML file #525
- Validate schema definitions, updating them to JSON schema 2020-12 #581
- changed HTTP header `Server` to `metadata`
- enabled new pylint checks #597 `logging-fstring-interpolation`, `fixme`, `useless-param-doc`, `suppress-message`
- reformatted logs to style `{` and refactored some of the messages to be clearer #597
- exceptions now default to `log.exception` with stacktrace #597
- POST/PATCH/PUT/DELETE requests on published submission responds with 405 instead of 401 HTTP response #618
- Submissions must have a `workflow` #591
- Refactor `publish` endpoint into its own python `class` and `module` #591
- Refactored Mongo queries to return the value for a single field #591
- There's more clear distinction between publishing to each integration: `datacite`, `metax`, and `rems` #591
- Separated operator classes into their own files for better readability #625
- updated ENA XML and JSON schemas to 1.16 #628
  - XML to JSON parser had to be adjusted for `assemblyGraph`
- Refactor `Operator` -> `ObjectOperator` #627
- Refactor `xml_object.py` -> `object_xml.py` #627
- Refactor operators to use a common base class called `BaseOperator` #627
- XML validation errors now compile all the failing elements into same error message and include the line number in the error reason #630
- Changed the submission object's `dac` field to `rems` and its subsequent endpoints similarly #648
- XML to JSON parser/converter was enhanced to accommodate for the new Bigpicture XML objects #445 #481 #491
- Updated BP sample XML and JSON schema, its parsing method and its related example file and tests #650

### Removed

- remove `datacite.json` to render the form from `folder["doiInfo"]`
  - we removed `namedtype` for `contributors` and `creators` we therefore allow `additionalProperties`
  - `subjectsSchema` is a given by frontend thus we allow via `additionalProperties`
- Removed `OIDC_ENABLED` testing variable which can cause misconfiguration incidents
- Removed `METAX_ENABLED` as superseded by the introduction of workflows #591
- Removed `REMS_ENABLED` as superseded by the introduction of workflows #591

- remove unused code related to change from user to project ownership caused by faulty rebase or rollback of certain features #579
- Remove dictionary de-duplication from `pre-commit`'s `sort` hook #626

### Fixed
- Schemas endpoint returned `400` for `/v1/schemas/datacite` #554
- XML delete when an object or submission is deleted #579
- small pylint issues e.g. web.HTTPSuccessful was never being raised #579
- fix `Any` type wherever that is possible. #579
- Published submissions and its objects cannot be altered #584
- Incorrectly marking a workflow schema as required because its step is required #591
- Incorrectly marking a workflow schema as required when it appears in the `requires` field of a schema that is not required #591
- deprecated syntax in github publish action for `::set-output` and better default param. Dockerfile fix for github actions
- mypy complaining about default values `None` in service handler

## [0.13.1] - 2022-05-31
### Changed
- migrated to variables used by motor 3 for ssl https://motor.readthedocs.io/en/stable/migrate-to-motor-3.html?highlight=ssl_certfile#renamed-uri-options #420
  - env vars `MONGO_SSL_CLIENT_KEY` and `MONGO_SSL_CLIENT_CERT` are replaced with `MONGO_SSL_CLIENT_CERT_KEY`
- adds required field affiliation for creator and contributor in datacite schema #399

## [0.13.0] - 2022-04-07

### Added

- Submission endpoint update #371
  - Adds mandatory query parameter `folder` for submit endpoint POST
  - On actions add and modify object is added or updated to folder(submission) where it belongs with it's accession ID, schema, submission type, title and filename
  - Adds metax integration to submit endpoint
- Integration with Metax service #356 #387
  - Adds new local container for testing against mocked Metax API
  - Introduces new env vars: `METAX_USER`, `METAX_PASS`, `METAX_URL` for connection to Metax service
  - Introduces new env var `DISCOVERY_URL` for creating link to dataset inside Fairdata SD catalog
  - Adds new key metaxIdentifier to Study and Dataset collections containing metax id returned from Metax API
  - Adds new handler MetaxServiceHandler to take care of mapping Submitter metadata to Metax metadata and to connect to Metax API
  - Adds new mapper class to adjust incoming metadata to Metax schema
- Add patching of folders after object save and update operations #354
  - Adds mandatory query parameter `folder` for objects endpoint POST
  - Object is added or updated to folder(submission) where it belongs with it's accession ID, schema, submission type, title and filename in the case of CSV and XML upload
  - Adds configuration for mypy linting to VScode devcontainer setup
- Templates API #256
  - use `ujson` as default json library
- Creating draft Datacite DOI for folders #257 #332
  - created a mock web app, which would act similarly to DataCite REST API
  - altered `publish_folder` endpoint so that `extraInfo` containing the DOI data is added upon publishing
  - added `datePublished` key to folders which takes in the date/time, when folder is published
- DOI Publishing and deletion to Datacite #332 #369
  - create draft DOIs for both Study and Datasets and add them to the folder `extraInfo` when published
  - delete draft DOIs on object delete
  - update DOI info at Datacite when folder is published
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
- Project ownership #346
  - added new collection `project`
  - added new key `projects` to `user`
  - added new key `projectId` to `folder` and `template-*` collections
  - new mandatory `/userinfo` value from AAI at login time `sdSubmitProjects`
    - user is redirected to an info page by AAI if key is missing
  - new mandatory query parameter `projectId` in `GET /folders`
  - new mandatory JSON key `projectId` in `POST /folders` and `POST /templates`
  - new endpoint `GET /templates` to replace `GET /users/current` `{"templates":[...]}`
  - new JSON keys `index` and `tags` to `PATCH /templates/schema/templateId`, same values as were previously used in `PATCH /user` which is now removed
  - WARNING: breaking change that requires fresh database, because "project" is new information that did not exist before, and it can't be migrated to existing user-owned hierarchy
- Multilevel add patch objects to support `/extraInfo/datasetIdentifiers/-` which needs dot notation for mongodb to work e.g. `extraInfo.datasetIdentifiers` #332

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
- allow inserting only one study in folder #332
- JSON schemas #332
   - introduce `keywords` required for Metax in `doiInfo`
   - dataset `description` and study `studyAbstract` are now mandatory
- `keywords` will be comma separated values, that will require splitting when adding to Metax API

### Fixed

- Coveralls report #267
- Typos for functions and tests #279
- Fix spelling mistakes for JSON schemas #323
- Oidcrp does not allow empty values, prefill them in mockauth so front-end can start #333
- Fix development environment #336
  - Add env vars `OIDC_URL` and `OIDC_URL_TEST` to mock auth container
  - Adds logging configs for mock auth
  - Updates mock auth api's token endpoint with expiration configs
  - Adds config .pre-commit-config.yaml file required by pre-commit library
  - Redirect url in docker-compose is now default
  - Adds logging for doi mock api

### Removed

- Removed `Authlib` dependency #315
- Project ownership #346
  - deprecated `folders` and `templates` keys from `GET /users/current`
    - as a side effect, deprecated `items` query parameter from the same endpoint
  - deprecated `PATCH /user`

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


[unreleased]: https://github.com/CSCfi/metadata-submitter/compare/v0.13.0...HEAD
[0.13.0]: https://github.com/CSCfi/metadata-submitter/compare/v0.10.0...v0.13.0
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
