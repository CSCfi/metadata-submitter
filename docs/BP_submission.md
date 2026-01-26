## Bigpicture Submission Workflow with SD Submit API

SD Submit API supports the submission of Bigpicture datasets.

This document explains the main dataset submission steps and how to
execute them from the command line. SD Submit for BigPicture currently
does not provide a UI or a dedicated CLI, so HTTP requests must be issued using a tool
such as [cURL](https://curl.se/).

The document lists the required curl commands for the submission process and briefly
describes the purpose of each one. Detailed API specifications, including example JSON
responses for all referenced HTTP requests, are available in the OpenAPI specification
[OpenAPI specifications](openapi.yml).

> **Note:** `curl` commands below include the additional `jq` command to
> prettify the JSON response in the terminal. The `| jq` part can be
> omitted from each command if it's not installed or needed in general.

### 1. Authenticate to the SD Submit API

Start by creating an environment variable in a bash terminal session for the API URL:

```bash
# Enter the API url inside the quotes
export API_URL="..."

# If you have deployed the API locally for testing, set this as:
export API_URL="http://localhost:5431"
```

Authenticate to the API via an OIDC Client.
Get the login url with below command:

```bash
curl --request GET $API_URL/login
```

Use curl -L command to get the JWT session token (or simply paste the login url in a web browser):

```bash
curl -L "..."
```

A JWT will be printed in the terminal or browser window. Copy it and use it for suqsequent API calls in the authorization header:

```bash
# Set the JWT as env variable
export TOKEN="..."

# Ensure login has completed by getting user info
curl --request GET $API_URL/v1/users \
     --header "authorization: Bearer $TOKEN" | jq
```

**Optional:**
A reusable API keys for the service can be created after the original OIDC authentication with the following command.
This key can then be used as a bearer token instead of the JWT in the authorization header:

```bash
curl --request POST $API_URL/v1/api/keys \
     --header "authorization: Bearer $TOKEN" \
     --data '{"key_id": "test api key"}'

# The created API key with the specified key_id will be printed in the terminal

# Replace the TOKEN env variable with the API key
export TOKEN="..."
```

### 2. Create a new submission entity

Start the submission process by creating a new submission. The submission will require all metadata related to the dataset.

#### Submit a new Bigpicture dataset with metadata files

Create a new submission by uploading all required metadata XML files with the following command. The command in this document refers to a set of test XML files available in this repository:

```bash
export SUBMISSION_ID=$(curl --request POST "$API_URL/v1/submit/Bigpicture" \
     --header "Authorization: Bearer $TOKEN" \
     --form "annotation=@./tests/test_files/xml/bigpicture/annotation.xml;type=text/xml" \
     --form "datacite=@./tests/test_files/xml/bigpicture/datacite.xml;type=text/xml" \
     --form "dataset=@./tests/test_files/xml/bigpicture/dataset.xml;type=text/xml" \
     --form "image=@./tests/test_files/xml/bigpicture/image.xml;type=text/xml" \
     --form "landing_page=@./tests/test_files/xml/bigpicture/landing_page.xml;type=text/xml" \
     --form "observation=@./tests/test_files/xml/bigpicture/observation.xml;type=text/xml" \
     --form "observer=@./tests/test_files/xml/bigpicture/observer.xml;type=text/xml" \
     --form "organisation=@./tests/test_files/xml/bigpicture/organisation.xml;type=text/xml" \
     --form "policy=@./tests/test_files/xml/bigpicture/policy.xml;type=text/xml" \
     --form "bprems=@./tests/test_files/xml/bigpicture/rems.xml;type=text/xml" \
     --form "sample=@./tests/test_files/xml/bigpicture/sample.xml;type=text/xml" \
     --form "staining=@./tests/test_files/xml/bigpicture/staining.xml;type=text/xml" | jq -r '.submissionId')
```

All XML files are validated and then added to the submission entity.
The `SUBMISSION_ID` environment variable is automatically extracted from the response to be used in subsequent API calls.

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

For other schema types, replace the schema type in the url parameter (`schemaType=<HERE>`) with any of the available schema types:
- `annotation`
- `landingpage`
- `observation`
- `observer`
- `organisation`
- `policy`
- `rems`
- `sample`
- `staining`

### 4. Update submission metadata

You can update an existing dataset submission by uploading modified XML files with the following command.
For example, to update the image metadata file:

```bash
curl --request PATCH "$API_URL/v1/submit/Bigpicture/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN" \
     --form "image=@./tests/test_files/xml/bigpicture/update/image.xml;type=text/xml" \
     --form "annotation=@./tests/test_files/xml/bigpicture/annotation.xml;type=text/xml" \
     --form "datacite=@./tests/test_files/xml/bigpicture/datacite.xml;type=text/xml" \
     --form "dataset=@./tests/test_files/xml/bigpicture/dataset.xml;type=text/xml" \
     --form "landing_page=@./tests/test_files/xml/bigpicture/landing_page.xml;type=text/xml" \
     --form "observation=@./tests/test_files/xml/bigpicture/observation.xml;type=text/xml" \
     --form "observer=@./tests/test_files/xml/bigpicture/observer.xml;type=text/xml" \
     --form "organisation=@./tests/test_files/xml/bigpicture/organisation.xml;type=text/xml" \
     --form "policy=@./tests/test_files/xml/bigpicture/policy.xml;type=text/xml" \
     --form "bprems=@./tests/test_files/xml/bigpicture/rems.xml;type=text/xml" \
     --form "sample=@./tests/test_files/xml/bigpicture/sample.xml;type=text/xml" \
     --form "staining=@./tests/test_files/xml/bigpicture/staining.xml;type=text/xml" | jq
```

**Note:** The submission update API call requires all necessary metadata XML files to be uploaded in the same call even if they have not been altered.


If you need to remove a submission entirely, you can delete it using the submission ID:

```bash
curl --request DELETE "$API_URL/v1/submit/Bigpicture/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN"
```

**Warning:** This action is permanent and cannot be undone. Make sure you have the correct submission ID before executing this command.
