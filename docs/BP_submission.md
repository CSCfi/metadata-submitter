# Bigpicture submission API

## Environmental variables

| Variable                  | Description                                                                                                                                                                                                                                                                        |
|---------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| DEPLOYMENT                | Deployment configuration ("NBIS").                                                                                                                                                                                                                                                 |
| API_PREFIX                | API root path (default value "").                                                                                                                                                                                                                                                  |
| SERVER_PORT               | Port the server listens on (default value "5431").                                                                                                                                                                                                                                 |
| BP_CENTER_ID              | Center ID used in Bigpicture IDs assigned by the API.                                                                                                                                                                                                                              |
| IMPORT_USERS              | JSON array of the ids of the users allowed to import existing datasets. See docs/BP_import.md.                                                                                                                                                                                     |
| S3_ENDPOINT               | Bigpicture Inbox S3 bucket.                                                                                                                                                                                                                                                        |
| S3_REGION                 | Bigpicture Inbox S3 bucket region.                                                                                                                                                                                                                                                 |
| CRYPT4GH_PUBLIC_KEY       | Base64 encoded PEM public Crypt4GH key for encrypting metadata objects written out after publish. Alternative to CRYPT4GH_PUBLIC_KEY_URL. Does not support key rotation.                                                                                                           |
| CRYPT4GH_PUBLIC_KEY_URL   | URL providing the PEM public Crypt4GH key for encrypting metadata objects written out after publish. Cached for one hour. Supports key rotation.                                                                                                                                   |
| OPENBAO_URL               | OpenBao server URL. Metadata objects stored in the database are encrypted using OpenBao when this is defined.                                                                                                                                                                      |
| OPENBAO_TOKEN             | OpenBao token. Alternative to OPENBAO_KUBERNETES_ROLE.                                                                                                                                                                                                                             |
| OPENBAO_KUBERNETES_ROLE   | OpenBao role for Kubernetes service account authentication. The service account token is exchanged for an OpenBao token. Alternative to OPENBAO_TOKEN.                                                                                                                             |
| OPENBAO_KUBERNETES_MOUNT  | OpenBao Kubernetes authentication method mount path (default value "kubernetes").                                                                                                                                                                                                  |
| OPENBAO_OBJECT_KEY_NAME   | OpenBao encryption key used to encrypt the metadata objects stored in the database. Required when OPENBAO_URL is defined.                                                                                                                                                          |
| OPENBAO_OBJECT_ENCRYPTION | Encryption method used for metadata objects stored in the database. "envelope" (default): metadata objects are encrypted with data encryption keys created for the provided key encryption key. "direct": metadata object are directly encrypted with the provided symmetric key.  |
| ADMIN_URL                 | NeIC SDA Admin API URL.                                                                                                                                                                                                                                                            |
| ADMIN_TOKEN               | NeIC SDA Admin API token.                                                                                                                                                                                                                                                          |
| JWT_ISSUER                | User's JWT token issuer.                                                                                                                                                                                                                                                           |
| JWT_ALGORITHM             | Algorithm used to sign and verify user's JWT.                                                                                                                                                                                                                                      |
| JWT_KEY                   | Public key used to verify the user's JWT signature.                                                                                                                                                                                                                                |
| DATABASE_URL              | Submit API database URL (postgresql+asyncpg:://username:password@host:port/database). *1                                                                                                                                                                                           |
| DATABASE_MIGRATE          | Apply database migrations when the server starts (true/false, default false). *1                                                                                                                                                                                                   |
| DISCOVERY_URL             | URL used by REMS and DataCite to direct users to the dataset. Must include the placeholder {id}, which is replaced with the dataset ID (e.g., https://datasets.bp.nbis.se/datasets/{id}.html).                                                                                     |
| DATACITE_API              | DataCite API URL.                                                                                                                                                                                                                                                                  |
| DATACITE_USER             | DataCite user.                                                                                                                                                                                                                                                                     |
| DATACITE_KEY              | DataCite key                                                                                                                                                                                                                                                                       |
| DATACITE_DOI_PREFIX       | DataCite DOI prefix.                                                                                                                                                                                                                                                               |
| REMS_URL                  | REMS API URL.                                                                                                                                                                                                                                                                      |
| REMS_USER                 | REMS API user.                                                                                                                                                                                                                                                                     |
| REMS_KEY                  | REMS API key.                                                                                                                                                                                                                                                                      |
| SYNC_CLIENTS              | Clients allowed to sync published submissions. See docs/BP_sync.md.                                                                                                                                                                                                                |
| SYNC_AUDIENCE             | Audience of the JWT tokens for syncing published submissions.                                                                                                                                                                                                                      |

*1 The database schema is automatically created if it does not already exist or it can
be created by executing the SQL statements in metadata_backend/database/postgres/schema/create.sql.
An existing database is upgraded with the Alembic migrations, either when the server starts with
DATABASE_MIGRATE=true or with `make db_upgrade`.

## Bigpicture Submission Workflow with SD Submit API

SD Submit API supports the submission of Bigpicture datasets.

This document explains the main dataset submission steps and how to
execute them from the command line. SD Submit for Bigpicture currently
does not provide a UI or a dedicated CLI, so HTTP requests must be issued using a tool
such as [cURL](https://curl.se/).

The document lists the required curl commands for the submission process and briefly
describes the purpose of each one. Detailed API specifications, including example JSON
responses for all referenced HTTP requests, are available in the OpenAPI specification
accessible from the root of the installed application.

> **Note:** `curl` commands below include the additional `jq` command to
> prettify the JSON response in the terminal. The `| jq` part can be
> omitted from each command if it's not installed or needed in general.

### 1. Authenticate to the SD Submit API

Go to the [Bigpicture login portal](https://login.bp.nbis.se) and complete OIDC authentication.

Then copy the same access token as _"For **uploading** to the Inbox"_ use it for all
suqsequent API calls in the authorization header:

```bash
# Set the JWT as env variable
export TOKEN="..."

# Set the API url as env variable
export API_URL="..."

# If you have deployed the API locally for testing, set this as:
export API_URL="http://localhost:5431"

# Ensure the API recognizes the user based on the access token with:
curl --request GET $API_URL/v1/users \
     --header "authorization: Bearer $TOKEN" | jq
```

### 2. Create a new submission entity

Start the submission process by creating a new submission. The submission will require all metadata related to the
dataset.

#### Submit a new Bigpicture dataset with metadata files

Create a new submission by uploading metadata XML files using the POST `submit` command. The examples below refer to
example XML files provided in this repository for both metadata standard versions 2.0 and 3.0.

The metadata version is read from the `METADATA_STANDARD` element of the dataset XML, and all XML files in one
submission must follow the XML schemas of that version. The metadata standard version 3.0 adds three new metadata
files: `annotator.xml`, `annotation_task.xml` and `ontology.xml`.

Example for the metadata standard version 2.0:

```bash
export SUBMISSION_ID=$(curl --request POST "$API_URL/v1/submit" \
     --header "Authorization: Bearer $TOKEN" \
     --form "annotation=@./tests/test_files/xml/bigpicture/2.0/annotation.xml;type=text/xml" \
     --form "datacite=@./tests/test_files/xml/bigpicture/2.0/datacite.xml;type=text/xml" \
     --form "dataset=@./tests/test_files/xml/bigpicture/2.0/dataset.xml;type=text/xml" \
     --form "image=@./tests/test_files/xml/bigpicture/2.0/image.xml;type=text/xml" \
     --form "landing_page=@./tests/test_files/xml/bigpicture/2.0/landing_page.xml;type=text/xml" \
     --form "observation=@./tests/test_files/xml/bigpicture/2.0/observation.xml;type=text/xml" \
     --form "observer=@./tests/test_files/xml/bigpicture/2.0/observer.xml;type=text/xml" \
     --form "organisation=@./tests/test_files/xml/bigpicture/2.0/organisation.xml;type=text/xml" \
     --form "policy=@./tests/test_files/xml/bigpicture/2.0/policy.xml;type=text/xml" \
     --form "bprems=@./tests/test_files/xml/bigpicture/2.0/rems.xml;type=text/xml" \
     --form "sample=@./tests/test_files/xml/bigpicture/2.0/sample.xml;type=text/xml" \
     --form "staining=@./tests/test_files/xml/bigpicture/2.0/staining.xml;type=text/xml" | jq -r '.submissionId')
```

Example for the metadata standard version 3.0:

```bash
export SUBMISSION_ID=$(curl --request POST "$API_URL/v1/submit" \
     --header "Authorization: Bearer $TOKEN" \
     --form "annotation=@./tests/test_files/xml/bigpicture/3.0/annotation.xml;type=text/xml" \
     --form "annotation_task=@./tests/test_files/xml/bigpicture/3.0/annotation_task.xml;type=text/xml" \
     --form "annotator=@./tests/test_files/xml/bigpicture/3.0/annotator.xml;type=text/xml" \
     --form "datacite=@./tests/test_files/xml/bigpicture/3.0/datacite.xml;type=text/xml" \
     --form "dataset=@./tests/test_files/xml/bigpicture/3.0/dataset.xml;type=text/xml" \
     --form "image=@./tests/test_files/xml/bigpicture/3.0/image.xml;type=text/xml" \
     --form "landing_page=@./tests/test_files/xml/bigpicture/3.0/landing_page.xml;type=text/xml" \
     --form "observation=@./tests/test_files/xml/bigpicture/3.0/observation.xml;type=text/xml" \
     --form "observer=@./tests/test_files/xml/bigpicture/3.0/observer.xml;type=text/xml" \
     --form "ontology=@./tests/test_files/xml/bigpicture/3.0/ontology.xml;type=text/xml" \
     --form "organisation=@./tests/test_files/xml/bigpicture/3.0/organisation.xml;type=text/xml" \
     --form "policy=@./tests/test_files/xml/bigpicture/3.0/policy.xml;type=text/xml" \
     --form "bprems=@./tests/test_files/xml/bigpicture/3.0/rems.xml;type=text/xml" \
     --form "sample=@./tests/test_files/xml/bigpicture/3.0/sample.xml;type=text/xml" \
     --form "staining=@./tests/test_files/xml/bigpicture/3.0/staining.xml;type=text/xml" | jq -r '.submissionId')
```

All XML files are validated and then added to the submission entity.
The `SUBMISSION_ID` environment variable is automatically extracted from the response to be used in subsequent API
calls.

### 3. Inspect the submission

After creating a submission, you can retrieve its details to verify the submission status and metadata.

#### Get submission by ID

Retrieve full details about a specific submission:

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### List metadata objects in the submission

Retrieve a list of metadata objects that have been linked to the submission based on the uploaded XML files.
The output will display all metadata accession IDs:

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/objects" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### List files in the submission

Retrieve a list of files that have been linked to the submission. The file list is parsed from the uploaded XML files.

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/files" \
     --header "Authorization: Bearer $TOKEN"
```

#### List all submissions

You can retrieve a list of all submissions you have made:

```bash
curl --request GET "$API_URL/v1/submissions" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### 4. Retrieve individual XML files

You can retrieve individual XML files from your submission by specifying the schema type.
The returned XML content have been modified to include a new accession ID:

#### Get dataset XML

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/objects/docs?schemaType=dataset" \
     --header "Authorization: Bearer $TOKEN"
```

#### Get image XML

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/objects/docs?schemaType=image" \
     --header "Authorization: Bearer $TOKEN"
```

**Other available XML files**

For other schema types, replace the schema type in the url parameter (`schemaType=<HERE>`) with any of the available
schema types:

- `annotation`
- `annotation_task` (since 3.0)
- `annotator` (since 3.0)
- `landing_page`
- `observation`
- `observer`
- `ontology` (since 3.0)
- `organisation`
- `policy`
- `rems`
- `sample`
- `staining`

### 4. Update submission metadata

You can update an existing dataset submission by uploading modified XML files with the PATCH `submit` command.

For example, to update the image metadata file in a metadata standard version 2.0 submission:

```bash
curl --request PATCH "$API_URL/v1/submit/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN" \
     --form "image=@./tests/test_files/xml/bigpicture/2.0/update/image.xml;type=text/xml" \
     --form "annotation=@./tests/test_files/xml/bigpicture/2.0/annotation.xml;type=text/xml" \
     --form "datacite=@./tests/test_files/xml/bigpicture/2.0/datacite.xml;type=text/xml" \
     --form "dataset=@./tests/test_files/xml/bigpicture/2.0/dataset.xml;type=text/xml" \
     --form "landing_page=@./tests/test_files/xml/bigpicture/2.0/landing_page.xml;type=text/xml" \
     --form "observation=@./tests/test_files/xml/bigpicture/2.0/observation.xml;type=text/xml" \
     --form "observer=@./tests/test_files/xml/bigpicture/2.0/observer.xml;type=text/xml" \
     --form "organisation=@./tests/test_files/xml/bigpicture/2.0/organisation.xml;type=text/xml" \
     --form "policy=@./tests/test_files/xml/bigpicture/2.0/policy.xml;type=text/xml" \
     --form "bprems=@./tests/test_files/xml/bigpicture/2.0/rems.xml;type=text/xml" \
     --form "sample=@./tests/test_files/xml/bigpicture/2.0/sample.xml;type=text/xml" \
     --form "staining=@./tests/test_files/xml/bigpicture/2.0/staining.xml;type=text/xml" | jq
```

**Note:** The submission update API call requires all necessary metadata XML files to be uploaded in the same call even
if they have not been altered.

**Note:** The metadata version of a submission cannot be changed. To move a submission to another version before
publishing it, delete the submission as shown below and submit it again.

If you need to remove a submission entirely, you can delete it using the DELETE `submit` command:

```bash
curl --request DELETE "$API_URL/v1/submit/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN"
```

**Warning:** This action is permanent and cannot be undone. Make sure you have the correct submission ID before
executing this command.
