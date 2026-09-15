# The expected REMS license text is held verbatim. REMS wraps a license itself, so the
# license is one line per paragraph and the expected text cannot be wrapped either.
# ruff: noqa: E501

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from metadata_backend.api.exceptions import SystemException, UserException
from metadata_backend.api.processors.xml.bigpicture import (
    BP_XML_OBJECT_CONFIG,
)
from metadata_backend.api.processors.xml.processors import XmlObjectProcessor, XmlStringDocumentsProcessor
from metadata_backend.api.services.submission.bigpicture import BP_FILES
from metadata_backend.api.services.submission.bigpicture_attributes import (
    BP_ATTRIBUTE_TYPE_STRING,
    BigpictureAttributesConfig,
    BigpictureStringAttribute,
)
from metadata_backend.api.services.submission.bigpicture_policy import (
    _BP_POLICY_ATTRIBUTES,
    _BP_POLICY_LICENSE_TEMPLATE_FILE,
    _BP_POLICY_REMS_LICENSE_LANGUAGE,
    BigpictureRemsLicenseProvider,
    _load_license_template,
    create_policy_license,
    is_clinical_policy,
    normalise_policy_attributes,
    policy_processor,
    validate_policy_attributes,
)
from metadata_backend.database.postgres.services.object import ObjectService

SUBMISSION_DIR = Path(__file__).parent.parent.parent.parent.parent / "test_files" / "xml" / "bigpicture"


def _string_attribute(tag: str = "tag", **fields) -> BigpictureStringAttribute:
    return BigpictureStringAttribute(tag=tag, attribute_type=BP_ATTRIBUTE_TYPE_STRING, **fields)


def _attributes_config(
    attributes: tuple[BigpictureStringAttribute, ...] = (),
    set_attributes: tuple[BigpictureStringAttribute, ...] = (),
) -> BigpictureAttributesConfig:
    return BigpictureAttributesConfig(attributes=attributes, set_attributes=set_attributes)


def _policy_xml(*attributes: tuple[str, str], set_attributes: tuple[tuple[str, str], ...] = ()) -> str:
    """A policy XML with the given attributes."""

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
    """A policy XML processor with the given attributes."""

    return XmlObjectProcessor(BP_XML_OBJECT_CONFIG, _policy_xml(*attributes, set_attributes=set_attributes))


def _example_policy_processor(**policy_values: str) -> XmlObjectProcessor:
    """The policy of the example Bigpicture document set.

    :param policy_values: New values for the named policy STRING_ATTRIBUTE tags.
    """

    processor = policy_processor(_example_documents_processor())

    for tag, value in policy_values.items():
        element = processor.xml.getroot().find(f'.//STRING_ATTRIBUTE[TAG="{tag}"]/VALUE')
        assert element is not None, f"'{tag}' is not a STRING_ATTRIBUTE of the example policy"
        element.text = value

    return processor


def _example_policy_xml() -> str:
    """The XML of the example policy, as the object service stores it."""

    return XmlObjectProcessor.write_xml(_example_policy_processor().xml)


def _example_documents_processor() -> XmlStringDocumentsProcessor:
    """The example Bigpicture documents."""

    documents = [
        (SUBMISSION_DIR / name).read_text(encoding="utf-8") for name in BP_FILES if (SUBMISSION_DIR / name).is_file()
    ]

    return XmlStringDocumentsProcessor(BP_XML_OBJECT_CONFIG, documents)


_EXPECTED_REMS_LICENSE_TITLE = "HUS policy"
_EXPECTED_REMS_LICENSE_TEXT = """Policy text: DISCLAIMER:
The use and sharing of Bigpicture data is dictated by the Bigpicture Data Sharing Agreement. The Policy Text comprises a concise overview thereof, however, only the official and formally signed contractual documents have a binding value.
Clause 6. [Obligations of the Data Users]
Each Data User processing Data must:
- Comply with applicable Data Protection Legislation.
- Follow recognized ethical standards for scientific research.

Type of dataset: Clinical/Anonymized

Defined research question required: True

Legal basis for sharing the data: Informed consent form (Biobank consents), Finnish biobank act

Use restrictions defined in informed consent form: A placeholder value.

Custom use restrictions: A placeholder value.

Allowed geographical distribution: Countries with GDPR adequacy (including UK)

Duration of access: Limited to the IMI Bigpicture project term

Type of access: Direct access

Allowed use: A placeholder value.

Required Bigpicture acknowledgements: This project has received funding from the Innovative Medicines Initiative 2 Joint Undertaking under grant agreement No 945358. This Joint Undertaking receives support from the European Union’s Horizon 2020 research and innovation program and EFPIA

Required custom acknowledgement: The samples/data used for the research were obtained from Helsinki Biobank. We thank all study participants for their generous participation in Helsinki Biobank.

Required citation: A placeholder value.

If the dataset is central to the study’s conclusion or the Data Contributor provides substantial contributions in interpretation or data analysis, the Data Contributor should be offered the option to co-author any dissemination.

Terms of use version: 2026-01-22T15:53:29.760746"""


_EXPECTED_COAUTHORSHIP_LICENSE_TEXT = """If the dataset is central to the study’s conclusion or the Data Contributor provides substantial contributions in interpretation or data analysis, the Data Contributor should be offered the option to co-author any dissemination."""


def _mock_object_service(*documents: str) -> ObjectService:
    """A mock object service whose get_xml_documents yields the given XML documents."""

    async def get_xml_documents(
        submission_id: str, object_type: str | Sequence[str] | None = None
    ) -> AsyncIterator[str]:
        for document in documents:
            yield document

    return cast(ObjectService, SimpleNamespace(get_xml_documents=get_xml_documents))


@pytest.mark.parametrize(("policy", "clinical"), [("policy_clinical.xml", True), ("policy_non_clinical.xml", False)])
def test_is_clinical_policy(policy, clinical):
    processor = XmlObjectProcessor(BP_XML_OBJECT_CONFIG, SUBMISSION_DIR / "single" / policy)

    assert is_clinical_policy(processor) == clinical


@pytest.mark.parametrize(
    ("tag", "value", "clinical"),
    [
        # The TAG is matched without case, punctuation or whitespace.
        ("Type of dataset", "Clinical/Anonymized", True),
        ("TYPE_OF_DATASET", "Non-Clinical/Obscured", False),
        # The scope is matched without case, punctuation or whitespace.
        ("type_of_dataset", "clinical/Anonymized", True),
        ("type_of_dataset", "non clinical / obscured", False),
        ("type_of_dataset", "NONCLINICAL/Obscured", False),
    ],
)
def test_is_clinical_policy_normalisation(tag, value, clinical):
    assert is_clinical_policy(_policy_processor((tag, value))) is clinical


def test_is_clinical_policy_error():
    processor = _policy_processor(("type_of_dataset", "Neither/Anonymized"))

    with pytest.raises(UserException, match="must start with 'Clinical' or 'Non-Clinical'"):
        is_clinical_policy(processor)


def test_is_clinical_policy_missing():
    processor = _policy_processor(("policy_text", "A policy."))

    with pytest.raises(UserException, match="is mandatory but was given no value"):
        is_clinical_policy(processor)


@pytest.mark.parametrize(
    ("tag", "value", "expected_tag", "expected_value"),
    [
        # A value is replaced by the controlled value it matches.
        ("type_of_dataset", "non clinical / obscured", "type_of_dataset", "Non-Clinical/Obscured"),
        ("duration_of_access", "UNLIMITED  TIME", "duration_of_access", "Unlimited time"),
        # A tag is replaced by the configured one, whether it differs in spelling or version.
        ("Type_Of_Dataset", "Clinical/Anonymized", "type_of_dataset", "Clinical/Anonymized"),
        ("duration_of_use", "Unlimited time", "duration_of_access", "Unlimited time"),
        # A tag that is no attribute is left alone, as nothing here knows what it is.
        ("Not_An_Attribute", "a value", "Not_An_Attribute", "a value"),
        # A value matching no controlled value is left for the validation to report.
        ("type_of_dataset", "Something else", "type_of_dataset", "Something else"),
    ],
)
def test_normalise_policy_attributes(tag, value, expected_tag, expected_value):
    processor = _policy_processor((tag, value))
    normalise_policy_attributes(processor)
    elements = processor.xml.getroot().findall("./ATTRIBUTES/STRING_ATTRIBUTE")
    assert [(element.findtext("TAG"), element.findtext("VALUE")) for element in elements] == [
        (expected_tag, expected_value)
    ]


def test_validate_policy_attributes():
    validate_policy_attributes(_example_policy_processor())


@pytest.mark.parametrize(
    ("values", "message"),
    [
        # An invalid controlled value.
        ({"type_of_dataset": "Not A Real Scope"}, "must be one of"),
        # An invalid boolean value.
        ({"coauthorship": "Maybe"}, "must be one of"),
        # A mandatory attribute given no value.
        ({"policy_text": ""}, "is mandatory"),
    ],
)
def test_validate_policy_attributes_error(values, message):
    with pytest.raises(UserException, match=message):
        validate_policy_attributes(_example_policy_processor(**values))


@pytest.mark.parametrize(
    ("values", "title"),
    [
        ({}, _EXPECTED_REMS_LICENSE_TITLE),
        # Default title.
        ({"title": ""}, "Terms of Use"),
    ],
)
def test_create_policy_license(values, title):
    localization = create_policy_license(_example_policy_processor(**values))

    assert localization.title == title
    assert localization.textcontent == _EXPECTED_REMS_LICENSE_TEXT


def test_create_policy_license_missing_mandatory_attribute():
    with pytest.raises(UserException, match="'policy_text' is mandatory"):
        create_policy_license(_example_policy_processor(policy_text=""))


def test_create_policy_license_coauthorship():
    text = create_policy_license(_example_policy_processor(coauthorship="False")).textcontent
    assert _EXPECTED_COAUTHORSHIP_LICENSE_TEXT not in text
    assert text == _EXPECTED_REMS_LICENSE_TEXT.replace(f"\n\n{_EXPECTED_COAUTHORSHIP_LICENSE_TEXT}", "")


def test_load_license_template():
    assert _load_license_template(_BP_POLICY_LICENSE_TEMPLATE_FILE, _BP_POLICY_ATTRIBUTES) is not None


@pytest.mark.parametrize(
    ("source", "attributes", "message"),
    [
        # Refers to an attribute that is not configured.
        (
            "Misspelled: {{ policy_txet }}\n",
            (_string_attribute("policy_text"),),
            "not configured: policy_txet",
        ),
        # Leaves out a mandatory attribute, which would be validated and then written nowhere.
        (
            "Policy text: {{ policy_text }}\n",
            (_string_attribute("policy_text"), _string_attribute("terms_of_use_version", mandatory=True)),
            "leaves out mandatory attributes: terms_of_use_version",
        ),
        # Not a valid Jinja template.
        (
            "{% if policy_text %}unclosed\n",
            (_string_attribute("policy_text"),),
            "Invalid REMS license template",
        ),
    ],
)
def test_load_license_template_error(tmp_path, source, attributes, message):
    path = tmp_path / "policy_license.jinja"
    path.write_text(source, encoding="utf-8")

    with pytest.raises(SystemException, match=message):
        _load_license_template(path, _attributes_config(attributes=attributes))


def test_load_license_template_missing_file_error(tmp_path):
    with pytest.raises(SystemException, match="Invalid REMS license template"):
        _load_license_template(tmp_path / "no_such_template.jinja", _attributes_config())


async def test_bigpicture_rems_license_provider_reads_the_policy():
    provider = BigpictureRemsLicenseProvider(_mock_object_service(_example_policy_xml()))

    localizations = await provider.get_license("test")

    assert localizations is not None
    assert list(localizations) == [_BP_POLICY_REMS_LICENSE_LANGUAGE]
    assert localizations[_BP_POLICY_REMS_LICENSE_LANGUAGE].title == _EXPECTED_REMS_LICENSE_TITLE
    assert localizations[_BP_POLICY_REMS_LICENSE_LANGUAGE].textcontent == _EXPECTED_REMS_LICENSE_TEXT


async def test_bigpicture_rems_license_provider_without_policy():
    provider = BigpictureRemsLicenseProvider(_mock_object_service())

    assert await provider.get_license("test") is None
