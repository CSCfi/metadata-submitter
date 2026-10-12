# Bigpicture sync API

The sync endpoints allow other services to mirror published metadata. One endpoint
lists published submissions, while the other returns an archive of the metadata
objects in one submission.

## Environmental variables

| Variable      | Description                                                   |
|---------------|---------------------------------------------------------------|
| SYNC_CLIENTS  | Clients allowed to sync published submissions.                |
| SYNC_AUDIENCE | Audience of the JWT tokens for syncing published submissions. |

`SYNC_CLIENTS` is a JSON array with one object per client, containing the
issuer (iss) and the client's base64-encoded PEM public keys used to sign the JWT
token.

```json
[{"iss": "sd-search-api", "public_keys": ["<base64-encoded PEM public key>"]}]
```

The sync endpoints are not mounted when `SYNC_CLIENTS` is unset. `SYNC_AUDIENCE` is required
with it.

## Authorization

The sync endpoints are under `/sync` and authorized with a bearer JWT token signed by the clients
private key. This service holds the public keys to verify the JWT token signature.

JWT claims:

| Claim | Value                                              |
|-------|----------------------------------------------------|
| `iss` | The issuer listed in `SYNC_CLIENTS`.               |
| `sub` | The same as `iss`.                                 |
| `aud` | The audience that must match the `SYNC_AUDIENCE`.  |
| `iat` | When the token was signed.                         |
| `exp` | When the token expires.                            |

A token is rejected unless all these claims are present.

A sync client may list several `public_keys` and a token can
be signed with any of them. This allows signing keys to be
rotated.

## Sync workflow

### 1. List published submissions (/sync)

Published submissions can be listed using the `/sync` endpoint.
Clients are expected to track the most recent publication datetime returned by the
endpoint. In subsequent calls, clients should use the `publishedStart` datetime
parameter to retrieve all submissions published since the previous time they called
the `/sync` endpoint. The `publishedStart` value should be set to
slightly before the tracked publication datetime to avoid missing any submissions
that were being published when `/sync` was called.

Example request:

```bash
curl --request GET "$API_URL/sync?publishedStart=2026-01-01T00:00:00Z" \
     --header "Authorization: Bearer $SYNC_TOKEN" | jq
```

Example response:

```json
{
  "submissions": [
    {
      "submissionId": "...",
      "published": "2026-01-15T09:12:03.123456+00:00",
      "ingested": "2026-01-15T10:02:41.512345+00:00"
    },
    {
      "submissionId": "...",
      "published": "2026-02-04T14:31:58.654321+00:00"
    }
  ]
}
```

The `ingested` date is set once the files of the submission have been ingested into the
archive and the dataset has been released. A submission is listed when it is published,
which may be before its files are ingested.

Clients that only need the metadata can ignore the `ingested` date.

Clients that also need the files must call `/sync` again later to see if a submission
has been ingested. Because the next call uses a later `publishedStart` date, a
submission that has not been ingested yet would not be returned again. To avoid this:

1. Keep a list of the submissions returned without an `ingested` date.
2. Set `publishedStart` slightly before the publication date of the oldest submission in
   that list, instead of the most recent publication date.
3. Remove a submission from the list once it is returned with an `ingested` date.

A submission whose files fail to ingest never gets an `ingested` date. Clients should
remove it from the list after waiting as long as they choose, so that it does not keep
`publishedStart` in the past.

The list of parameters:

| Parameter        | Description                                                                                                                         |
|------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `publishedStart` | Optional. The first publication date to return, inclusive (ISO 8601 format). Everything published up to the end date when omitted.  |
| `publishedEnd`   | Optional. The last publication date to return, inclusive (ISO 8601 format). Everything published since the start date when omitted. |

The dates must specify a UTC offset, for example `2026-01-01T00:00:00Z` or `2026-01-01T03:00:00+03:00`.

Omitting both parameters returns all published submissions:

```bash
curl --request GET "$API_URL/sync" \
     --header "Authorization: Bearer $SYNC_TOKEN" | jq
```

### 2. Get submission metadata archive (/sync/{submissionId})

The metadata objects of one submission can be retrieved as a zip archive
using the `/sync/{submissionId}` endpoint. The XML
metadata files are stored in the METADATA directory:

```
METADATA/dataset.xml
METADATA/image.xml
METADATA/datacite.xml
...
```

There is one document per schema, containing all metadata objects of that schema.

The files of the submission are listed in `FILES/files.json`. The list contains every
file of the dataset, including the image and annotation files and the metadata documents
uploaded with them, ordered by path.

```json
[
  {
    "fileId": "...",
    "objectId": "...",
    "path": "..."
  }
]
```

| Field      | Description                                                              |
|------------|--------------------------------------------------------------------------|
| `fileId`   | The file accession.                                                      |
| `objectId` | The accession of the metadata object that references the file. Optional. |
| `path`     | The file path.                                                           |

Example request:

```bash
export SUBMISSION_ID="..."

curl --request GET "$API_URL/sync/$SUBMISSION_ID" \
     --header "Authorization: Bearer $SYNC_TOKEN" \
     --output "$SUBMISSION_ID.zip"
```
