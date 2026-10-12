import pytest
from pydantic import ValidationError

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.processors.xml.bigpicture import BP_XML_OBJECT_CONFIG_2, BigpictureVersion
from metadata_backend.api.processors.xml.processors import XmlObjectProcessor
from metadata_backend.api.services.submission.bigpicture_attributes import (
    BP_ATTRIBUTE_TYPE_STRING,
    BP_BOOLEAN_CONTROLLED_VALUES,
    BP_VALUE_TYPE_BOOLEAN,
    BP_VALUE_TYPE_CONTROLLED_VALUE,
    BP_VALUE_TYPE_TEXT,
    BigpictureAttributesConfig,
    BigpictureVersionedStringAttribute,
    normalised_value,
    read_attributes,
)

_POLICY_OBJECT_NAME = "Policy"

_V2 = BigpictureVersion.V2_0
_V3 = BigpictureVersion.V3_0


def _string_attribute(tag: str = "tag", **fields) -> BigpictureVersionedStringAttribute:
    return BigpictureVersionedStringAttribute(tag=tag, attribute_type=BP_ATTRIBUTE_TYPE_STRING, **fields)


def _controlled_attribute(*controlled_values, **fields) -> BigpictureVersionedStringAttribute:
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
        # A boolean attribute is treated as a controlled value with True and False values.
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["true"], ["True"]),
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["Yes"], ["True"]),
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["False"], ["False"]),
        (_string_attribute(value_type=BP_VALUE_TYPE_BOOLEAN), ["no"], ["False"]),
    ],
)
def test_validated_values(attribute, given, expected):
    assert attribute.validated_values(given, _POLICY_OBJECT_NAME, _V3) == expected


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
        attribute.validated_values(given, _POLICY_OBJECT_NAME, _V2)


def test_validated_values_version():
    """A controlled value given versions is allowed only in those versions."""

    # "Worldwide" is in every version, and "Only 2.0" only in 2.0.
    attribute = _controlled_attribute("Worldwide", {"value": "Only 2.0", "versions": ["2.0"]})

    # In 2.0, both are allowed.
    assert attribute.validated_values(["worldwide"], _POLICY_OBJECT_NAME, _V2) == ["Worldwide"]
    assert attribute.validated_values(["only 2.0"], _POLICY_OBJECT_NAME, _V2) == ["Only 2.0"]

    # In 3.0, only "Worldwide" is allowed, and the error lists only it.
    assert attribute.validated_values(["worldwide"], _POLICY_OBJECT_NAME, _V3) == ["Worldwide"]
    with pytest.raises(UserException, match=r"has value 'only 2.0' but must be one of: Worldwide\.$"):
        attribute.validated_values(["only 2.0"], _POLICY_OBJECT_NAME, _V3)


def test_validated_values_version_alias():
    """A controlled value of one version may be an alias of a controlled value of another."""

    attribute = _controlled_attribute(
        {"value": "Old", "versions": ["2.0"], "aliases": ["New"]},
        {"value": "New", "versions": ["3.0"]},
    )

    assert attribute.validated_values(["new"], _POLICY_OBJECT_NAME, _V2) == ["Old"]
    assert attribute.validated_values(["new"], _POLICY_OBJECT_NAME, _V3) == ["New"]
    with pytest.raises(UserException, match=r"has value 'old' but must be one of: New\.$"):
        attribute.validated_values(["old"], _POLICY_OBJECT_NAME, _V3)


def test_unknown_version_error():
    with pytest.raises(ValidationError, match="versions"):
        _string_attribute(versions=["1.0"])

    with pytest.raises(ValidationError, match="versions"):
        _controlled_attribute({"value": "Old", "versions": ["1.0"]})


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
            {
                "value_type": BP_VALUE_TYPE_CONTROLLED_VALUE,
                "controlled_values": ({"value": "Old", "aliases": ["New"]}, {"value": "New", "versions": ["3.0"]}),
            },
            "differ only in case, punctuation or whitespace in version 3.0",
        ),
        (
            {
                "versions": ["3.0"],
                "value_type": BP_VALUE_TYPE_CONTROLLED_VALUE,
                "controlled_values": ("Worldwide", {"value": "Old", "versions": ["2.0"]}),
            },
            "has controlled value 'Old' in versions the attribute is not in: 2.0",
        ),
        (
            {
                "value_type": BP_VALUE_TYPE_CONTROLLED_VALUE,
                "controlled_values": ({"value": "Old", "versions": ["2.0"]},),
            },
            "has no controlled values in version 3.0",
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
            set_attributes=(_string_attribute("Duration Of Access", versions=["2.0"]),),
        )


def test_string_attributes_same_alias_error():
    with pytest.raises(ValidationError, match="tags that are the same when normalised in version 2.0"):
        BigpictureAttributesConfig(
            attributes=(_string_attribute("duration_of_access"),),
            set_attributes=(_string_attribute("duration_of_use", aliases=["Duration Of Access"]),),
        )


def test_string_attributes_alias_of_another_version():
    """An alias of an attribute of one version may be the tag of an attribute of another."""

    BigpictureAttributesConfig(
        attributes=(
            _string_attribute("duration_of_use", versions=["2.0"], aliases=["duration_of_access"]),
            _string_attribute("duration_of_access", versions=["3.0"]),
        ),
        set_attributes=(),
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
    # BP.policy.xsd has not changed between 2.0 and 3.0.
    return XmlObjectProcessor(BP_XML_OBJECT_CONFIG_2, _policy_xml(*attributes, set_attributes=set_attributes))


def _attributes_config(
    attributes: tuple[BigpictureVersionedStringAttribute, ...] = (),
    set_attributes: tuple[BigpictureVersionedStringAttribute, ...] = (),
) -> BigpictureAttributesConfig:
    return BigpictureAttributesConfig(attributes=attributes, set_attributes=set_attributes)


def _versioned_attributes_config() -> BigpictureAttributesConfig:
    """Two mandatory attributes, one only in 2.0 and the other only in 3.0."""

    return _attributes_config(
        attributes=(
            _string_attribute("only_2_0", versions=["2.0"], mandatory=True),
            _string_attribute("only_3_0", versions=["3.0"], mandatory=True),
        )
    )


def test_read_attributes_version():
    """Only the attributes of the metadata object's version are validated and returned."""

    config = _versioned_attributes_config()

    # A 2.0 object passes without the mandatory 3.0 attribute, which is not returned.
    attributes = read_attributes(_policy_processor(("only_2_0", "a")), config, _POLICY_OBJECT_NAME, _V2)
    assert [(attribute.tag, values) for attribute, values in attributes] == [("only_2_0", ["a"])]

    # A 3.0 object passes without the mandatory 2.0 attribute, which is not returned.
    attributes = read_attributes(_policy_processor(("only_3_0", "a")), config, _POLICY_OBJECT_NAME, _V3)
    assert [(attribute.tag, values) for attribute, values in attributes] == [("only_3_0", ["a"])]


def test_read_attributes_version_error():
    """An attribute from another version is rejected."""

    config = _versioned_attributes_config()

    with pytest.raises(UserException, match="'only_3_0' is not in metadata standard version 2.0, only in 3.0"):
        read_attributes(_policy_processor(("only_3_0", "a")), config, _POLICY_OBJECT_NAME, _V2)

    with pytest.raises(UserException, match="'only_2_0' is not in metadata standard version 3.0, only in 2.0"):
        read_attributes(_policy_processor(("only_2_0", "a")), config, _POLICY_OBJECT_NAME, _V3)


def test_read_attributes_alias():
    """An attribute is read from its alias, which another version's attribute may have as its TAG."""

    config = _attributes_config(
        attributes=(
            _string_attribute("only_2_0", versions=["2.0"], mandatory=True, aliases=["only_3_0"]),
            _string_attribute("only_3_0", versions=["3.0"], mandatory=True),
        )
    )

    attributes = read_attributes(_policy_processor(("Only 3.0", "a")), config, _POLICY_OBJECT_NAME, _V2)
    assert [(attribute.tag, values) for attribute, values in attributes] == [("only_2_0", ["a"])]

    # The alias is not the other way round.
    with pytest.raises(UserException, match="'only_2_0' is not in metadata standard version 3.0, only in 2.0"):
        read_attributes(_policy_processor(("only_2_0", "a")), config, _POLICY_OBJECT_NAME, _V3)


def test_read_attributes_multiple_value_error():
    # Same tag twice (normalised tag).
    config = _attributes_config(attributes=(_string_attribute("duration_of_access"),))

    with pytest.raises(UserException, match="may be given only once"):
        read_attributes(
            _policy_processor(("duration_of_access", "a"), ("Duration Of Access", "b")),
            config,
            _POLICY_OBJECT_NAME,
            _V3,
        )


@pytest.mark.parametrize("tag", ["duration_of_access", "Duration_Of_Access", "DURATION OF ACCESS", "durationOfAccess"])
def test_read_attributes_normalised(tag):
    config = _attributes_config(attributes=(_string_attribute("duration_of_access"),))

    attributes = read_attributes(_policy_processor((tag, "a")), config, _POLICY_OBJECT_NAME, _V3)
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

    given = read_attributes(_policy_processor(("tag", value)), config, _POLICY_OBJECT_NAME, _V3)

    assert [values for _, values in given] == [[]]


@pytest.mark.parametrize("value", ["n/a and more", "Nilsson", "nano", "0", "-"])
def test_read_attributes_value_resembling_empty_string(value):
    config = _attributes_config(attributes=(_string_attribute("tag"),))

    given = read_attributes(_policy_processor(("tag", value)), config, _POLICY_OBJECT_NAME, _V3)

    assert [values for _, values in given] == [[value]]


def test_read_attributes_string_with_whitespace():
    config = _attributes_config(attributes=(_string_attribute("tag"),))

    given = read_attributes(_policy_processor(("tag", "  a  ")), config, _POLICY_OBJECT_NAME, _V3)

    assert [values for _, values in given] == [["a"]]


def test_read_attributes_attributes_before_set_attributes():
    config = _attributes_config(
        attributes=(_string_attribute("tag"),),
        set_attributes=(_string_attribute("tag2", multiple=True),),
    )

    given = read_attributes(
        _policy_processor(("tag", "a"), set_attributes=(("tag2", "b"), ("tag2", "c"))), config, _POLICY_OBJECT_NAME, _V3
    )

    assert [(attribute.tag, values) for attribute, values in given] == [("tag", ["a"]), ("tag2", ["b", "c"])]
