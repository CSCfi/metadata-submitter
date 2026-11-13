# Bigpicture submission API

## Bigpicture Submission Workflow with SD Submit API

SD Submit API supports the submission of Bigpicture datasets.

This document explains the main dataset submission steps and how to
execute them from the command line. SD Submit for Bigpicture currently
does not provide a UI nor a dedicated CLI, so HTTP requests must be issued using a tool
such as [cURL](https://curl.se/).

The document lists the required curl commands for the submission process and briefly
describes the purpose of each one. Detailed API specifications, including example JSON
responses for all referenced HTTP requests, are available in the OpenAPI specification
accessible from the root of the installed application.

A submission goes through these steps:

1. Authenticate to the SD Submit API.
2. Create a submission by uploading the metadata XML files. The submission ID returned is the
   dataset's accession ID.
3. Inspect the submission.
4. Update the submission if needed.
5. Upload the encrypted data files to the Bigpicture Inbox under the submission's directory.
6. Publish the submission.

To bring a dataset that is already archived in SDA into SD Submit, see
[BP_import.md](BP_import.md) instead.

> **Note:** `curl` commands below include the additional `jq` command to
> prettify the JSON response in the terminal. The `| jq` part can be
> omitted from each command if it's not installed or needed in general.

### 1. Authenticate to the SD Submit API

Go to the [Bigpicture login portal](https://login.bp.nbis.se) and complete OIDC authentication.

Then copy the access token shown _"For **uploading** to the Inbox"_ and use it for all
subsequent API calls in the authorization header. The same token is needed when publishing,
since the API then uploads the metadata files to your Inbox on your behalf.

```bash
# Set the JWT as env variable
export TOKEN="..."

# Set the API url as env variable
export API_URL="..."

# If you have deployed the API locally for testing, set this as:
export API_URL="http://localhost:5431"

# Ensure the API recognizes the user based on the access token with:
curl --request GET "$API_URL/v1/users" \
     --header "Authorization: Bearer $TOKEN" | jq
```

### 2. Create a new submission entity

Start the submission process by creating a new submission. The submission will require all metadata related to the
dataset.

#### Submit a new Bigpicture dataset with metadata files

Create a new submission by uploading metadata XML files using the POST `submit` command. The examples below refer to
example XML files provided in this repository for both metadata standard versions 2.0 and 3.0.
The metadata version is read from the `METADATA_STANDARD` element of the dataset XML, and all XML files in one
submission must follow the XML schemas of that version.

Each XML file is recognised by its **file name**, so the uploaded files must be named exactly
`annotation.xml`, `annotation_task.xml`, `annotator.xml`, `datacite.xml`, `dataset.xml`, `image.xml`,
`landing_page.xml`, `observation.xml`, `observer.xml`, `ontology.xml`, `organisation.xml`, `policy.xml`,
`rems.xml`, `sample.xml` and `staining.xml`. Each file may be given only once. The form field names
are not used.

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
     --form "rems=@./tests/test_files/xml/bigpicture/2.0/rems.xml;type=text/xml" \
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
     --form "rems=@./tests/test_files/xml/bigpicture/3.0/rems.xml;type=text/xml" \
     --form "sample=@./tests/test_files/xml/bigpicture/3.0/sample.xml;type=text/xml" \
     --form "staining=@./tests/test_files/xml/bigpicture/3.0/staining.xml;type=text/xml" | jq -r '.submissionId')
```

All XML files are validated and then added to the submission entity. Every metadata object is
assigned an accession ID, and the dataset's accession ID becomes the submission ID.
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

Retrieve a list of data files that have been linked to the submission. The file list is parsed from the
uploaded XML files, and each `path` is where the file is expected in the Inbox (see
[step 5](#5-upload-the-data-files-to-the-inbox)).

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/files" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### List all submissions

You can retrieve a list of all submissions you have made. The list is paginated: use `page` (from 1) and
`per_page` (default 5, at most 100) to see more. It can be filtered with, for example, `published=true` or
`published=false`.

```bash
curl --request GET "$API_URL/v1/submissions?page=1&per_page=20" \
     --header "Authorization: Bearer $TOKEN" | jq
```

#### Retrieve individual XML files

You can retrieve individual XML files from your submission by specifying the schema type.
The returned XML content has been modified to include the assigned accession IDs.

Get the dataset XML:

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/objects/docs?schemaType=dataset" \
     --header "Authorization: Bearer $TOKEN"
```

Get the image XML:

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/objects/docs?schemaType=image" \
     --header "Authorization: Bearer $TOKEN"
```

For other schema types, replace the schema type in the url parameter (`schemaType=<HERE>`) with any of the available
schema types:

- `annotation`
- `annotation_task` (since 3.0)
- `annotator` (since 3.0)
- `datacite`
- `dataset`
- `image`
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

You can update an unpublished submission by uploading modified XML files with the PATCH `submit` command.

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
     --form "rems=@./tests/test_files/xml/bigpicture/2.0/rems.xml;type=text/xml" \
     --form "sample=@./tests/test_files/xml/bigpicture/2.0/sample.xml;type=text/xml" \
     --form "staining=@./tests/test_files/xml/bigpicture/2.0/staining.xml;type=text/xml" | jq
```

**Note:** The submission update API call requires all necessary metadata XML files to be uploaded in the same call even
if they have not been altered. Metadata objects that are missing from the update are removed from the submission.

**Note:** The metadata version of a submission cannot be changed. To move a submission to another version before
publishing it, delete the submission as shown below and submit it again.

If you need to remove an unpublished submission entirely, you can delete it using the DELETE `submit` command:

```bash
curl --request DELETE "$API_URL/v1/submit/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN"
```

**Warning:** This action is permanent and cannot be undone. Make sure you have the correct submission ID before
executing this command.

### 5. Upload the data files to the Inbox

Before publishing, upload the dataset's data files to the Bigpicture Inbox, encrypted with Crypt4GH. Each file
must be under the directory `DATASET_<SUBMISSION_ID>`, at the path given by its `filename` attribute in the XML
files, with the `.c4gh` suffix added. The exact paths are listed by
[List files in the submission](#list-files-in-the-submission).

| Files                    | Path in the Inbox                                                       |
|--------------------------|-------------------------------------------------------------------------|
| Images (`image.xml`)     | `DATASET_<SUBMISSION_ID>/IMAGES/IMAGE_<image alias>/<file>.dcm.c4gh`    |
| Annotations              | `DATASET_<SUBMISSION_ID>/ANNOTATIONS/<file>.c4gh`                       |
| Ontologies (3.0)         | `DATASET_<SUBMISSION_ID>/ONTOLOGIES/<file>.c4gh`                        |
| Annotation tasks (3.0)   | `DATASET_<SUBMISSION_ID>/ANNOTATION_TASKS/<file>.c4gh`                  |
| Thumbnails (optional)    | `DATASET_<SUBMISSION_ID>/LANDING_PAGE/THUMBNAILS/<file>.jpg.c4gh`       |

Do not upload the metadata XML files: publishing writes them to the Inbox itself. Thumbnails are not
listed in the XML files; any `.jpg.c4gh` file in the thumbnails directory is added to the submission
when it is published.

### 6. Publish the submission

Once the metadata is final and all data files are in the Inbox, publish the submission with the PATCH
`publish` command:

```bash
curl --request PATCH "$API_URL/v1/publish/$SUBMISSION_ID" \
     --header "Authorization: Bearer $TOKEN" | jq
```

The response contains the submission ID. Publishing:

1. Checks the Inbox: every data file named in the XML files must be present, and the dataset directory
   must not contain any other files. Missing or unexpected files are listed in the error message.
2. Registers a DOI for the dataset with DataCite and, for a dataset with a clinical policy, creates the
   access application in REMS.
3. Writes the Crypt4GH-encrypted metadata XML files to `DATASET_<SUBMISSION_ID>/METADATA/` and
   `DATASET_<SUBMISSION_ID>/LANDING_PAGE/` in the Inbox. The landing page XML includes the DOI and REMS links.
4. Marks the submission published.

After the request returns, the data and metadata files are ingested into SDA and the dataset is
released in the background. This can take a while, and no further action is needed from you.

**Warning:** A published submission cannot be updated or deleted.

If publishing fails, for example because of a missing file, fix the problem and run the same command
again. Identifiers already registered by the failed attempt (DOI, REMS) are reused rather than created
again, and they are updated to match the current metadata. Publishing a submission that is already being
published fails at once with HTTP status 409.

#### Inspect the registrations

After publishing, the DOI and REMS identifiers of the dataset can be retrieved with:

```bash
curl --request GET "$API_URL/v1/submissions/$SUBMISSION_ID/registrations" \
     --header "Authorization: Bearer $TOKEN" | jq
```
