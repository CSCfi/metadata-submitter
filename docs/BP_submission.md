## BigPicture Submission Workflow with SD Submit API

SD Submit is a service that will support several use-cases including
the submission of BigPicture datasets. The project currently includes
an API solution developed and maintained in this repository, which
enables programmatic submission of these datasets.

The flowchart below depicts the steps for the programmatic submission
process. Each step is explained below in this markdown document with
instructions on how to execute them via the command line.

![BigPicture Submission flowchart](_static/bp-flowchart.svg)

### Further context

SD Submit service utilizes an instance of MongoDB as its database. As a
result of this, all information is mainly stored as JSON documents and
thus, HTTP requests primarily respond with some JSON content. Despite this,
XML content is also stored and XML content can be fetched via this API
(shown below).

There are many tools for convenient creation of HTTP requests to a web
service e.g. [Postman](https://www.postman.com/) or [REST Client Extension
for Visual Studio Code](https://github.com/Huachao/vscode-restclient),
which could be used for the purpose of programmatic submissions. In fact,
this repository also contains [this document](../tests/http/publication_bp.http)
for executing all of the same API calls with the REST Client extension,
which are listed below in this markdown document.

However, these instructions aim to assist with using the SD Submit API
for programmatic submissions specifically via the command line. The project
currently does not come with a built-in CLI so HTTP requests need to be
handled with a tool such as [cURL](https://curl.se/). Hence, this markdown
document lists the specific `curl` commands required for the dataset submission
process and briefly explains what each of them achieve. For more detailed
API specifications that include examples of JSON responses for any of the
HTTP requests listed below, see the project [OpenAPI specifications](openapi.yml).

> **Note:** `curl` commands below include the additional `jq` command to
prettify the JSON response in the terminal. Thus, the `| jq` part can be
omitted from each command if it's not installed or needed in general.


### 1. Authenticate to SD Submit

Start by creating an environment variable in a bash terminal session for the API URL:

```bash
# Enter the API url inside the quotes
export API_URL="..."

# If you have deployed the SD Submit API
# locally for testing, set this as:
export API_URL="http://localhost:5430"
```

Fetch session cookie from the server, which will be used for **all subsequent** API calls:

```bash
# Send request to AAI service
session_cookie=$(curl -s -L -D - $API_URL/aai \
    | grep 'Set-Cookie: AIOHTTP_SESSION' \
    | sed 's/Set-Cookie: \(AIOHTTP_SESSION=[^;]*\).*/\1/')
```

You can then inspect the stored user data in the terminal:

```bash
# Get user JSON object
curl -H "Cookie: $session_cookie" \
     -X GET $API_URL/v1/users/current | jq
```

The `userId` and `projectId` values found in the JSON object of the
previous response will be used in subsequent API request query strings
and JSON payloads. They can be stored as bash environment variables
for convenience with following commands:

```bash
# Get user ID
user_id=$(curl -H "Cookie: $session_cookie" \
    -s $API_URL/v1/users/current \
    | jq -r '.userId')

# Get project ID
project_id=$(curl -H "Cookie: $session_cookie" \
    -s $API_URL/v1/users/current \
    | jq -r '.projects[0].projectId')

# The above assumes the user is part of a single project.
# Choose another project from the project list by changing the "projects[0]" index value.
```

> **Note:** The `project` concept used for user access in SD Submit
will include Perun groups in the future.

### 2. Create a new submission entity

Start the submission process by creating a new submission:

```bash
# Assign the submission a name and a description
# next to their respective keys below
curl -H "Cookie: $session_cookie" \
     -X POST "$API_URL/v1/submissions" \
     --json '{
       "name": "<ENTER NAME HERE>",
       "description": "<ENTER DESCRIPTION HERE>",
       "projectId": "'$project_id'",
       "workflow": "BigPicture"
     }' | jq
```

The resulting `submissionId` value of the submission object can again
be stored as environment variable for convenience like this:

```bash
# Get submission ID
submission_id=$(curl -H "Cookie: $session_cookie" \
    -X GET $API_URL/v1/submissions?projectId=$project_id \
    | jq -r '.submissions[0].submissionId')
```

The submission is formed as a JSON object, which will include all required
information about a dataset. Its content can be viewed with the following command:

```bash
# Get submission object
curl -H "Cookie: $session_cookie" \
     -X GET $API_URL/v1/submissions/$submission_id | jq
```

> **Note:** All users who belong to the same project can view and
edit this same submission with the instructions below.
Thus, submission can be filled out by multiple users.

### 3. a) Add metadata to the submission

SD Submit API can receive XML files directly and link the metadata
to the submission with the following commands:

```bash
# Name the schema of the XML file as an env variable. Options are:
# "bpdataset", "bpsample", "bpimage", "bpstaining" or "bpobservation"
export schema_type="bpdataset"

# Determine the path to the XML file as an env variable
export file_path="path/to/file/dataset.xml"

# Add metadata to submission
curl -H "Cookie: $session_cookie" \
     -F "$schema_type=@$file_path" \
     -X POST "$API_URL/v1/objects/$schema_type?submission=$submission_id" \
     | jq

# If the XML content is not formatted correctly or according to the correct schema,
# you will receive an error response
```

Notice that the response will include a newly generated unique internal
**accession ID** for this metadata object (or a list of multiple IDs,
if the file includes a set of multiple metadata items e.g. for images).
The object accession IDs can be re-read from the submission object within
the list of metadata objects.

You can inspect the entire metadata object that was stored in the database
with the following commands by replacing `{accession_id_here}` with the
specific `accessionId` value:

```bash
# Get metadata item (returns it in JSON format)
curl -H "Cookie: $session_cookie" \
     -X GET $API_URL/v1/objects/$schema_type/{accession_id_here} | jq

# Get metadata item (returns the XML content)
curl -H "Cookie: $session_cookie" \
     -X GET $API_URL/v1/objects/$schema_type/{accession_id_here}?format=xml
```

> **Note:** Datacite DOI and REMS information will be filled out in a similar
manner in the future (after version 2.0.0 of metadata schemas is released)

### 3. b) Edit already submitted metadata

The metadata items added to the submission previously can be replaced
with a modified XML file, while retaining the same accession ID,
or deleted entirely. This can be done with the following commands:

```bash
# Set environment variables accordingly
export schema_type="bpdataset"
export file_path="path/to/file/dataset.xml"
export accession_id="some uuid"

# Replace the metadata item with a specific accession ID
curl -H "Cookie: $session_cookie" \
     -F "$schema_type=@$file_path" \
     -X PUT "$API_URL/v1/objects/$schema_type/$accession_id" \
     | jq

# Delete the metadata item with a specific accession ID
curl -H "Cookie: $session_cookie" \
     -X DELETE "$API_URL/v1/objects/$schema_type/$accession_id"
```

To review the metadata items again or the submission object, see the commands used in previous steps.

### 4. Adding files to submission

Currently, SD Submit API needs to receive information about the files
that will be included in the submission. This means gathering and
sending a JSON blob, which should minimally look like this
(but more files can be added to the `files` array to send at once):

```json
{
    "userId": "submitter's user id",
    "projectId": "submitter's project id",
    "files": [
        {
            "name": "file_name",
            "path": "s3:/path/to/file_name",
            "bytes": 100,
            "encrypted_checksums": [
                {
                "type": "sha256",
                "value": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
                }
            ],
            "unencrypted_checksums": [
                {
                "type": "sha256",
                "value": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
                }
            ]
        }
    ]
}
```

It may be easiest to write and store the above as a JSON file locally.
It can then be sent over with the following command:

```bash
# Send information about file(s)
curl -H "Cookie: $session_cookie" \
     -X POST "$API_URL/v1/files" \
     --json @file_payload.json | jq
```

The list of files will be stored for each project group and it can be viewed with:
```bash
# Get list of files in a project
curl -H "Cookie: $session_cookie" \
     -X GET "$API_URL/v1/files?projectId=$project_id" | jq
```

From the above commands, you can gain the accession ID of the file object
for the next part. The file can then be added to the submission and linked
with a specific metadata object with the following command:

```bash
# Add file(s) to the submission
curl -H "Cookie: $session_cookie" \
     -X PATCH "$API_URL/v1/submissions/$submission_id/files" \
     --json '[
         {
             "accessionId": "<ENTER FILE ACCESSION ID>",
             "version": 1,
             "objectId": {
                 "accessionId": "<ENTER METADATA ACCESSION ID>",
                 "schema": "<ENTER SCHEMA NAME>"
             }
         }
     ]' | jq
```

The list of submission files can then be seen in the submission object.
All files in the submission should be linked to some metadata objects
before moving to next steps.

### 5. Begin ingestion of files

> **Note:** This section of the API is yet to be implemented and is currently under development.

Once the user is finished compiling the files and its metadata into the
same submission, the data ingestion pipeline can be initiated followingly:

```bash
# Initiate the data ingestion
curl -H "Cookie: $session_cookie" \
     -X POST "$API_URL/v1/submissions/$submission_id/ingest" | jq
```

After this, SD Submit service will continuously poll the
[Admin API](https://github.com/neicnordic/sensitive-data-archive/blob/main/sda/cmd/api/api.md)
in the background and update the status of each file linked to the submission.
To proceed to the next part, the file ingestion needs to be finalized in the
pipeline and statuses need to be marked as `completed` in the submission object.
This can be checked by getting the submission object.

### 6. Announce the completed submission

```bash
# Announce the submission to be published
curl -H "Cookie: $session_cookie" \
     -X PATCH "$API_URL/v1/announce/$submission_id" | jq
```

After this, the dataset described in the submission object will be registered
to DataCite, made accessible via the REMS service and discoverable by
BigPicture Imaging Beacon discovery service. The submission object can still be
viewed via the API but it can no longer be edited with previously covered commands.
