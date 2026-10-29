# Importing an existing Bigpicture dataset

An **import** brings a Bigpicture dataset that was already archived in SDA, outside SD Submit, into
SD Submit. The dataset keeps the accession it already has. Its metadata gets accessions for every other
object, and the dataset's XML metadata files in SDA are replaced with the newly accessioned ones.

## Configuration

| Variable                        | Description                                                                 |
|---------------------------------|-----------------------------------------------------------------------------|
| `IMPORT_USERS`                  | JSON array of the ids of the users allowed to import. Default `[]`.         |
| `INGEST_RETRY_COOLDOWN_SECONDS` | How long to wait before sending SDA again a request it has not carried out. |

## Who can import

Import is available only in the NBIS deployment, and only to users listed in `IMPORT_USERS`. Anyone
else is refused.

## Importing a dataset

Send the dataset's Bigpicture XML files to `POST /v1/import`, the same files you would send for a new
submission. `datacite.xml` is not accepted in an import.

### What is validated

**The metadata is validated exactly as for a new submission:** XML schemas, references between
objects, mandatory content, and the policy.

**Accessions:**

- The dataset must have an accession, which becomes the submission's ID.
- The dataset accession must have the format:
  `{BP_CENTER_ID}-dataset-xxxxxx-xxxxxx`, where each `x` is a lowercase letter or digit other than
  `i`, `l`, `o`, `0` and `1`.
- No other object may have an accession. They will be assigned new ones.
- A reference to another object may have an accession only if references the dataset.

**The dataset in SDA:**

- It must not already have been imported or submitted.
- It must exist in SDA, must not be deprecated, and must have files.
- All its files must be under one shared top-level directory.

**Below that directory, the files must be laid out as for a new submission.** Paths are compared
without the `.c4gh` suffix:

| Files            | Path below the top-level directory                                       |
|------------------|--------------------------------------------------------------------------|
| Metadata XMLs    | `METADATA/dataset.xml`, `METADATA/policy.xml`, …                         |
| Landing page XML | `LANDING_PAGE/landing_page.xml`                                          |
| Thumbnails       | `LANDING_PAGE/THUMBNAILS/*.jpg`                                          |
| Images           | `IMAGES/IMAGE_{alias}/*.dcm`, as given in `image.xml`                    |
| Other data files | `ANNOTATIONS/`, `ONTOLOGIES/`, `ANNOTATION_TASKS/`, as given in the XMLs |

**Matching the XMLs and SDA:**

- Every data file named in the XMLs must be in SDA at its path.
- Every file in SDA must be a metadata XML, a data file named in the XMLs, or a thumbnail. Anything
  else is an error.
- The metadata XMLs in SDA must be the same ones being imported. The one exception: a landing page may
  be added if the dataset in SDA doesn't have one.
- Two files with the same path in the dataset are an error.

All problems found in the dataset's files are reported together, so they can be fixed in one go.

**REMS**, for datasets with a clinical policy, when registration is enabled:

- The REMS workflow in `rems.xml` must exist, and belong to the organisation given in `rems.xml`.
- If the dataset already has a REMS resource and catalogue item, they must belong to that organisation,
  and the catalogue item must use that workflow. They are reused rather than duplicated.
- An existing catalogue item whose resource is no longer active is an error.

### After a successful import

- **The submission is marked as imported.**
- **The data files and thumbnails are recorded** in the database with the accessions SDA gave them, and as already
  archived. They are never uploaded or ingested again.
- **The old metadata XMLs in SDA are not recorded** in the database. They will be replaced during publish.

## Changing or deleting an import

An imported submission can't be updated. To correct its XMLs before publishing, delete it with
`DELETE /v1/import/{id}` and import it again. The normal submission endpoints refuse to change or
delete an imported submission. As with any submission, a published import can't be deleted.

## Publishing

Publish an imported submission:

- **writes the newly accessioned metadata XMLs** to the SDA inbox, under the dataset's own top-level
  directory and at the same paths as the old ones;
- **skips the inbox check for data files**, because they are already archived
- **registers the dataset in REMS**, reusing an existing resource and catalogue item if there are any.
  An existing resource keeps its licences, because REMS can't change a resource's licences after it is
  created.

## Ingest

After publishing, SD Submit ingests the new metadata XMLs as usual. It then updates the dataset in SDA
in three steps:

1. **Removes the old metadata XMLs from the dataset.** They stay archived in SDA, only no longer
   part of the dataset. No other ingested files in SDA are touched.
2. **Adds the new metadata XMLs.**
3. **Releases the dataset.**

Between steps 1 and 2 the dataset briefly has no metadata XMLs.

Each step is confirmed by checking the dataset files in SDA. Requests that SDA doesn't execute are sent
again.

A dataset that is deprecated, or has files removed, in SDA outside SD Submit before step 3 can't be
released. Ingest then stops with an error, logged on every scan until the dataset is registered again.
