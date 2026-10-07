# Sensitive data submission API

## Environmental variables

The sensitive data (SD) workflow is used by the CSC deployment (`DEPLOYMENT=CSC`).

| Variable                    | Description                                                                                                                                                                                                              |
|-----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| DEPLOYMENT                  | Deployment configuration ("CSC", default value "CSC").                                                                                                                                                                   |
| API_PREFIX                  | API root path (default value "").                                                                                                                                                                                        |
| BASE_URL                    | Application base URL. Used to construct the OIDC callback URL (BASE_URL + API_PREFIX + /callback).                                                                                                                       |
| OIDC_URL                    | SD AAI provider URL.                                                                                                                                                                                                     |
| OIDC_CLIENT_ID              | SD AAI client ID.                                                                                                                                                                                                        |
| OIDC_CLIENT_SECRET          | SD AAI client secret.                                                                                                                                                                                                    |
| OIDC_REDIRECT_URL           | URL where the user is redirected after a successful SD AAI login (SD Submit UI).                                                                                                                                         |
| OIDC_SCOPE                  | OIDC scopes (default value "openid profile email").                                                                                                                                                                      |
| OIDC_DPOP                   | Enables DPoP (Demonstration of Proof-of-Possession) for OIDC requests (default value False). Must be set to True for the CSC deployment.                                                                                 |
| JWT_KEY                     | Base64 encoded secret key used to sign and verify the JWT issued by the API after OIDC login.                                                                                                                            |
| JWT_ISSUER                  | Issuer claim of the JWT issued by the API (default value "SD Submit").                                                                                                                                                   |
| JWT_ALGORITHM               | Algorithm used to sign and verify the JWT issued by the API (default value "HS256").                                                                                                                                     |
| CSC_LDAP_HOST               | CSC LDAP URL (ldap:// or ldaps://) used to retrieve the user's CSC projects.                                                                                                                                             |
| CSC_LDAP_USER               | CSC LDAP bind user.                                                                                                                                                                                                      |
| CSC_LDAP_PASSWORD           | CSC LDAP bind password.                                                                                                                                                                                                  |
| KEYSTONE_ENDPOINT           | CSC Pouta Keystone URL. Used to create temporary project scoped EC2 credentials for listing the user's Allas buckets and granting SD Submit read access to them.                                                         |
| S3_ENDPOINT                 | Allas S3 endpoint URL.                                                                                                                                                                                                   |
| S3_REGION                   | Allas S3 region.                                                                                                                                                                                                         |
| STATIC_S3_ACCESS_KEY_ID     | S3 access key ID of the SD Submit service project. Used to read the files in the buckets linked to submissions.                                                                                                          |
| STATIC_S3_SECRET_ACCESS_KEY | S3 secret access key of the SD Submit service project.                                                                                                                                                                   |
| SD_SUBMIT_PROJECT_ID        | OpenStack project ID of the SD Submit service project. Granted read access to the user's bucket using a bucket policy.                                                                                                   |
| CSC_PID_URL                 | CSC PID service URL. Used to register DataCite DOIs.                                                                                                                                                                     |
| CSC_PID_KEY                 | CSC PID service API key.                                                                                                                                                                                                 |
| METAX_URL                   | Metax V3 API URL.                                                                                                                                                                                                        |
| METAX_TOKEN                 | Metax API token.                                                                                                                                                                                                         |
| ROR_URL                     | ROR API URL (e.g., https://api.ror.org/v2). Used to resolve organisations when mapping metadata to Metax.                                                                                                                |
| REMS_URL                    | REMS API URL.                                                                                                                                                                                                            |
| REMS_USER                   | REMS API user.                                                                                                                                                                                                           |
| REMS_KEY                    | REMS API key.                                                                                                                                                                                                            |
| DISCOVERY_URL               | URL used by REMS and DataCite to direct users to the dataset. Must include the placeholder {id}, which is replaced with the Metax ID, or the DOI if there is no Metax ID (e.g., https://etsin.fairdata.fi/dataset/{id}). |
| DATABASE_URL                | Submit API database URL (postgresql+asyncpg://username:password@host:port/database). *1                                                                                                                                  |
| LOG_LEVEL                   | Log level (default value "INFO").                                                                                                                                                                                        |

*1 The database schema is created and upgraded using Alembic migrations (`make db_upgrade`).

### External services

The CSC deployment uses the following external services. All of them must be configured,
otherwise the application fails to start or the related API calls fail.

| Service    | Variables                               | Purpose                                                                                   |
|------------|-----------------------------------------|-------------------------------------------------------------------------------------------|
| SD AAI     | OIDC_*, BASE_URL, JWT_*                 | User login. The API issues its own JWT in a secure cookie after a successful login.       |
| CSC LDAP   | CSC_LDAP_*                              | Retrieving the CSC projects the user is a member of.                                      |
| Keystone   | KEYSTONE_ENDPOINT                       | Temporary EC2 credentials for the user's project to list buckets and set bucket policies. |
| Allas (S3) | S3_*, STATIC_S3_*, SD_SUBMIT_PROJECT_ID | Listing the data files in the bucket linked to the submission.                            |
| CSC PID    | CSC_PID_*                               | Registering and publishing the DataCite DOI.                                              |
| Metax      | METAX_*                                 | Registering and publishing the dataset in Fairdata Metax.                                 |
| ROR        | ROR_URL                                 | Resolving organisation names and identifiers for Metax.                                   |
| REMS       | REMS_*                                  | Creating the REMS resource and catalogue item used to apply for data access.              |

### Allas bucket access

Data files are not uploaded to SD Submit. Instead, the user uploads the files to an Allas
bucket in their own CSC project and links the bucket to the submission. SD Submit reads the
files using the S3 credentials of its own service project (`STATIC_S3_ACCESS_KEY_ID`,
`STATIC_S3_SECRET_ACCESS_KEY`).

To make this possible, `PUT /v1/buckets/{bucket}?projectId=...` adds a bucket policy statement
(`GrantSDSubmitReadAccess`) that grants the `SD_SUBMIT_PROJECT_ID` project read access to the
user's bucket. The policy is set using temporary EC2 credentials created through Keystone with
the user's Pouta access token, which is retrieved from the OIDC userinfo endpoint. The bucket
endpoints therefore require that the user has logged in through the OIDC login, since the
OIDC access token is read from the session cookie.

### Publishing

When a submission is published (`PATCH /v1/publish/{submissionId}`):

1. All files in the linked bucket are added to the submission. At least one file is required.
2. The submission must contain DataCite metadata (`metadata`) and REMS information (`rems`).
3. The submission is registered with external services:
    - A draft DOI is created through CSC PID.
    - A draft dataset is created in Metax.
    - The DOI is published through CSC PID with the `DISCOVERY_URL` as its landing page.
    - The Metax draft is updated with the DataCite metadata.
    - A REMS resource and catalogue item are created and the REMS application URL is added to the Metax description.
    - The Metax dataset is published.
4. The submission is marked as published and can no longer be modified.

The registration identifiers (DOI, Metax ID, REMS IDs) are stored as they are created, so a
failed publish can be retried without creating duplicate registrations.

## Sensitive data submission workflow with SD Submit API

SD Submit API supports the submission of sensitive data (SD) datasets at CSC.

### Submission metadata

Submission metadata is stored in the `submission.json` document. One submission is
conceptually equivalent to one dataset.

Supported metadata standards:

- DataCite V4.5: https://datacite-metadata-schema.readthedocs.io/en/4.5/properties/
- Metax dataset V3: https://metax.fairdata.fi/v3/docs/user-guide/datasets-api/

The `submission.json` document contains the following main fields:

- submissionId: unique id assigned to the dataset.
- projectId: the project that owns the dataset.
- name: project specific unique name for the dataset.
- title: the dataset title.
- description: the dataset description.
- bucket: the bucket associated with the submission
- metadata: DataCite metadata associated with the submission.
- rems: REMS metadata associated with the submission.
- workflow: type of the submission.

### Metax metadata

When a submission is published, a Metax dataset V3 is created and published in Metax.
Most of the Metax fields are mapped from the DataCite metadata (`metadata`) in the
`submission.json` document, but not all of them:

- The title and description are taken from the `title` and `description` fields of the
  `submission.json` document, not from the DataCite metadata. The REMS application link is
  added to the description.
- The persistent identifier is the DOI registered through CSC PID during publishing.
- Organisation identifiers and names are taken from ROR (see [Organisations](#organisations)).
- Some fields are hardcoded: `data_catalog`, `access_rights` and `issued` (the publish date).

The dataset is created and published as follows:

1. A draft dataset is created with the submission `title` and `description`, and the DOI
   registered through CSC PID as the `persistent_identifier`.
2. After the DOI has been published, the draft is updated with the metadata mapped from the
   DataCite metadata, as described below.
3. After the REMS catalogue item has been created, the REMS application link is added to the
   end of the description ("SD Apply Application link: ...").
4. The dataset is published.

Mapping DataCite V4.5 to Metax V3:

| DataCite property                    | DataCite sub-property                                                      | Metax field                | Metax sub-field                                         | Notes                                                                                                                                                                  |
|--------------------------------------|----------------------------------------------------------------------------|----------------------------|---------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| –                                    | –                                                                          | persistent_identifier      | –                                                       | The DOI registered through CSC PID. DataCite `identifiers` are ignored.                                                                                                |
| –                                    | –                                                                          | title                      | –                                                       | The submission `title`. DataCite `titles` are ignored.                                                                                                                 |
| –                                    | –                                                                          | description                | –                                                       | The submission `description` followed by the REMS application link. DataCite `descriptions` are ignored.                                                               |
| creators                             | name, nameIdentifiers, affiliation                                         | actors (role=creator)      | person.name, person.external_identifier, organization   | Only the first nameIdentifier and the first affiliation are used. The affiliation is required.                                                                         |
| contributors                         | name, nameIdentifiers, affiliation                                         | actors (role=contributor)  | person.name, person.external_identifier, organization   | As creators. The contributorType is ignored.                                                                                                                           |
| publisher                            | name                                                                       | actors (role=publisher)    | organization                                            |                                                                                                                                                                        |
| publisher, fundingReferences         | name, funderName, awardNumber                                              | projects                   | participating_organizations, funding                    | The publisher is the participating organization. Each funding reference is a funding with `funder.organization` and `funding_identifier` (from awardNumber).           |
| subjects                             | subject, valueUri                                                          | field_of_science, keyword  | –                                                       | See [Subjects](#subjects). At least one subject is required.                                                                                                           |
| dates (dateType=Other)               | date                                                                       | temporal                   | start_date, end_date                                    | A single date or a date range separated by `/`. See [Dates](#dates). Other date types are ignored.                                                                     |
| geoLocations                         | geoLocationPlace                                                           | spatial                    | geographic_name, reference.url                          | The YSO location URL is looked up by the English place name from `resource/metax/geo_locations.json`.                                                                  |
| geoLocations                         | geoLocationPoint, geoLocationBox, geoLocationPolygon                       | spatial                    | custom_wkt                                              | Converted to WKT `POINT` and `POLYGON`. A polygon is closed if needed. The inPolygonPoint is added as a separate `POINT`.                                               |
| language                             | –                                                                          | language                   | url                                                     | An ISO 639 code (e.g. `en`, `fi`) mapped to a lexvo.org URL using `resource/metax/languages.json`.                                                                     |
| –                                    | –                                                                          | issued                     | –                                                       | The publish date.                                                                                                                                                      |
| –                                    | –                                                                          | data_catalog               | –                                                       | Always `urn:nbn:fi:att:data-catalog-sd`.                                                                                                                               |
| –                                    | –                                                                          | access_rights              | access_type, license, restriction_grounds               | Always `restricted`, `notspecified` and `personal_data` from the `http://uri.suomi.fi/codelist/fairdata/` code lists. DataCite `rightsList` is ignored.                |

DataCite properties not listed above are not sent to Metax. The Metax fields `relation`,
`theme`, `bibliographic_citation`, `provenance` and `remote_resources` are not set.

#### Organisations

Every organisation (creator and contributor affiliations, the publisher and funders) is looked
up from ROR (`ROR_URL`) by its name. The organisation identifier and name in the
`submission.json` document are replaced with the ROR identifier and preferred name. Publishing
fails if the organisation name is not found in ROR.

#### Subjects

Each subject is matched to a Metax field of science
(`<METAX_URL>/reference-data/fields-of-science`) using, in order:

1. the `valueUri` or the `subject` as a field of science URL
   (e.g. `http://www.yso.fi/onto/okm-tieteenala/ta111`),
2. the `subject` as a field of science code (e.g. `ta111` or `111`),
3. the `subject` as a field of science label (e.g. `Mathematics`),
4. the `subject` as `<code> - <label>` (e.g. `111 - Mathematics`).

A matched subject is added as a `field_of_science` and its label as a `keyword`. Other
subjects are added as a `keyword`. Metax requires at least one keyword.

#### Dates

Metax dates are in `YYYY-MM-DD` format. DataCite dates are converted as follows:
`YYYY` becomes `YYYY-01-01`, `YYYY-MM` becomes `YYYY-MM-01`, and ISO 8601 date times
are truncated to the date. Other formats fail publishing.

### Submission workflow

SD Submit is normally used through the SD Submit UI. The API can also be used from the command
line with an API key created after logging in:

```bash
# Set the API url as env variable
export API_URL="..."

# Create an API key in a browser session after logging in through $API_URL/login,
# or with an existing JWT, and use it as the bearer token in subsequent calls:
export TOKEN="..."

# Ensure the API recognizes the user and list the user's projects:
curl --request GET "$API_URL/v1/users" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### Create a new submission

Create a submission in one of the user's projects using a `submission.json` document. An
example document is available in `tests/test_files/submission/submission.json`:

```bash
export PROJECT_ID="..."

export SUBMISSION_ID=$(jq --arg projectId "$PROJECT_ID" '. + {projectId: $projectId}' \
     ./tests/test_files/submission/submission.json | \
     curl --request POST "$API_URL/v1/submissions" \
     --header "Authorization: Bearer $TOKEN" \
     --header "Content-Type: application/json" \
     --data @- | jq -r '.submissionId')
```

#### Update the submission

Update the submission document. Only the provided fields are changed:

```bash
curl --request PATCH "$API_URL/v1/submissions/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN" \
     --header "Content-Type: application/json" \
     --data '{"description": "Updated description"}' | jq
```

#### Link a bucket to the submission

Grant SD Submit read access to the bucket and link it to the submission. Granting access
requires a browser session, see [Allas bucket access](#allas-bucket-access):

```bash
export BUCKET="..."

# Read access is granted to SD Submit with PUT /v1/buckets/{bucket}?projectId=...
# This can only be called using a browser login session. It requires the OIDC access
# token from the session cookie set by $API_URL/login to create temporary Keystone
# credentials for the project.

# Check that SD Submit has been granted read access to the bucket.
# Returns 200 if access has been granted and 403 otherwise.
curl --head "$API_URL/v1/buckets/$BUCKET?projectId=$PROJECT_ID" \
     --header "Authorization: Bearer $TOKEN"

# Link the bucket to the submission. The bucket can't be changed once it has been linked.
curl --request PATCH "$API_URL/v1/submissions/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN" \
     --header "Content-Type: application/json" \
     --data "{\"bucket\": \"$BUCKET\"}" | jq

# List the files in the bucket.
curl --request GET "$API_URL/v1/buckets/$BUCKET/files?projectId=$PROJECT_ID" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### Inspect the submission

```bash
# Get the submission document. Returns the submission.json including the linked bucket.
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### Publish the submission

```bash
curl --request PATCH "$API_URL/v1/publish/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN" | jq

# List the DOI, Metax and REMS registrations.
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/registrations" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### Delete the submission

An unpublished submission can be deleted:

```bash
curl --request DELETE "$API_URL/v1/submissions/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN"
```
