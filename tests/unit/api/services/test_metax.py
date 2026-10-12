import pytest
from pydantic_string_url import AnyUrl

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.models.datacite import (
    GeoLocation,
    GeoLocationPoint,
    GeoLocationPolygonPoint,
    Publisher,
    Subject,
)
from metadata_backend.api.models.metax import FieldOfScience, MetaxFields
from metadata_backend.api.services.metax import MetaxMapper, MetaxService
from metadata_backend.api.services.ror import RorService


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


def _metax_fields() -> MetaxFields:
    return MetaxFields(title="title", description="description", persistent_identifier="doi", actors=[], keyword=[])


def test_map_spatial_unknown_place():
    metax = _metax_fields()
    metax.spatial = []
    location = GeoLocation(
        geoLocationPlace="Unknown place", geoLocationPoint=GeoLocationPoint(pointLatitude=60.0, pointLongitude=24.0)
    )
    MetaxMapper._map_spatial([location], metax)
    assert metax.spatial[0].geographic_name == "Unknown place"
    assert metax.spatial[0].reference is None
    assert metax.spatial[0].custom_wkt == ["POINT (24.0 60.0)"]


def test_map_spatial_without_place():
    metax = _metax_fields()
    metax.spatial = []
    location = GeoLocation(geoLocationPoint=GeoLocationPoint(pointLatitude=60.0, pointLongitude=24.0))
    MetaxMapper._map_spatial([location], metax)
    assert metax.spatial[0].geographic_name is None
    assert metax.spatial[0].reference is None
    assert metax.spatial[0].custom_wkt == ["POINT (24.0 60.0)"]


def test_map_spatial_known_place():
    metax = _metax_fields()
    metax.spatial = []
    MetaxMapper._map_spatial([GeoLocation(geoLocationPlace="Valaam")], metax)
    assert metax.spatial[0].reference.url == "http://www.yso.fi/onto/yso/p105065"


async def test_map_projects_without_funding_references():
    metax = _metax_fields()
    metax.projects = []
    mapper = MetaxMapper(TestMetaxService(), TestRorService())
    await mapper._map_projects(Publisher(name="CSC"), None, metax)
    assert len(metax.projects) == 1
    assert metax.projects[0].participating_organizations[0].pref_label == {"en": "CSC"}
    assert metax.projects[0].funding == []


def _polygon_point(lon: float, lat: float) -> GeoLocationPolygonPoint:
    return GeoLocationPolygonPoint(polygonPoint=GeoLocationPoint(pointLongitude=lon, pointLatitude=lat))


def test_map_spatial_polygon():
    metax = _metax_fields()
    metax.spatial = []
    polygon = [_polygon_point(24.0, 60.0), _polygon_point(25.0, 60.0), _polygon_point(25.0, 61.0)]
    MetaxMapper._map_spatial([GeoLocation(geoLocationPolygon=polygon)], metax)
    assert metax.spatial[0].custom_wkt == ["POLYGON((24.0 60.0, 25.0 60.0, 25.0 61.0, 24.0 60.0))"]


def test_map_spatial_polygon_ignores_in_polygon_point():
    metax = _metax_fields()
    metax.spatial = []
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
    metax = _metax_fields()
    metax.spatial = []
    with pytest.raises(UserException, match="at least three distinct polygonPoints"):
        MetaxMapper._map_spatial([GeoLocation(geoLocationPolygon=polygon)], metax)
