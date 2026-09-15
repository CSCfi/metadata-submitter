"""The Bigpicture policy metadata object and the REMS license it yields.

The policy's own attribute configuration, reading the policy, and creating the REMS
license from it. The attributes themselves are in bigpicture_attributes.py.
"""

# TODO: Make these modules a bigpicture package, to drop the prefix and split further.

from pathlib import Path
from typing import override

from jinja2 import Environment, Template, TemplateError, meta

from ....database.postgres.services.object import ObjectService
from ...exceptions import SystemException, UserException
from ...models.rems import RemsLicenseLocalization
from ...processors.xml.bigpicture import BP_POLICY_OBJECT_TYPE, BP_POLICY_PATH, BP_POLICY_SCHEMA, BP_XML_OBJECT_CONFIG
from ...processors.xml.processors import XmlDocumentsProcessor, XmlObjectProcessor
from ..rems import RemsLicenseProvider
from .bigpicture_attributes import (
    BigpictureAttributesConfig,
    BigpictureStringAttribute,
    load_bigpicture_attributes,
    normalise_string_attributes,
    normalised_value,
    read_attributes,
    read_string_attribute_values,
)

_BP_RESOURCE_DIR = Path(__file__).parent.parent.parent.parent / "resource" / "bigpicture"

_BP_POLICY_ATTRIBUTES_FILE = _BP_RESOURCE_DIR / "policy_attributes.yaml"
_BP_POLICY_ATTRIBUTES = load_bigpicture_attributes(_BP_POLICY_ATTRIBUTES_FILE)
_BP_POLICY_ATTRIBUTE_BY_TAG = {
    tag: attribute for attribute in _BP_POLICY_ATTRIBUTES.all_attributes for tag in attribute.tags
}

_BP_POLICY_OBJECT_NAME = "Policy"
_BP_POLICY_REMS_LICENSE_LANGUAGE = "en"

_BP_POLICY_TITLE_TAG = "title"

# The dataset type is the scope and the de-identification, separated by a slash.
# Only the scope is read.
_BP_POLICY_TYPE_OF_DATASET_TAG = "type_of_dataset"
_BP_POLICY_CLINICAL_SCOPE = "Clinical"
_BP_POLICY_NON_CLINICAL_SCOPE = "Non-Clinical"


def _configured_policy_attribute(tag: str) -> BigpictureStringAttribute:
    """The configured policy attribute with the given TAG.

    :param tag: The attribute TAG.
    :raises SystemException: if the attribute is not configured.
    :return: The attribute.
    """

    attribute = _BP_POLICY_ATTRIBUTE_BY_TAG.get(tag)
    if attribute is None:
        raise SystemException(f"Policy attribute '{tag}' must be configured in '{_BP_POLICY_ATTRIBUTES_FILE}'.")

    return attribute


_policy_title_attribute = _configured_policy_attribute(_BP_POLICY_TITLE_TAG)

if _policy_title_attribute.default is None:
    raise SystemException(
        f"Policy attribute '{_BP_POLICY_TITLE_TAG}' must be configured with a default "
        f"in '{_BP_POLICY_ATTRIBUTES_FILE}'."
    )

_policy_type_of_dataset_attribute = _configured_policy_attribute(_BP_POLICY_TYPE_OF_DATASET_TAG)

_BP_POLICY_SCOPES = {
    normalised_value(_BP_POLICY_CLINICAL_SCOPE): True,
    normalised_value(_BP_POLICY_NON_CLINICAL_SCOPE): False,
}


def policy_processor(processor: XmlDocumentsProcessor) -> XmlObjectProcessor:
    """Get the the processor of the policy metadata object in a submission.

    :param processor: The XML documents processor.
    :return: The policy object processor.
    """

    # The BP XML processor guarantees that we have one policy metadata object.
    policy_identifiers = processor.get_object_identifiers(BP_POLICY_SCHEMA)
    return processor.get_object_processor(BP_POLICY_SCHEMA, BP_POLICY_PATH, policy_identifiers[0].name)


def is_clinical_policy(processor: XmlObjectProcessor) -> bool:
    """
    Check if the policy is clinical.

    The 'type_of_dataset' TAG and the scope its value starts with are matched without
    case, punctuation or whitespace, the same way they are matched later during attribute
    normalisation and validation.

    :param processor: The policy object processor.
    :raises UserException: if 'type_of_dataset' is missing or the scope can't be extracted from it.
    :return: True if the policy is clinical.
    """

    # The field name should be descriptive as it is used in error messages.
    field_name = f"{_BP_POLICY_OBJECT_NAME} attribute '{_BP_POLICY_TYPE_OF_DATASET_TAG}'"

    values = read_string_attribute_values(processor, _policy_type_of_dataset_attribute)
    if not values:
        raise UserException(f"{field_name} is mandatory but was given no value.")

    value = values[0]

    # The scope is the text before the first slash.
    scope = _BP_POLICY_SCOPES.get(normalised_value(value.split("/", 1)[0]))
    if scope is None:
        raise UserException(
            f"{field_name} must start with '{_BP_POLICY_CLINICAL_SCOPE}' or "
            f"'{_BP_POLICY_NON_CLINICAL_SCOPE}' before '/', got: '{value}'"
        )

    return scope


_LICENSE_ENVIRONMENT = Environment(
    # A value is written as it is, not HTML escaped: '&' stays '&' rather than '&amp;'.
    autoescape=False,
    # The newline after a '{% %}' tag is dropped rather than written out as an empty line.
    trim_blocks=True,
    # Whitespace before a '{% %}' tag is dropped, rather than being written out as indentation.
    lstrip_blocks=True,
)


def _load_license_template(path: Path, attributes: BigpictureAttributesConfig) -> Template:
    """
    Read the REMS license Jinja template and check that it refers to the configured attributes.

    :param path: The license template file.
    :param attributes: The attributes the template may refer to.
    :raises SystemException: if the template cannot be read, is not a valid template, or
        refers to the attributes wrongly.
    :return: The license template.
    """

    try:
        source = path.read_text(encoding="utf-8")
        template = _LICENSE_ENVIRONMENT.from_string(source)
        referred = meta.find_undeclared_variables(_LICENSE_ENVIRONMENT.parse(source))
    except (OSError, TemplateError) as ex:
        raise SystemException(f"Invalid REMS license template '{path}'.") from ex

    if unknown := referred - attributes.tags:
        raise SystemException(
            f"REMS license template '{path}' refers to attributes that are not configured: "
            f"{', '.join(sorted(unknown))}."
        )

    if missing := attributes.mandatory_tags - referred:
        raise SystemException(
            f"REMS license template '{path}' leaves out mandatory attributes: {', '.join(sorted(missing))}."
        )

    return template


_BP_POLICY_LICENSE_TEMPLATE_FILE = _BP_RESOURCE_DIR / "policy_license.jinja"
_BP_POLICY_LICENSE_TEMPLATE = _load_license_template(_BP_POLICY_LICENSE_TEMPLATE_FILE, _BP_POLICY_ATTRIBUTES)


def normalise_policy_attributes(processor: XmlObjectProcessor) -> None:
    normalise_string_attributes(processor, _BP_POLICY_ATTRIBUTES)


def validate_policy_attributes(processor: XmlObjectProcessor) -> None:
    read_attributes(processor, _BP_POLICY_ATTRIBUTES, _BP_POLICY_OBJECT_NAME)


def create_policy_license(processor: XmlObjectProcessor) -> RemsLicenseLocalization:
    """
    Create the REMS license from the policy XML.

    :param processor: The XML documents processor.
    :raises UserException: if the Policy XML can't be used to create the REMS license.
    :return: The license title and text.
    """

    context = _license_context(read_attributes(processor, _BP_POLICY_ATTRIBUTES, _BP_POLICY_OBJECT_NAME))
    text = _BP_POLICY_LICENSE_TEMPLATE.render(context)
    return RemsLicenseLocalization(title=str(context[_BP_POLICY_TITLE_TAG]), textcontent=text.strip())


def _license_context(
    attribute_values: list[tuple[BigpictureStringAttribute, list[str]]],
) -> dict[str, str | list[str]]:
    """
    The attribute values the license template is rendered with, keyed by attribute tag.

    :param attribute_values: The attributes with the values the policy gives them.
    :return: The values of each attribute, a list of them if it allows multiple.
    """

    context: dict[str, str | list[str]] = {}
    for attribute, values in attribute_values:
        if not values and attribute.default is not None:
            values = [attribute.default]

        context[attribute.tag] = values if attribute.multiple else next(iter(values), "")

    return context


class BigpictureRemsLicenseProvider(RemsLicenseProvider):
    """Bigpicture REMS license is created from the policy metadata object."""

    def __init__(self, object_service: ObjectService) -> None:
        self._object_service = object_service

    @override
    async def get_license(self, submission_id: str) -> dict[str, RemsLicenseLocalization] | None:
        async for xml in self._object_service.get_xml_documents(submission_id, BP_POLICY_OBJECT_TYPE):
            localization = create_policy_license(XmlObjectProcessor(BP_XML_OBJECT_CONFIG, xml))
            return {_BP_POLICY_REMS_LICENSE_LANGUAGE: localization}

        return None
