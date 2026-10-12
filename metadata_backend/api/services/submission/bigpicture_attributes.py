"""Bigpicture metadata object attributes.

Their configuration, and reading and writing them to the metadata object XML.
"""

# TODO: Make these modules a bigpicture package, to drop the prefix and split further.

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, override

import yaml
from lxml.etree import _Element as Element  # noqa
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from ...exceptions import SystemException, UserException
from ...processors.xml.bigpicture import BigpictureVersion
from ...processors.xml.processors import XmlObjectProcessor

BP_STRING_ATTRIBUTE_TRUE = "True"
BP_STRING_ATTRIBUTE_FALSE = "False"
BP_STRING_ATTRIBUTE_EMPTY = frozenset({"n/a", "nil", "none"})

_BP_STRING_ATTRIBUTE_XPATH = "./ATTRIBUTES/STRING_ATTRIBUTE"
_BP_SET_STRING_ATTRIBUTE_XPATH = "./ATTRIBUTES/SET_ATTRIBUTE/VALUE/STRING_ATTRIBUTE"


def normalised_value(value: str) -> str:
    """
    Return the normalised form of the value.

    Normalised without case, punctuation or whitespace.

    :param value: The value.
    :return: The normalised form of tje value.
    """

    return "".join(character for character in value.lower() if character.isalnum())


# The values saying an attribute has none, in the form they are matched in.
_BP_NORMALISED_STRING_ATTRIBUTE_EMPTY = frozenset(normalised_value(value) for value in BP_STRING_ATTRIBUTE_EMPTY)


BigpictureAttributeType = Literal["string"]
BP_ATTRIBUTE_TYPE_STRING: BigpictureAttributeType = "string"

BigpictureValueType = Literal["text", "controlledValue", "boolean"]
BP_VALUE_TYPE_TEXT: BigpictureValueType = "text"
BP_VALUE_TYPE_CONTROLLED_VALUE: BigpictureValueType = "controlledValue"
BP_VALUE_TYPE_BOOLEAN: BigpictureValueType = "boolean"


class BigpictureVersioned(BaseModel):
    """An attribute or controlled value defined in some or all metadata standard versions.

    :param versions: The metadata standard versions it is defined in, all if none.
    """

    # Reject unknown keys to report configuration errors.
    model_config = ConfigDict(frozen=True, extra="forbid")

    versions: tuple[BigpictureVersion, ...] = ()

    def is_in(self, version: BigpictureVersion) -> bool:
        """
        Check whether it is defined in the given metadata standard version.

        Without listed versions, it is defined in every version.

        :param version: The metadata standard version.
        :return: True if it is defined in the version.
        """

        return not self.versions or version in self.versions


class BigpictureVersionedAttribute(BigpictureVersioned):
    """A Bigpicture metadata object attribute, and the metadata standard versions it belongs to.

    :param tag: The attribute TAG.
    :param aliases: Other TAGs the attribute may be given with.
    :param attribute_type: The kind of Bigpicture XML attribute the value is read from.
    :param value_type: The kind of value read from the Bigpicture XML element.
    :param mandatory: Whether the attribute is mandatory and must have a value.
    :param multiple: Whether the attribute may occur more than once.
    """

    tag: str
    aliases: tuple[str, ...] = ()
    attribute_type: BigpictureAttributeType
    value_type: BigpictureValueType = BP_VALUE_TYPE_TEXT
    mandatory: bool = False
    multiple: bool = False

    @property
    def normalised_tags(self) -> tuple[str, ...]:
        """Return the normalised TAG and its aliases, the TAG first."""

        return tuple(normalised_value(tag) for tag in (self.tag, *self.aliases))

    def validated_values(self, values: list[str], object_name: str, version: BigpictureVersion) -> list[str]:
        """
        Validate and return the attribute values.

        :param values: The attribute values.
        :param object_name: The metadata object the attribute is read from, named as the
            submitter knows it, for informative user errors.
        :param version: The metadata standard version of the metadata object.
        :raises UserException: if the attribute values do not pass validation.
        :return: The validated attribute values.
        """

        if self.mandatory and not values:
            raise UserException(f"{object_name} attribute '{self.tag}' is mandatory but was given no value.")

        if not self.multiple and len(values) > 1:
            raise UserException(
                f"{object_name} attribute '{self.tag}' was given {len(values)} times but may be given only once."
            )

        return values


class BigpictureVersionedControlledValue(BigpictureVersioned):
    """A controlled value of a Bigpicture metadata object attribute, and the metadata standard
    versions it belongs to.

    :param value: The controlled value.
    :param aliases: Other ways of writing the controlled value.
    """

    value: str
    aliases: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def expand_plain_value(cls, data: Any) -> Any:
        """Expand a plain string into a controlled value."""

        return {"value": data} if isinstance(data, str) else data

    @property
    def controlled_values(self) -> tuple[str, ...]:
        """Return the controlled value and its aliases, the controlled value first."""

        return self.value, *self.aliases

    @property
    def normalised_controlled_values(self) -> tuple[str, ...]:
        """Return the normalised controlled value and its aliases, the controlled value first."""

        return tuple(normalised_value(value) for value in self.controlled_values)


BP_BOOLEAN_CONTROLLED_VALUES = (
    BigpictureVersionedControlledValue(value=BP_STRING_ATTRIBUTE_TRUE, aliases=("yes",)),
    BigpictureVersionedControlledValue(value=BP_STRING_ATTRIBUTE_FALSE, aliases=("no",)),
)


class BigpictureVersionedStringAttribute(BigpictureVersionedAttribute):
    """A Bigpicture STRING_ATTRIBUTE.

    :param controlled_values: The controlled attribute values if any.
    :param default: The default attribute value.
    """

    controlled_values: tuple[BigpictureVersionedControlledValue, ...] | None = None
    default: str | None = None

    @model_validator(mode="before")
    @classmethod
    def expand_boolean_values(cls, data: Any) -> Any:
        """Expand a boolean value type into its controlled values."""

        if not isinstance(data, dict) or data.get("value_type") != BP_VALUE_TYPE_BOOLEAN:
            return data

        return {**data, "controlled_values": BP_BOOLEAN_CONTROLLED_VALUES}

    @model_validator(mode="after")
    def check_controlled_values(self) -> "BigpictureVersionedStringAttribute":
        """Check that the controlled values are provided only for controlled value attributes."""

        # A boolean value is also assigned controlled values.
        if self.value_type in (BP_VALUE_TYPE_CONTROLLED_VALUE, BP_VALUE_TYPE_BOOLEAN):
            if not self.controlled_values:
                raise ValueError(f"Attribute '{self.tag}' of value type '{self.value_type}' requires controlled values")

            # A controlled value of one version may be an alias of a controlled value of another.
            for version in BigpictureVersion:
                normalised = [
                    value
                    for controlled in self.controlled_values
                    if controlled.is_in(version)
                    for value in controlled.normalised_controlled_values
                ]
                if len(set(normalised)) != len(normalised):
                    raise ValueError(
                        f"Attribute '{self.tag}' has controlled values that differ only in case, punctuation or "
                        f"whitespace in version {version}"
                    )

        elif self.controlled_values is not None:
            raise ValueError(
                f"Attribute '{self.tag}' of value type '{self.value_type}' does not support controlled values"
            )

        return self

    @model_validator(mode="after")
    def check_controlled_value_versions(self) -> "BigpictureVersionedStringAttribute":
        """Check that every controlled value is in the attribute's versions, and that every version of
        the attribute has a controlled value."""

        for controlled in self.controlled_values or ():
            if other_versions := [version for version in controlled.versions if not self.is_in(version)]:
                raise ValueError(
                    f"Attribute '{self.tag}' has controlled value '{controlled.value}' in versions the attribute "
                    f"is not in: {', '.join(other_versions)}"
                )

        if self.controlled_values:
            for version in BigpictureVersion:
                if self.is_in(version) and not any(controlled.is_in(version) for controlled in self.controlled_values):
                    raise ValueError(f"Attribute '{self.tag}' has no controlled values in version {version}")

        return self

    @model_validator(mode="after")
    def check_default(self) -> "BigpictureVersionedStringAttribute":
        """Check that a mandatory attribute has no default."""

        if self.mandatory and self.default is not None:
            raise ValueError(f"Mandatory attribute '{self.tag}' allows no default")

        return self

    def matched_controlled_value(self, value: str, version: BigpictureVersion) -> str | None:
        """
        Return the controlled value that matches the given value after normalisation.

        Returns None if the value does not match any controlled value of the version, or its
        aliases, after normalisation.

        :param value: The value read from the metadata object.
        :param version: The metadata standard version of the metadata object.
        :return: The controlled value it matches, or None if it matches none.
        """

        normalised = normalised_value(value)
        for controlled in self.controlled_values or ():
            if controlled.is_in(version) and normalised in controlled.normalised_controlled_values:
                return controlled.value

        return None

    @override
    def validated_values(self, values: list[str], object_name: str, version: BigpictureVersion) -> list[str]:
        """
        Validate and replace attribute values.

        Controlled values are matched after normalisation, and changed to match their
        official value.

        :param values: The attribute values.
        :param object_name: The metadata object the attribute is read from, named as the
            submitter knows it, for informative user errors.
        :param version: The metadata standard version of the metadata object.
        :raises UserException: if the attribute values do not pass validation.
        :return: The validated attribute values.
        """

        values = super().validated_values(values, object_name, version)

        if self.controlled_values is None:
            return values

        matched_values = []
        for value in values:
            matched = self.matched_controlled_value(value, version)
            if matched is None:
                allowed = [controlled.value for controlled in self.controlled_values if controlled.is_in(version)]
                raise UserException(
                    f"{object_name} attribute '{self.tag}' has value '{value}' but must be one of: "
                    f"{', '.join(allowed)}."
                )
            matched_values.append(matched)

        return matched_values


class BigpictureAttributesConfig(BaseModel):
    """Bigpicture attributes configuration file."""

    # Reject unknown keys to report configuration errors.
    model_config = ConfigDict(extra="forbid")

    attributes: tuple[BigpictureVersionedStringAttribute, ...]
    set_attributes: tuple[BigpictureVersionedStringAttribute, ...]

    @property
    def all_attributes(self) -> tuple[BigpictureVersionedStringAttribute, ...]:
        return *self.attributes, *self.set_attributes

    @property
    def tags(self) -> set[str]:
        """Return the tag of every attribute the file declares."""

        return {attribute.tag for attribute in self.all_attributes}

    @property
    def mandatory_tags(self) -> set[str]:
        """Return the tag of every attribute that must be given a value in its versions."""

        return {attribute.tag for attribute in self.all_attributes if attribute.mandatory}

    @model_validator(mode="after")
    def check_tags(self) -> "BigpictureAttributesConfig":
        """Check that no two attributes have the same tag, or alias, in the same version.

        An alias of an attribute of one version may be the tag of an attribute of another.
        """

        for version in BigpictureVersion:
            tags: dict[str, list[str]] = {}
            for attribute in self.all_attributes:
                if attribute.is_in(version):
                    for tag in (attribute.tag, *attribute.aliases):
                        tags.setdefault(normalised_value(tag), []).append(tag)

            repeated = [same for same in tags.values() if len(same) > 1]
            if repeated:
                raise ValueError(
                    f"Attributes have tags that are the same when normalised in version {version}: "
                    f"{'; '.join(', '.join(same) for same in repeated)}"
                )

        return self


def _string_attributes_by_xpath(
    attributes: BigpictureAttributesConfig,
) -> tuple[tuple[str, tuple["BigpictureVersionedStringAttribute", ...]], ...]:
    """
    The STRING_ATTRIBUTE attributes grouped by the XPath their values are read from.

    Each group has the attributes of every version. A TAG that is not configured is
    ignored.

    :param attributes: The attributes the metadata object declares.
    :return: Each XPath with the attributes read from it.
    """

    return (
        (_BP_STRING_ATTRIBUTE_XPATH, attributes.attributes),
        (_BP_SET_STRING_ATTRIBUTE_XPATH, attributes.set_attributes),
    )


def load_bigpicture_attributes(path: Path) -> BigpictureAttributesConfig:
    """Load a Bigpicture attributes configuration file."""

    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return BigpictureAttributesConfig.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as ex:
        raise SystemException(f"Invalid Bigpicture attributes file '{path}'.") from ex


def is_string_attribute_value(value: str) -> bool:
    """
    Check if a string attribute has a value.

    A value saying the attribute has none is matched without case, punctuation or
    whitespace.

    :param value: The value read from the metadata object.
    :return: True if the attribute has a value.
    """

    value = value.strip()
    return bool(value) and normalised_value(value) not in _BP_NORMALISED_STRING_ATTRIBUTE_EMPTY


def _string_elements_by_normalised_tag(processor: XmlObjectProcessor, xpath: str) -> dict[str, list[Element]]:
    """
    Every STRING_ATTRIBUTE element of a metadata object, by the normalised form of its TAG.

    :param processor: The metadata object processor.
    :param xpath: The XPath to the STRING_ATTRIBUTE elements.
    :return: The elements, by the normalised form of the TAG each of them gives.
    """

    elements: dict[str, list[Element]] = {}
    for element in processor.xml.getroot().xpath(xpath):
        elements.setdefault(normalised_value(element.findtext("TAG") or ""), []).append(element)
    return elements


def _string_attribute_values(element: Element) -> list[str]:
    """Return the values for one STRING_ATTRIBUTE element."""

    return [value.text for value in element.iterfind("VALUE") if value.text]


def _string_attribute_tag_values(elements: dict[str, list[Element]], normalised_tags: Iterable[str]) -> list[str]:
    """
    The values STRING_ATTRIBUTE elements with the given TAGs are given, without validating them.

    :param elements: The metadata object's STRING_ATTRIBUTE elements, by normalised TAG.
    :param normalised_tags: The normalised TAGs to read.
    :return: The values given, stripped, without those giving no value.
    """

    return [
        value.strip()
        for tag in normalised_tags
        for element in elements.get(tag, [])
        for value in _string_attribute_values(element)
        if is_string_attribute_value(value)
    ]


def read_string_attribute_values(
    processor: XmlObjectProcessor, attribute: BigpictureVersionedStringAttribute
) -> list[str]:
    """
    The values one attribute of ATTRIBUTES/STRING_ATTRIBUTE is given, as they are given.

    The TAG, or an alias, is matched without case, punctuation or whitespace, so the
    attribute is found whether or not the metadata object has been normalised. The values are
    returned unvalidated, for a caller reading one attribute rather than validating
    the metadata object.

    :param processor: The metadata object processor.
    :param attribute: The attribute to read.
    :return: The values given, stripped, without those giving no value.
    """

    elements = _string_elements_by_normalised_tag(processor, _BP_STRING_ATTRIBUTE_XPATH)
    return _string_attribute_tag_values(elements, attribute.normalised_tags)


def normalise_string_attributes(
    processor: XmlObjectProcessor, attributes: BigpictureAttributesConfig, version: BigpictureVersion
) -> None:
    """
    Replace each TAG and STRING_ATTRIBUTE controlled value in the metadata object XML with the
    one it matches.

    A TAG and a controlled value, or their aliases, are matched without case, punctuation or
    whitespace.

    :param processor: The metadata object processor.
    :param attributes: The attributes the metadata object declares.
    :param version: The metadata standard version of the metadata object.
    """

    for xpath, xpath_attributes in _string_attributes_by_xpath(attributes):
        elements = _string_elements_by_normalised_tag(processor, xpath)

        for attribute in xpath_attributes:
            if not attribute.is_in(version):
                continue
            for tag in attribute.normalised_tags:
                for element in elements.get(tag, []):
                    _normalise_tag(element, attribute)
                    _normalise_values(element, attribute, version)


def _normalise_tag(element: Element, attribute: BigpictureVersionedStringAttribute) -> None:
    """Replace the TAG of a STRING_ATTRIBUTE element with the TAG the attribute has.

    :param element: The STRING_ATTRIBUTE element.
    :param attribute: The attribute the element gives.
    """

    tag = element.find("TAG")
    if tag is not None and tag.text != attribute.tag:
        tag.text = attribute.tag


def _normalise_values(
    element: Element, attribute: BigpictureVersionedStringAttribute, version: BigpictureVersion
) -> None:
    """
    Replace each VALUE of a STRING_ATTRIBUTE element with the controlled value it matches.

    An attribute whose values are not controlled has nothing to match against, so its
    values are left as they are.

    :param element: The STRING_ATTRIBUTE element.
    :param attribute: The attribute the element gives.
    :param version: The metadata standard version of the metadata object.
    """

    if attribute.controlled_values is None:
        return

    for value in element.iterfind("VALUE"):
        text = (value.text or "").strip()
        if not is_string_attribute_value(text):
            continue

        matched = attribute.matched_controlled_value(text, version)
        if matched is not None and matched != value.text:
            value.text = matched


def read_attributes(
    processor: XmlObjectProcessor,
    attributes: BigpictureAttributesConfig,
    object_name: str,
    version: BigpictureVersion,
) -> list[tuple[BigpictureVersionedStringAttribute, list[str]]]:
    """
    Read and validate every attribute a Bigpicture metadata object declares in its version.

    :param processor: The metadata object processor.
    :param attributes: The attributes the metadata object declares.
    :param object_name: The metadata object, named as the submitter knows it, for
        informative user errors.
    :param version: The metadata standard version of the metadata object.
    :raises UserException: if any of the values do not pass validation, or an attribute of
        another version is given.
    :return: The attributes of the version with their values.
    """

    attributes_expected_version = []
    attributes_different_version = []

    for xpath, xpath_attributes in _string_attributes_by_xpath(attributes):
        elements = _string_elements_by_normalised_tag(processor, xpath)

        # The TAGs and aliases of this version's attributes.
        version_tags = {
            tag for attribute in xpath_attributes if attribute.is_in(version) for tag in attribute.normalised_tags
        }

        for attribute in xpath_attributes:
            if attribute.is_in(version):
                attributes_expected_version.append(
                    (attribute, _string_attribute_tag_values(elements, attribute.normalised_tags))
                )
            else:
                tags = [tag for tag in attribute.normalised_tags if tag not in version_tags]
                attributes_different_version.append((attribute, _string_attribute_tag_values(elements, tags)))

    # Reject attributes belonging to another version.
    for attribute, values in attributes_different_version:
        if values:
            raise UserException(
                f"{object_name} attribute '{attribute.tag}' is not in metadata standard version {version}, "
                f"only in {', '.join(attribute.versions)}."
            )

    # Validate the attribute values.
    return [
        (attribute, attribute.validated_values(values, object_name, version))
        for attribute, values in attributes_expected_version
    ]
