from metadata_backend.api.models.metax import FieldOfScience


def test_code():
    fos = FieldOfScience(id="1", url="http://www.yso.fi/onto/okm-tieteenala/ta999", pref_label={"en": "Physics"})
    assert fos.code == "ta999"


def test_label():
    # English
    fos = FieldOfScience(
        id="1", url="http://www.yso.fi/onto/okm-tieteenala/ta999", pref_label={"en": "Physics", "fi": "Fysiikka"}
    )
    assert fos.label == "Physics"

    # Finnish fallback
    fos.pref_label = {"fi": "Fysiikka"}
    assert fos.label == "Fysiikka"

    # First value
    fos.pref_label = {"sv": "Fysik", "de": "Physik"}
    assert fos.label == "Fysik"
