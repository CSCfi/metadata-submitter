import uuid
from random import randrange

from metadata_backend.api.models.metax import FieldOfScience, MetaxFields
from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.submission import Submission
from metadata_backend.services.metax_service import MetaxServiceHandler
from metadata_backend.services.ror_service import RorServiceHandler
from tests.utils import sd_submission_dict


async def test_metax_service(client, secret_env):
    """Test publish Metax fields using test service."""

    from metadata_backend.services.metax_service import MetaxServiceHandler
    from metadata_backend.services.pid_service import PIDServiceHandler

    metax_service = MetaxServiceHandler()
    ror_service = RorServiceHandler()
    pid_service = PIDServiceHandler(metax_service)

    # Submission with DataCite metadata
    project_id = f"test_{uuid.uuid4()}"
    submission_dict = sd_submission_dict()
    submission_dict["projectId"] = project_id
    submission = Submission(**submission_dict)

    # Register draft DOI
    doi = await pid_service.create_draft_doi()

    submission_id = f"test_{uuid.uuid4()}"
    metax_discovery_url = f"https://etsin.demo.fairdata.fi/dataset/{uuid.uuid4()}"  # Domain registered in DataCite.

    # Submission registration
    registration = Registration(
        submissionId=submission_id, doi=doi, title=submission.title, description=submission.description
    )

    # Register Metax ID
    metax_id = await metax_service.create_draft_dataset(doi, submission.title, submission.description)
    created_dataset = await metax_service.get_dataset(metax_id)
    assert created_dataset["id"] is not None
    assert created_dataset["description"] == {"en": "TestDescription"}
    assert created_dataset["title"] == {"en": "TestTitle"}
    assert created_dataset["persistent_identifier"].startswith("10.80869")
    assert created_dataset["persistent_identifier"] == doi

    # Check Metax state is "draft"
    assert created_dataset["state"] == "draft"

    # Update Submission registration with Metax ID
    registration.metaxId = metax_id

    # Add DataCite metadata and publish DOI
    # Field_of_science is required for SD submission.
    await pid_service.publish(
        registration, submission.metadata, metax_discovery_url, require_field_of_science=True, publish=False
    )

    # Update Metax dataset
    await metax_service.update_dataset_metadata(submission.metadata, metax_id, ror_service)

    # Update Metax dataset description
    rems_url = f"https://sd-apply.csc.fi/catalogue/{randrange(100)}"
    new_description = registration.description + f"\n\nSD Apply Application link: {rems_url}"
    await metax_service.update_dataset_description(metax_id, new_description)

    # Publish Metax dataset
    published_dataset = await metax_service.publish_dataset(metax_id, doi)

    # Check Metax state changed from "draft" to "published"
    assert published_dataset["state"] == "published"

    published_metax = MetaxFields(**published_dataset)
    metadata = submission.metadata

    assert published_metax.persistent_identifier == doi
    assert published_metax.title["en"] == metadata.titles[0].title
    assert published_metax.description["en"] == new_description

    # Check Metax access_rights
    assert (
        published_metax.access_rights.access_type.url
        == "http://uri.suomi.fi/codelist/fairdata/access_type/code/restricted"
    )
    assert (
        published_metax.access_rights.license[0].url
        == "http://uri.suomi.fi/codelist/fairdata/license/code/notspecified"
    )
    assert (
        published_metax.access_rights.restriction_grounds[0].url
        == "http://uri.suomi.fi/codelist/fairdata/restriction_grounds/code/personal_data"
    )

    # Check Metax actors
    for actor in published_metax.actors:
        if actor.roles[0] == "creator":
            assert any(actor.person.name == creator.name for creator in metadata.creators)
            for creator in metadata.creators:
                assert any(
                    actor.organization.pref_label["en"] == affiliation.name for affiliation in creator.affiliation
                )
        if actor.roles[0] == "publisher":
            assert actor.organization.pref_label["en"] == metadata.publisher.name
        if actor.roles[0] == "contributor":
            assert any(actor.person.name == contributor.name for contributor in metadata.contributors)
            for contributor in metadata.contributors:
                assert any(
                    actor.organization.pref_label["en"] == affiliation.name for affiliation in contributor.affiliation
                )
    # Check Metax keywords
    assert all(subject.subject in published_metax.keyword for subject in metadata.subjects)

    # Check Metax field_of_science
    subject_value_uris = {subject.valueUri for subject in metadata.subjects}
    fos_urls = {fos.url for fos in published_metax.field_of_science}
    assert subject_value_uris == fos_urls

    # Check Metax language
    assert published_metax.language[0].url == "http://lexvo.org/id/iso639-3/eng"

    # Check Metax projects
    for project in published_metax.projects:
        assert project.participating_organizations[0].pref_label["en"] == metadata.publisher.name
        for funding in project.funding:
            assert any(
                funding.funder.organization.pref_label["en"] == fundingRef.funderName
                for fundingRef in metadata.fundingReferences
            )
            assert any(
                funding.funding_identifier == fundingRef.awardNumber for fundingRef in metadata.fundingReferences
            )

    # Check Metax spatial
    for location in published_metax.spatial:
        assert any(location.geographic_name == geoLocation.geoLocationPlace for geoLocation in metadata.geoLocations)
        # TODO(improve): Tests for custom_wkt

    # Check Metax temporal
    for date in metadata.dates:
        if date.dateType == "Other":
            date_split = date.date.split("/", 1)
            assert any(date_split[0] == temporal.start_date for temporal in published_metax.temporal)
            assert any(date_split[1] == temporal.end_date for temporal in published_metax.temporal)


async def test_get_fields_of_science(client, secret_env):
    """Test get Metax fields of science."""

    metax_service = MetaxServiceHandler()

    fields = await metax_service.get_fields_of_science()
    assert len(fields) > 1

    ontology_url = "http://www.yso.fi/onto/okm-tieteenala"

    # Check Mathematics.
    assert (
        FieldOfScience(
            id="8848e88b-a536-43c7-b614-0045b136920d",
            url=f"{ontology_url}/ta111",
            pref_label={"en": "Mathematics", "fi": "Matematiikka", "sv": "Matematik"},
        )
        in fields
    )

    field = next((f for f in fields if f.code == "ta111"), None)
    assert field is not None
    assert field.url == f"{ontology_url}/ta111"

    # Check URLs.
    assert all(f.url.startswith(ontology_url) and f.url.rstrip("/").split("/")[-1] == f.code for f in fields), (
        "Not all URLs have the expected base URL and code suffix"
    )
