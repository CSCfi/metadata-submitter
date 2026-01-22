from pydantic_string_url import AnyUrl

from metadata_backend.api.models.datacite import Subject
from metadata_backend.api.models.metax import FieldOfScience
from metadata_backend.api.services.metax import MetaxService


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
