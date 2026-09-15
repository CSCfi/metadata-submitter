import pytest
from pydantic import ValidationError

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.processors.xml.bigpicture import BP_XML_OBJECT_CONFIG
from metadata_backend.api.processors.xml.processors import XmlObjectProcessor
from metadata_backend.api.services.submission.bigpicture_attributes import (
    BP_ATTRIBUTE_TYPE_STRING,
    BP_BOOLEAN_CONTROLLED_VALUES,
    BP_VALUE_TYPE_BOOLEAN,
    BP_VALUE_TYPE_CONTROLLED_VALUE,
    BP_VALUE_TYPE_TEXT,
    BigpictureAttributesConfig,
    BigpictureStringAttribute,
    normalised_value,
    read_attributes,
)

_POLICY_OBJECT_NAME = "Policy"


def _string_attribute(tag: str = "tag", **fields) -> BigpictureStringAttribute:
    return BigpictureStringAttribute(tag=tag, attribute_type=BP_ATTRIBUTE_TYPE_STRING, **fields)


def _controlled_attribute(*controlled_values, **fields) -> BigpictureStringAttribute:
    return _string_attribute(value_type=BP_VALUE_TYPE_CONTROLLED_VALUE, controlled_values=controlled_values, **fields)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("durationofaccess", "durationofaccess"),
        ("duration_of_access", "durationofaccess"),
        ("Duration Of Access", "durationofaccess"),
        ("Non-Clinical/Obscured", "nonclinicalobscured"),
    ],
)
def test_normalised_value(value, expected):
    """A value is normalised without case, punctuation or whitespace."""

    assert normalised_value(value) == expected


@pytest.mark.parametrize(
    ("attribute", "given", "expected"),
    [
        # A string attribute is not validated and is returned unchanged.
        (_string_attribute(), ["anything at all"], ["anything at all"]),
        (_string_attribute(multiple=True), ["a", "b"], ["a", "b"]),
        # A controlled value is normalised and matched, and the value it matches is returned.
        (_controlled_attribute("Unlimited time"), ["Unlimited time"], ["Unlimited time"]),
        (_controlled_attribute("Unlimited time"), ["unlimited  TIME"], ["Unlimited time"]),
        (_controlled_attribute("Non-Clinical/Obscured"), ["NON CLINICAL OBSCURED"], ["Non-Clinical/Obscured"]),
        (_controlled_attribute("Non-Clinical/Obscured"), ["nonclinicalobscured"], ["Non-Clinical/Obscured"]),
        # A previous controlled value value becomes the current one that replaces it.
        (_controlled_attribute("Worldwide", {"value": "New", "previous_values": ["Old"]}), ["old"], ["New"]),
        # A boolean attribute is treated as a controlled value with True and False values.
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["true"], ["True"]),
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["Yes"], ["True"]),
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["False"], ["False"]),
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["no"], ["False"]),
    ],
)
def test_validated_values(attribute, given, expected):
    assert attribute.validated_values(given, _POLICY_OBJECT_NAME) == expected


@pytest.mark.parametrize(
    ("attribute", "given", "message"),
    [
        # A mandatory attribute must be given a value.
        (_string_attribute(mandatory=True), [], "'tag' is mandatory"),
        # An attribute that is not multiple can have only one value.
        (_string_attribute(), ["a", "b"], "may be given only once"),
        # An invalid controlled value.
        (_controlled_attribute("Worldwide"), ["Europe"], "must be one of"),
        # An invalid boolean value.
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["Invalid"], "must be one of"),
    ],
)
def test_validated_values_error(attribute, given, message):
    with pytest.raises(UserException, match=message):
        attribute.validated_values(given, _POLICY_OBJECT_NAME)


@pytest.mark.parametrize("configured", [None, ("Enabled",)])
def test_boolean_controlled_values(configured):
    attribute = _string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN, controlled_values=configured)
    assert attribute.controlled_values == BP_BOOLEAN_CONTROLLED_VALUES


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"value_type": BP_VALUE_TYPE_CONTROLLED_VALUE}, "requires controlled values"),
        ({"value_type": BP_VALUE_TYPE_TEXT, "controlled_values": ("a",)}, "does not support controlled values"),
        (
            {"value_type": BP_VALUE_TYPE_CONTROLLED_VALUE, "controlled_values": ("Non-Clinical", "non clinical")},
            "differ only in case",
        ),
        (
            {"tag": "duration_of_access", "previous_tags": ("Duration Of Access",)},
            "previous_tags that are the same tag",
        ),
        ({"mandatory": True, "default": "a"}, "allows no default"),
    ],
)
def test_string_attribute_error(fields, message):
    with pytest.raises(ValidationError, match=message):
        _string_attribute(**fields)


def test_string_attributes_same_tag_error():
    with pytest.raises(ValidationError, match="tags that are the same when normalised"):
        BigpictureAttributesConfig(
            attributes=(_string_attribute("duration_of_access"),),
            set_attributes=(_string_attribute("type_of_access", previous_tags=("Duration Of Access",)),),
        )


def _policy_xml(*attributes: tuple[str, str], set_attributes: tuple[tuple[str, str], ...] = ()) -> str:
    """A Policy XML with the given attributes."""

    def string_attribute(tag: str, value: str) -> str:
        return f"<STRING_ATTRIBUTE><TAG>{tag}</TAG><VALUE>{value}</VALUE></STRING_ATTRIBUTE>"

    tags = "".join(string_attribute(tag, value) for tag, value in attributes)
    tags += "".join(
        f"<SET_ATTRIBUTE><TAG>{tag}s</TAG><VALUE>{string_attribute(tag, value)}</VALUE></SET_ATTRIBUTE>"
        for tag, value in set_attributes
    )
    return f'<POLICY alias="1"><DATASET_REF alias="1"/><ATTRIBUTES>{tags}</ATTRIBUTES></POLICY>'


def _policy_processor(
    *attributes: tuple[str, str], set_attributes: tuple[tuple[str, str], ...] = ()
) -> XmlObjectProcessor:
    return XmlObjectProcessor(BP_XML_OBJECT_CONFIG, _policy_xml(*attributes, set_attributes=set_attributes))


def _attributes_config(
    attributes: tuple[BigpictureStringAttribute, ...] = (),
    set_attributes: tuple[BigpictureStringAttribute, ...] = (),
) -> BigpictureAttributesConfig:
    return BigpictureAttributesConfig(attributes=attributes, set_attributes=set_attributes)


def test_read_attributes_previous_tag():
    config = _attributes_config(
        attributes=(_string_attribute("new", previous_tags=("old",)),),
    )

    attributes = read_attributes(_policy_processor(("old", "a")), config, _POLICY_OBJECT_NAME)
    assert [(attribute.tag, values) for attribute, values in attributes] == [("new", ["a"])]


def test_read_attributes_multiple_value_error():
    # Same tag twice (previous tag).
    config = _attributes_config(
        attributes=(_string_attribute("new", previous_tags=("old",)),),
    )

    with pytest.raises(UserException, match="may be given only once"):
        read_attributes(_policy_processor(("new", "a"), ("old", "b")), config, _POLICY_OBJECT_NAME)

    # Same tag twice (normalised tag).
    config = _attributes_config(attributes=(_string_attribute("duration_of_access"),))

    with pytest.raises(UserException, match="may be given only once"):
        read_attributes(
            _policy_processor(("duration_of_access", "a"), ("Duration Of Access", "b")), config, _POLICY_OBJECT_NAME
        )


@pytest.mark.parametrize("tag", ["duration_of_access", "Duration_Of_Access", "DURATION OF ACCESS", "durationOfAccess"])
def test_read_attributes_normalised(tag):
    config = _attributes_config(attributes=(_string_attribute("duration_of_access"),))

    attributes = read_attributes(_policy_processor((tag, "a")), config, _POLICY_OBJECT_NAME)
    assert [values for _, values in attributes] == [["a"]]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "  ",
        "N/A",
        "nil",
        "None",
        # Matched without case, punctuation or whitespace.
        "n/a.",
        "n / a",
        "N.A.",
        "NA",
        "Nil.",
    ],
)
def test_read_attributes_empty_string(value):
    config = _attributes_config(attributes=(_string_attribute("tag"),))

    given = read_attributes(_policy_processor(("tag", value)), config, _POLICY_OBJECT_NAME)

    assert [values for _, values in given] == [[]]


@pytest.mark.parametrize("value", ["n/a and more", "Nilsson", "nano", "0", "-"])
def test_read_attributes_value_resembling_empty_string(value):
    config = _attributes_config(attributes=(_string_attribute("tag"),))

    given = read_attributes(_policy_processor(("tag", value)), config, _POLICY_OBJECT_NAME)

    assert [values for _, values in given] == [[value]]


def test_read_attributes_string_with_whitespace():
    config = _attributes_config(attributes=(_string_attribute("tag"),))

    given = read_attributes(_policy_processor(("tag", "  a  ")), config, _POLICY_OBJECT_NAME)

    assert [values for _, values in given] == [["a"]]


def test_read_attributes_attributes_before_set_attributes():
    config = _attributes_config(
        attributes=(_string_attribute("tag"),),
        set_attributes=(_string_attribute("tag2", multiple=True),),
    )

    given = read_attributes(
        _policy_processor(("tag", "a"), set_attributes=(("tag2", "b"), ("tag2", "c"))), config, _POLICY_OBJECT_NAME
    )

    assert [(attribute.tag, values) for attribute, values in given] == [("tag", ["a"]), ("tag2", ["b", "c"])]
