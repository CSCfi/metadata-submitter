from datetime import date
from unittest.mock import AsyncMock

import pytest
from pydantic_string_url import AnyUrl

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.models.datacite import (
    Affiliation,
    Creator,
    Date,
    GeoLocation,
    GeoLocationPoint,
    GeoLocationPolygonPoint,
    Publisher,
    Subject,
)
from metadata_backend.api.models.metax import (
    ACCESS_TYPE_URL,
    DATA_CATALOG,
    LICENSE_URL,
    RESTRICTION_GROUND_URL,
    FieldOfScience,
    MetaxFields,
    MetaxMappedFields,
)
from metadata_backend.api.models.submission import SubmissionMetadata
from metadata_backend.api.services.metax import MetaxMapper, MetaxService
from metadata_backend.api.services.ror import RorService
from metadata_backend.services.metax_service import MetaxServiceHandler


class TestMetaxService(MetaxService):
    async def get_fields_of_science(self) -> list[FieldOfScience]:
        return [
            FieldOfScience(
                id="1",
                url=AnyUrl("http://www.yso.fi/onto/okm-tieteenala/ta111"),
                pref_label={
                    "en": "Mathematics",
                    "fi": "Matematiikka",
                },
            ),
            FieldOfScience(
                id="2",
                url=AnyUrl("http://www.yso.fi/onto/okm-tieteenala/ta222"),
                pref_label={
                    "en": "Physics",
                    "fi": "Fysiikka",
                },
            ),
        ]


async def test_get_field_of_science_by_url():
    service = TestMetaxService()

    for url in [
        "http://www.yso.fi/onto/okm-tieteenala/ta111",
        "https://www.yso.fi/onto/okm-tieteenala/ta111",
        "http://www.yso.fi/onto/okm-tieteenala/ta111/",
    ]:
        # Search URL in subject.subject.
        subject = Subject(subject=url)
        field = await service.get_field_of_science(subject)
        assert field is not None
        assert field.code == "ta111"
        assert field.label == "Mathematics"
        assert str(field.url) == "http://www.yso.fi/onto/okm-tieteenala/ta111"
        # Search URL in subject.valueUri.
        subject = Subject(subject="unknown", valueUri=AnyUrl(url))
        field = await service.get_field_of_science(subject)
        assert field is not None
        assert field.code == "ta111"
        assert field.label == "Mathematics"
        assert str(field.url) == "http://www.yso.fi/onto/okm-tieteenala/ta111"


async def test_get_field_of_science_by_code():
    service = TestMetaxService()

    for code in ["TA111", "ta111", "ta 111 ", "111"]:
        # Search code in subject.subject.
        subject = Subject(subject=code)
        field = await service.get_field_of_science(subject)
        assert field is not None
        assert field.code == "ta111"
        assert field.label == "Mathematics"
        assert str(field.url) == "http://www.yso.fi/onto/okm-tieteenala/ta111"


async def test_get_field_of_science_by_label():
    service = TestMetaxService()

    for label in ["Mathematics", "Matematiikka", "mathem  atics", "MATEMA-TIIKKA"]:
        # Search label in subject.subject.
        subject = Subject(subject=label)
        field = await service.get_field_of_science(subject)
        assert field is not None
        assert field.code == "ta111"
        assert field.label == "Mathematics"
        assert str(field.url) == "http://www.yso.fi/onto/okm-tieteenala/ta111"


async def test_get_field_of_science_by_ui():
    service = TestMetaxService()

    for ui in ["111 - Matematiikka", "111 - MATEMA-TIIKKA", "0 - Matematiikka"]:
        # Search ui formatted string in subject.subject.
        subject = Subject(subject=ui)
        field = await service.get_field_of_science(subject)
        assert field is not None
        assert field.code == "ta111"
        assert field.label == "Mathematics"
        assert str(field.url) == "http://www.yso.fi/onto/okm-tieteenala/ta111"


async def test_get_field_of_science_unknown_subject():
    service = TestMetaxService()
    subject = Subject(subject="unknown")
    field = await service.get_field_of_science(subject)
    assert field is None


async def test_get_field_of_science_empty_subject():
    service = TestMetaxService()
    subject = Subject(subject="")
    field = await service.get_field_of_science(subject)
    assert field is None


class TestRorService(RorService):
    async def get_organisation(self, organisation: str) -> tuple[AnyUrl, str] | None:
        return AnyUrl("https://ror.org/020hwjq30"), organisation


def test_map_spatial_unknown_place():
    metax = MetaxMappedFields()
    location = GeoLocation(
        geoLocationPlace="Unknown place", geoLocationPoint=GeoLocationPoint(pointLatitude=60.0, pointLongitude=24.0)
    )
    MetaxMapper._map_spatial([location], metax)
    assert metax.spatial[0].geographic_name == "Unknown place"
    assert metax.spatial[0].reference is None
    assert metax.spatial[0].custom_wkt == ["POINT (24.0 60.0)"]


def test_map_spatial_without_place():
    metax = MetaxMappedFields()
    location = GeoLocation(geoLocationPoint=GeoLocationPoint(pointLatitude=60.0, pointLongitude=24.0))
    MetaxMapper._map_spatial([location], metax)
    assert metax.spatial[0].geographic_name is None
    assert metax.spatial[0].reference is None
    assert metax.spatial[0].custom_wkt == ["POINT (24.0 60.0)"]


def test_map_spatial_known_place():
    metax = MetaxMappedFields()
    MetaxMapper._map_spatial([GeoLocation(geoLocationPlace="Valaam")], metax)
    assert metax.spatial[0].reference.url == "http://www.yso.fi/onto/yso/p105065"


async def test_map_projects_without_funding_references():
    metax = MetaxMappedFields()
    mapper = MetaxMapper(TestMetaxService(), TestRorService())
    await mapper._map_projects(Publisher(name="CSC"), None, metax)
    assert len(metax.projects) == 1
    assert metax.projects[0].participating_organizations[0].pref_label == {"en": "CSC"}
    assert metax.projects[0].funding == []


def _polygon_point(lon: float, lat: float) -> GeoLocationPolygonPoint:
    return GeoLocationPolygonPoint(polygonPoint=GeoLocationPoint(pointLongitude=lon, pointLatitude=lat))


def test_map_spatial_polygon():
    metax = MetaxMappedFields()
    polygon = [_polygon_point(24.0, 60.0), _polygon_point(25.0, 60.0), _polygon_point(25.0, 61.0)]
    MetaxMapper._map_spatial([GeoLocation(geoLocationPolygon=polygon)], metax)
    assert metax.spatial[0].custom_wkt == ["POLYGON((24.0 60.0, 25.0 60.0, 25.0 61.0, 24.0 60.0))"]


def test_map_spatial_polygon_ignores_in_polygon_point():
    metax = MetaxMappedFields()
    polygon = [
        _polygon_point(24.0, 60.0),
        _polygon_point(25.0, 60.0),
        _polygon_point(25.0, 61.0),
        _polygon_point(24.0, 60.0),
        GeoLocationPolygonPoint(inPolygonPoint=GeoLocationPoint(pointLongitude=24.5, pointLatitude=60.5)),
    ]
    MetaxMapper._map_spatial([GeoLocation(geoLocationPolygon=polygon)], metax)
    assert metax.spatial[0].custom_wkt == ["POLYGON((24.0 60.0, 25.0 60.0, 25.0 61.0, 24.0 60.0))"]


@pytest.mark.parametrize(
    "polygon",
    [
        [],
        [GeoLocationPolygonPoint(inPolygonPoint=GeoLocationPoint(pointLongitude=24.5, pointLatitude=60.5))],
        [_polygon_point(24.0, 60.0), _polygon_point(25.0, 60.0), _polygon_point(24.0, 60.0)],
    ],
)
def test_map_spatial_polygon_too_few_points(polygon):
    metax = MetaxMappedFields()
    with pytest.raises(UserException, match="at least three distinct polygonPoints"):
        MetaxMapper._map_spatial([GeoLocation(geoLocationPolygon=polygon)], metax)


def _submission_metadata(**kwargs) -> SubmissionMetadata:
    return SubmissionMetadata(
        creators=[Creator(name="Creator", affiliation=[Affiliation(name="CSC")])],
        publisher=Publisher(name="CSC"),
        subjects=[Subject(subject="keyword")],
        **kwargs,
    )


def _metax_service_handler() -> MetaxServiceHandler:
    handler = MetaxServiceHandler.__new__(MetaxServiceHandler)
    handler.get_fields_of_science = TestMetaxService().get_fields_of_science
    return handler


async def test_validate_dataset_metadata():
    """Test that validate does not change the submission metadata."""
    metadata = _submission_metadata()
    original_metadata = metadata.model_copy(deep=True)
    await _metax_service_handler().validate_dataset_metadata(metadata, TestRorService())
    assert metadata == original_metadata


async def test_validate_dataset_metadata_missing_affiliation():
    metadata = _submission_metadata()
    metadata.creators = [Creator(name="Creator")]
    with pytest.raises(UserException, match="Affiliation is required for Creator"):
        await _metax_service_handler().validate_dataset_metadata(metadata, TestRorService())


@pytest.mark.parametrize("subjects", [None, []], ids=["null", "empty"])
async def test_validate_dataset_metadata_no_subjects(subjects):
    """Test that metadata without subjects is rejected, since keywords are mapped from the subjects."""
    metadata = _submission_metadata()
    metadata.subjects = subjects
    with pytest.raises(UserException, match="At least one Metax keyword is required"):
        await _metax_service_handler().validate_dataset_metadata(metadata, TestRorService())


async def test_validate_dataset_metadata_invalid_date():
    metadata = _submission_metadata(dates=[Date(date="not a date", dateType="Other")])
    with pytest.raises(UserException, match="Invalid date value: not a date"):
        await _metax_service_handler().validate_dataset_metadata(metadata, TestRorService())


async def test_validate_dataset_metadata_invalid_language():
    metadata = _submission_metadata(language="en-GB")
    with pytest.raises(UserException, match="Invalid language: en-GB"):
        await _metax_service_handler().validate_dataset_metadata(metadata, TestRorService())


async def test_update_dataset_metadata():
    """Test that the mapped fields are merged into the dataset read from Metax and the result is patched to Metax.

    Mapped fields replace the dataset's fields, fields with no values mapped are cleared, and fields that are
    not mapped keep their MetaxFields defaults, such as the access rights.
    """
    handler = _metax_service_handler()

    metax_dataset = {
        "title": {"en": "title"},
        "description": {"en": "description"},
        "persistent_identifier": "doi",
        "actors": [
            {"organization": {"pref_label": {"en": "Old"}}, "roles": ["creator"], "person": {"name": "Old Creator"}}
        ],
        "keyword": ["old"],
        "temporal": [{"start_date": "2020-01-01", "end_date": None}],
    }

    # Replace the GET request to Metax with a Metax dataset the mapped fields are merged into.
    handler.get_dataset = AsyncMock(return_value=metax_dataset)
    handler._patch = AsyncMock()

    await handler.update_dataset_metadata(_submission_metadata(), "metax_id", TestRorService())

    csc_organization = {"pref_label": {"en": "CSC"}, "external_identifier": "https://ror.org/020hwjq30"}

    handler._patch.assert_awaited_once_with(
        "metax_id",
        {
            **metax_dataset,
            # Mapped fields replace the dataset's fields.
            "actors": [
                {
                    "organization": csc_organization,
                    "roles": ["creator"],
                    "person": {"name": "Creator", "external_identifier": None},
                },
                {"organization": csc_organization, "roles": ["publisher"], "person": None},
            ],
            "keyword": ["keyword"],
            # Fields the dataset did not have are mapped.
            "issued": date.today().isoformat(),
            "projects": [{"participating_organizations": [csc_organization], "funding": []}],
            # Fields with nothing mapped are cleared, even if the dataset had them.
            "temporal": None,
            # Fields that are not mapped keep their defaults.
            "data_catalog": DATA_CATALOG,
            "access_rights": {
                "access_type": {"url": ACCESS_TYPE_URL},
                "license": [{"url": LICENSE_URL}],
                "restriction_grounds": [{"url": RESTRICTION_GROUND_URL}],
            },
            "field_of_science": None,
            "language": None,
            "spatial": None,
            "relation": None,
            "theme": None,
        },
    )


@pytest.mark.parametrize(
    "draft_fields",
    [
        {"actors": None, "keyword": None, "projects": None},
        {},
    ],
    ids=["null", "missing"],
)
async def test_update_dataset_metadata_draft_without_fields(draft_fields):
    """Test that a draft read from Metax without the fields the mapper fills in is updated with the mapped fields."""
    handler = _metax_service_handler()

    # Replace the GET request to Metax with a new draft, which has no actors, keywords or projects.
    handler.get_dataset = AsyncMock(
        return_value={
            "title": {"en": "title"},
            "description": {"en": "description"},
            "persistent_identifier": "doi",
            **draft_fields,
        }
    )
    handler._patch = AsyncMock()

    await handler.update_dataset_metadata(_submission_metadata(), "metax_id", TestRorService())

    data = handler._patch.await_args.args[1]
    assert [actor["person"] for actor in data["actors"]] == [{"name": "Creator", "external_identifier": None}, None]
    assert data["keyword"] == ["keyword"]
    assert len(data["projects"]) == 1


def test_metax_mapped_fields_exist_in_metax_fields():
    """Test that every mapped field is a Metax field, since an unknown one would be sent to Metax as an extra field."""
    assert set(MetaxMappedFields.model_fields) <= set(MetaxFields.model_fields)
