from metadata_backend.api.models.metax import FieldOfScience
from metadata_backend.api.services.metax import MetaxService


class TestMetaxService(MetaxService):
    async def get_fields_of_science(self) -> list[FieldOfScience]:
        return [
            FieldOfScience(
                id="1",
                url="http://www.yso.fi/onto/okm-tieteenala/ta111",
                pref_label={
                    "en": "Mathematics",
                    "fi": "Matematiikka",
                },
            ),
            FieldOfScience(
                id="2",
                url="http://www.yso.fi/onto/okm-tieteenala/ta222",
                pref_label={
                    "en": "Physics",
                    "fi": "Fysiikka",
                },
            ),
        ]


async def test_get_field_of_science_by_code():
    service = TestMetaxService()

    for code in ["TA111", "ta111", "ta 111 ", "111"]:
        field = await service.get_field_of_science(code)
        assert field is not None
        assert field.code == "ta111"


async def test_get_field_of_science_by_label():
    service = TestMetaxService()

    for label in ["Mathematics", "Matematiikka", "mathem  atics", "MATEMA-TIIKKA"]:
        field = await service.get_field_of_science(label)
        assert field is not None
        assert field.code == "ta111"


async def test_get_field_of_science_unknown():
    service = TestMetaxService()

    field = await service.get_field_of_science("Unknown")
    assert field is None


async def test_get_field_of_science_empty():
    service = TestMetaxService()

    field = await service.get_field_of_science("")
    assert field is None
