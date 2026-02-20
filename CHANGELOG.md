# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Calendar Versioning](https://calver.org/).

## [Unreleased]

### Removed

- (users) Workflow path parameter from submit endpoints.
- Previously used methods and mentions of OpenAPI specification generation.

### Fixed

- Mockauth hostname issue when running integration tests in local env
- (users) Unauthenticated API calls will result in `401 Unauthorized` error response, not `500 Internal Server Error`

### Changed

- Integration tests can be run inside a dedicated container for CI purposes
- Workflows are deployment specific
- OIDC callbacks are hidden from OpenAPI docs.
- All deployments support both web browser and cli login methods.
- Make OIDC DPoP enabling configurable.

### Added

- Use mock-oauth2-server for integration tests.

## [2026.2.0] - 2026-02-06

### Changed

- Authorization flow uses RFC 9449 DPoP mechanism
- (users) GET /submissions endpoint no longer requires project_id if the user has only a single project (e.g. in the NBIS deployments).
- (users) PATCH /submit no longer returns the submission.json document.
- Exclude unused environmental variables when initialising CSC and NBIS services.
- Create ROR service handler only for the CSC deployment and added ROR to service health check.
- Improved multipart /submit request error messages.
- Simplified publish handling and removed previous publish configuration.
- Create Datacite, CSC PID and Metax service handers only when the deployment type requires it.
- Use different databases for CSC and NBIS integration tests.
- Improved OIDC related tests.
- Renamed environment variables (database, discovery URLs, OIDC, admin polling) and switched to lazy loading via configuration models.
- Refactored handler architecture (API and service handlers), unified service injection, and reorganized classes into appropriate packages.
- Refactored health check handling across API and service handlers, including a simplified base class structure.
- S3 and Keystone environment variables use config pydantic models
- `files` table `bytes` column datatype from `INTEGER` to `BIGINT`
- Migrated to using Metax V3 API
- Overhauled integration test setup to accommodate testing against test DataCite and PID API services.
- Updated DataCite schema handling (types, rightsList, geolocation points, polygon handling) and improved BigPicture XML/DataCite parsing.
- Refactored PID, DataCite, OIDC, and deployment environment configurations to use Pydantic and reorganized them under conf/ for isolated loading.
- simplified registration related unit tests.
- support a single registration only in Postgres. Simplifies schema e.g. replaces registration_id with submission_id.
- support a single registration only in API. Simplifies code e.g. replaces list of registrations with a single one.
- Removed frontend from Dockerfile (#919)
- Replaced Alpine container images with Debian trixie images in Dockerfile (#919)
- Changed 'BP.bp' XML schema file prefix to 'BP.' to comply with official BigPicture naming convention.
- Add and use DataCite XML document root path (DATACITE_PATH).
- Moved BigPicture and FEGA XML processor tests in separate files. Shared test functions are test_utils.py.
- Moved BigPicture and FEGA XML processor configurations in separate files.
- moved test specific defaults values from OIDC env variables to conftest.py.
- read OIDC env variables using BaseSettings.
- Get files in bucket and check bucket access endpoints use preset static EC2 credentials
- List all buckets and grant access to bucket endpoints create user and project specific EC2 credentials upon request for a single use.
- Increased  mypy validation coverage and made related code changes. For example, replaced XmlObjectIdentifier with ObjectIdentifier.
- Enabled ruff fixes and made related code changes in tests.
- Use BigPicture dataset id as the submission id. BigPicture does not support submission ids.
- Make project id optional in new submit URLs to make it possible for BigPicture Swedish submitter to submit without defining a project id. For BigPicture Swedish submitters the project_id is the user_id and this can be retrieved from the JWT token.
- Simplify new submit URLs.
- improved get and verify user projects tests.
- moved ldap.py code to project.py file to have all ProjectService code in one place.
- Made Pydantic models strict to fail fast and improve data validation.
- patch /submissions/{submissionId}/rems to return 204 instead of submission id
- patch /submissions/{submissionId}/metadata to return 204 instead of submission id
- renamed patch /submissions/{submissionId}/doi endpoint to /submissions/{submissionId}/metadata
- API model fields to either use Python case or camel case but not both. Simplifies code and reduces false positive lint errors.
- Improved submission.json update to simply merge new field values to old values. Field values can't be accidentally removed but can be explicitly removed by setting field value to null or to empty collection.
- Removed workflow.json and workflow configuration jsons as these are no longer used by the API.
- "workflow" field "SDSX" enumeration value to "SD".
- "workflow" field type to SubmissionWorkflow enum in Submission Pydantic model.
- Renamed "doiInfo" to "metadata" in submission.json document.
- validate and format Datacite subjects according to OKM field of science only when the workflow is SD.
- Datacite Publisher is now set in the Pydantic model. Default is "CSC - IT Center for Science".
- Datacite resourceTypeGeneral and resourceType are now set in Pydantic model. Can be overriden during publish if needed.
- moved Datacite controlled vocabulary whitespace removal from publish to Pydantic model.
- moved Datacite name field population using givenName and familyName from publish to Pydantic model.
- using server side functionality to set all default and update values. Fallbacks exist for SQLLite.
- added database check constraints for enumerations.
- file postgres service and repository ingest status update to be able to update ingest error and error type.
- file postgres service and repository file retrieval to make submission_id optional. Needed later if we want to process files over all submissions rather than one submission at a time.
- update files.ingest_status in NeIC SDA ingest only when the status is verified, ready, or error. Other NeIC statuses are not saved in SD Submit Postgres.
- minor changes to NeIC SDA ingest to use the IngestStatus enumeration
- For simplify changed IngestStatus enumeration to be the same as in NeIC SDA pipeline.
- Previously used mock S3 docker image to a docker image from motoserver that supports handling bucket policies
- Bucket listing and file listing methods now check bucket policies first and do not return buckets/files that do not have the correct bucket policy assigned
- (users) Data folders are now referred to as buckets. This affects the endpoints previously dealing with "folders" incl. `PATCH /submissions/{submissionId}/folder` -> `PATCH /submissions/{submissionId}/bucket`
- Everything previously referred to as "folders" regarding data is now referred to as "buckets"
- (users) object_type rather than schema_type is now saved in Postgres and generally used instead of the schema_type e.g. in accessioning.
- (users) UserErrors exception to return a list of errors in RFC 7807 format.
- (users) removed /validate endpoint for XML validation.
- (users) removed /objects endpoints.
- (users) In SDSX submissions, publishing operation now automatically fetches a list of files from a designated folder in an object storage to be included in the submission
- (users) /publish endpoint so that if it fails for any reason, the user is expected to call it again to re-try failed actions (#900)
- (users) PATCH /submission endpoint so that any field can be safely changed instead of name and description only. The submission document can be updated by the user, however, some fields can't be removed or changed and existing values are preserved (#900)
- (users) publish action requires that the submission has at least one file (#900)
- LDAP is now used instead for getting list of user's projects (#891)
- OIDC callback returns JWT token in secure cookie (#884)
- Middleware authentication requires JWT cookie or API key (#884)
- Renamed DISCOVERY_URL to METAX_DISCOVERY_URL and added BEACON_DISCOVERY_URL variable (#900)
- 'publish' part of workflow.json schema includes, which schemas should be included in each step: datacite (pid or datacite), rems, or discovery (metax or beacon) (#900)
- Study description is no longer a separate field from study abstract in DataCite data (#900)
- JSONValidator 'validate' property complies with Python conventions (#900)
- /submission endpoint now keeps state by writing external resource information (e.g. DOI or metax ID) into 'registrations' table after each external call (#900)
- PublishAPIHandler handler and 'publish_submission' method are improved as it is clearer, which parameters are passed to them (#900)
- Moved accessioning to its own service (api/services/accession.py) (#900)
- refactored the API to fetch and store info with Postgres tables instead of MongoDB collections (#900)
- submission title and description are now stored in submissions table columns.
- refactored publish_submission function for better readability. E.g. added `_filtered_registrations` helper function and moved some registration code to new instance methods.
- SDSX registration during publish now uses submission title, description and id instead of dataset title and description and id.
- (users) Updated subjects and contributors in submission doiInfo schema to resemble Qvain
- Secure header used in cookies is configurable with environment variable
- Docker file uses base uv image instead of installing uv from script
- fixed and refactored AccessService tests.
- (users) Updated creators in submission doiInfo schema to resemble Qvain
- when calling backend, the admin token is assumed to be in the `X-Authorization` header
- `/ingest` no longer needs json payload
- Renamed and tested debug log helpers (#869)
- Moved vulture configuration to project.toml (#869)
- renamed vulture whitelist to vulture_whitelist.py.
- moved spellcheck to tox.
- use tox-uv to manage virtual environments using tox.
- Reword all "Big Picture" related words to the correct format "Bigpicture"
- object_base inherits from BaseOperator class instead of abstract base class
- Reformat accession ID for Bigpicture's schemas and file
- Updated OpenAPI specifications to version 3.1.1
- Retitled PUT requests for updating DOI, REMS or linked folder info in a submission to be a PATCH request instead
- Updated dependencies

### Fixed

- Resolving REMS organisation from workflow for resource and catalogue item.
- Metax mapping did not use ROR organisation identifiers or preferred labels as keywords.
- Improved Metax and Datacite mapping for field of science.
- Auth healtcheck.
- Metax healtcheck.
- (users) Submission registration endpoint now returns 404 when publish has not been called.
- DataCite integration test mock service can now generate a DOI.
- Dockerfile to run Python in the given normal user `submitter` space.
- several bugs related to submission.json and metadata object submissions.
- (users) changed ints to datetimes in submission model for date fields.
- (users) submission.json serialization in Postgres submission service.
- Metax 'creator' and 'contributors' mapping in MetaxMapper (#900)
- /publish not calling DataCite publish for datasets (#900)
- (users) Removed no longer used userId field from post_project_files payload validation error message. #883)
- Filter accession IDs in `get_collection_objects()` to only match `collection`
- (users) any user_id can be provided in post project files endpoint (#874)
- Clarify error when trying to retrieve bprems from objects endpoints (#871)

### Added

- DPoPHandler to assist with implementing DPoP mechanism since `idpyoidc` library hasn't implemented it properly
- semicolons to create.sql file.
- database health check.
- REMS integration tests.
- Integration testing for FileProviderService using Allas test service
- Script for generating Metax reference data for ROR organizations and geolocations
- Mapping from Datacite's metadata to Metax V3's fields
- Low-level integration testing for DataCite and CSC PID service handlers, including DOI creation logic and new GET support.
- Centralized DataCiteService providing DataCite and CSC PID DOI creation, publishing, and shared functionality.
- CI/CD pipeline for automatically creating API docker images
- Update DataCite and REMS URLs in BigPicture landing page XML.
- tests for reading env variables using BaseSettings.
- Added ALLOW_REGISTRATION env to disable registrations in QA deployment.
- pouta_access_token from AAI userinfo object is stored in session cookies.
- Integration with Pouta Keystone service for fetching project scoped EC2 credentials.
- DEPLOYMENT env variable (CSC, NBIS) to prepare for BigPicture Swedish deployment. Selects the ProjectService.
- NbisProjectService (NoProjectService) that uses user_id as the project_id.
- ALLOW_UNSAFE environmental variable to delete published submissions in integration tests.
- post /workflows/{workflow}/projects/{projectId}/submissions/ now supports SD submissions (submission.json).
- patch /workflows/{workflow}/projects/{projectId}/submissions/{submissionId} endpoints.
- head and delete /workflows/{workflow}/projects/{projectId}/submissions/{submissionId} endpoints.
- check that metadata object name is unique for an object type within a project before object is saved.
- check that submission name is unique within a project before submission is saved.
- project_id column to the objects Postgres table to easily find objects by name in a project.
- Datacite xml reader creates the Pydantic datacite model.
- Datacite nameType mandatory field population in Pydantic model when givenName and familyName have been provided.
- all missing fields to datacite Pydantic model.
- schema generation code.
- files.created and modified columns.
- files.ingest_error_count column.
- files.ingest_error_type column with values: user_error, transient_error, permanent_error
- schema creation, dropping and granting SQL.
- (users) Endpoint for a user to check whether a bucket can be accessed in SD Submit in a specific project
- (users) Endpoint for a user to grant SD Submit API read access to buckets in an S3 instance
- Functionality to add and read bucket policies of S3 buckets
- ruff linter to make linting faster and less rigorous (to require less developer effort to pass)
- (users) more accessioning unit tests.
- (users) New XML POST endpoint stores the submitted BP XML metadata objects in the Postgres database.
- (users) New POST endpoint generates the submission.json from submitted BP XMLs (except datacite information). - Added: New XML POST endpoint stores the generated submission.json in the Postgres database.
- (users) New POST endpoint injects BP accessions in the XML metadata objects including references.
- (users) New POST endpoint validates the minimum and maximum number of expected BP metadata objects within non-complementary datasets.
- (users) New POST endpoint validates that BP XML references point to existing metadata objects in non-complementary datasets.
- (users) New POST endpoint identifies BP XML objects and validates them against their BP XML Schemas.
- (users) GET /submissions/{submissionId}/objects/docs endpoint to get metadata  documents in submission. Only supported for BP.
- (users) GET /submissions/{submissionId}/objects endpoint to list metadata objects in submission.
- (users) POST /workflows/{workflow}/projects/{projectId}/submissions multipart/form-data endpoint for making submissions with metadata. Only supported for BP.
- XmlFileDocumentsProcessor uses fsspec to support other file systems in addition to the unix filesystem.
- New XML processor uses a fast C based XML Schema validator.
- configured the XML processor for BP and FEGA.
- Configurable XML processor to validate XML schemas, and to inject ids given names.
- (users) Endpoints and functionality for fetching a list of files or folders from an object storage (e.g. via S3 API)
- Use of adobe/S3Mock docker image for integration testing purposes
- FileProviderService for handling requests to file provider APIs such as S3
- Add more mock data to mock rems api for better frontend testing
- (users) New projects get endpoint to retrieve user's projects (#891)
- (users) API key endpoints to add, list and remove API keys (#884)
- (users) GET /submissions/{submissionId}/registrations endpoint to list external registrations (e.g. DOI or Metax ID) for the submission or its metadata objects (#900)
- (users) Required field "title" to submission json payload, which is needed to register the submission to DataCite etc.
- 'to_json' function that converts python dict to json and supports datetime conversion without microseconds (#900)
- Pydantic models (api/models.py) for most API handling operations (#900)
- 'JsonObjectService' and 'XmlObjectService' and moved some metadata object related functionality to those classes (#900)
- 'submissions', 'objects', 'files' and 'registrations' Postgres tables, repositories and services for storing everything in Postgres, which was previously stored in a MongoDB instance (#900)
- "submission" field in workflow.json under "publish" sections. This is used to indicate that the submission.json should be used, instead of a metadata object, to extract information for DataCite etc. registration. This also indicated that the registration information should be stored in the submissions table without an object id, as it is not associated with any metadata object.
- Automatic version number updating CI job
- FileService to check that submitter files exist and return their size.
- env `POLLING_INTERVAL` so that `POLLING_INTERVAL` is configurable
- release dataset for BigPicture submissions during `/announce`
- APiKeyRepository to save and remove API keys in Postgres.
- Makefile for pulling secrets from a Vault instance required by new integration tests
- LDAP service to get user's CSC project.
- Check accession id in PUT object XML content (#876)
- create dataset via Admin API once files are ready
- polling Admin API to see when all files are ready
- Functions for API key creation, validation, revoking, and listing. Storage to be changed to persistent storage in a future MR.
- Functions for JWT token creation and validation. Uses standard subject (`sub`), expiration (`exp`), issued-at (`iat`), and issuer (`iss`) claims. Internal user id stored in 'sub'. Signature, expiration and issuer are checked during validation.
- uv to manage virtual environments, tools and dependencies.
- Clarify that bprems cannot be deleted or modified through objects endpoints (#879)
- post file accession IDs via Admin API once files are verified
- polling Admin API to see when all files are verified

### Removed

- frontend files support.
- removed the taxonomy search endpoint.
- Echoing of all Sqlalchemy log messages
- Extra codes in metax_mapper
- Generated json file for identifier_types and related codes
- Mock metax service and use real Metax test instance for integration test
- Metax reference data for funding reference
- DataCite and PID mock services from testing environment.
- DATACITE_PREFIX mock environmental parameter as unnecessary.
- support for DataCite related study references.
- support for DataCite study registration.
- Replaced black with ruff.
- support for fega study is publish to simplify publish code and metax mapping.
- unused api endpoints path /rems, /metadata, /bucket.
- text_name field from the Submission Pydantic model.
- spell checking
- pylint and flake linters
- Removed Files and Datacite steps from workflow schemas
- (users) Metadata objects drafts.
- Endpoints relating to files metadata objects being stored and fetched from MongoDB collection that are now unnecessary
- Use of MongoDB by the backend entirely
- (users) User related endpoints (#895)
- (users) /submit XML endpoint (#910)
- (users) Multi-part content type support from /objects and /drafts endpoints. Both JSON and XML are now given in the request body (#900)
- (users) 'announce' endpoint as redundant (#900)
- user and project MongoDB collection and all related code (#891, #895)
- aiohttp session (#884)
- 'files', 'metadataObjects', 'drafts' and 'extraInfo' keys from submission json object. Information is stored directly in Postgres tables instead (#900)
- SUBMISSION_ONLY_SCHEMAS as all supported metadata objects are now real (#900)
- Support for CSV files (#900)
- Support for dataset metadata objects for SDSX workflow
- (users) template related API endpoints and database layer functions as unnecessary functionality. This is not needed by programmatic submitters and not used by the interactive frontend (#885).
- template related API endpoints and database layer functions to lower the total cost of ownership and get the product to production faster (#885).
- Spellchecking in gitlab-ci.yml (#858)
- GitHub workflows.
- overlapping tasks in gitlab-ci.yml, pre-commit and tox.

### Deprecated

- Usage of Metax V2
- removed code and files no longer used by the API, for example unused XML, JSON and workflow code.

## [2025.4.0] - 2025-04-01

### Added

- Added mock PID service and PID tests (#839)
- minimal and full publication test cases for each workflow
- (users) Process information from XML file for bprems schema and add it to the rems key in a BP submission
- Use CSC PID service for DOI in FEGA and generic workflows (#827)
- Implemented support for Bigpicture annotation and observer metadata schemas
- Included new Bigpicture related schemas
- Add /ingest endpoint for starting data ingestion
- Mocked Admin API service #843
- Instructions on how to use the SD Submit API for BigPicture programmatic dataset submissions #815
- Defined a discovery service for each workflow 512
- Total size of files is included in Metax metadata #507
- Tests for taxonomy search #826
- Created an endpoint for getting taxonomy names and id based on NCBI database dump files #281
- Endpoint for flagging file as deleted #824
- BP metadata gets accession attribute added to the XML content as well before it's stored #818
- Endpoint to add and remove a linked folder path to a submission #825
- new format for error responses of /validate endpoint #641
- Validate files against file schema #823
- List of Funding references from crossref API and enum values for Funder Names in Submission schema #817
- Added a POST endpoint for receiving file information #814
- Added additional 'announce' endpoint for BP workflow and to openapi document #813
- Added new endpoint `/users/{userId}/key` for generating a signing key #777

### Changed

- Updated instructions in the README and the CONTRIBUTING files
- Altered and removed some of the Github actions workflows that were either not doing the correct thing or not needed anymore
- (users) Submission can no longer have the same name inside the project
- (users) Previous functionality behind POST and PUT request for adding/modifying submission files is unified and the endpoint is retitled to `PATCH /v1/submissions/{submissionId}/files`
- Updated OpenAPI specifications
- all required schemas are needed before publishing a submission in unit and integration tests
- Updated some EGA related XML schemas to be up-to-date
- (users) Bigpicture related metadata validation process now follows the Bigpicture metadata version 2.0.0
- Updated XML to JSON conversion logic to accommodate new metadata schema versions
- REMS object is refined and validated when it is added to a submission #532 #649
- GET files request returns only latest file versions #840
- Removed large taxonomy related `names.json` file from the repository commit history and brought  back as git LFS pointer file
- Modify SDSX workflow to be the same as FEGA workflow
- Refactored POST files endpoint to address several issues #828
- BigPicture workflow no longer requires a study
- XML objects are parsed from multipart XML structure into single objects before storing so the content matches with its JSON counterpart #818
- Modified workflow for Generic use case #821
- Updated middleware to accept user signed tokens #777
- Switch to `idpyoidc` library instead of `oidc-rp`
- Updated dependencies

### Removed

- Some XSD files which are perceivably not being utilized at the moment
- Previously implemented logic that automatically converted ISO-8601 duration string in incoming metadata to a numeric value
- Some schemas that are unnecessary for Generic use case workflow #841
- RabbitMQ message broker functionality

### Fixed

- Fixed faulty Datacite unit tests (#859)
- Addressed utcnow deprecation warnings
- Fix pyspelling not ignoring urls (#857)
- Update broken and permanent redirect links in documentation (#856)
- Fixed taxonomy script file permissions and ´docker casing warnings
- Automated changelog generation with CI jobs and github actions recognizes git LFS files
- Add missing schema check that disallowed multiple metadata objects
- Fixed newly posted versions of deleted files still showing up as deleted #828
- Fixed bugs in file version creation #823

## [2024.01.0] - 2024-01-15

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
- Bigpicture observation XML schema was added and JSON schema for it was produced #665
- Bigpicture staining XML schema was added and JSON schema for it was produced #666

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
- Updated BP image and dataset JSON schemas for better functionality #664
- Updated XML to JSON converter to parse ISO-8601 duration strings into numbers in BP sample attributes #696

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


[Unreleased]: https://gitlab.ci.csc.fi/sds-dev/sd-submit/metadata-submitter/compare/2026.2.0...HEAD
[2026.2.0]: https://gitlab.ci.csc.fi/sds-dev/sd-submit/metadata-submitter/compare/2025.4.0...2026.2.0
[2025.4.0]: https://gitlab.ci.csc.fi/sds-dev/sd-submit/metadata-submitter/-/compare/2024.1.0...2025.4.0
[2024.01.1]: https://gitlab.ci.csc.fi/sds-dev/sd-submit/metadata-submitter/-/compare/v0.13.1...2024.01.0
[0.13.1]: https://github.com/CSCfi/metadata-submitter/compare/v0.13.0...v0.13.1
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
