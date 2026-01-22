## Sensitive data submission Workflow with SD Submit API

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

To send metadata to Metax, the DataCite metadata in the `submission.json` document
must mapped to the Metax dataset V3 format.

Mapping DataCite V4.5 to Metax V3:

| Datacite property                      | Datacite sub-property                                                        | Metax field               | Metax sub-field                                               |
|----------------------------------------|------------------------------------------------------------------------------|---------------------------|---------------------------------------------------------------|
| Identifier                             | –                                                                            | persistent_identifier     | –                                                             |
| Creator                                | creatorName, nameIdentifier, affiliation                                     | actors (role=creator)     | name, external_identifier, organization                       |
| Title                                  | –                                                                            | title                     | –                                                             |
| Publisher                              | publisherName, publisherIdentifier                                           | actors (role=publisher)   | –                                                             |
| Subject                                | –                                                                            | field_of_science          | –                                                             |
| Subject                                | –                                                                            | keyword                   | –                                                             |
| Contributor                            | contributorName, nameIdentifier, affiliation                                 | actors (role=contributor) | name, external_identifier, organization, or organization, url |
| -                                      | –                                                                            | issued                    | –                                                             |
| Date (dateType=Other)                  | –                                                                            | temporal                  | start_date, end_date                                          |
| Description (descriptionType=abstract) | –                                                                            | description               | –                                                             |
| GeoLocation                            | geoLocationPolygon, geoLocationBox, geoLocationPoint, geoLocationPlace       | spatial                   | as_wkt, geographic_name                                       |
| Language                               | –                                                                            | language                  | –                                                             |
| Rights                                 | –                                                                            | access_rights/license     | –                                                             |
| –                                      | –                                                                            | access_rights/access_type | –                                                             |
| Publisher, FundingReference            | publisherName, publisherIdentifier, funderName, funderIdentifier,awardNumber | projects                  | participating_organizations, fundings, funding_identifier     |
| –                                      | –                                                                            | bibliographic_citation    | –                                                             |
| –                                      | –                                                                            | provenance                | –                                                             |
| –                                      | –                                                                            | remote_resources          | –                                                             |
