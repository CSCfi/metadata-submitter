"""Publish service."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic_string_url import AnyUrl

from ..exceptions import SystemException, UserException
from ..models.datacite import Subject
from ..models.submission import SubmissionWorkflow


class PublishSource(Enum):
    """The source for publishing submissions."""

    SUBMISSION = "submission"  # Publish using the submission document.
    OBJECT = "object"  # Publish using a metadata object.


class PublishConfig(BaseModel):
    """Service configuration for publishing submissions."""

    model_config = ConfigDict(frozen=True)

    source: PublishSource
    object_type: str | None = None

    use_pid_service: bool
    use_datacite_service: bool
    use_rems_service: bool
    use_metax_service: bool
    use_bp_beacon_service: bool

    require_okm_field_of_science: bool = False  # Require OKM field of science: https://finto.fi/okm-tieteenala/en/

    @model_validator(mode="after")
    def model_validator_object_type(self) -> "PublishConfig":
        """Check that object type is defined."""
        if self.source == PublishSource.OBJECT and not self.object_type:
            raise ValueError("object_type must be defined when source is 'object'")
        return self


SD_PUBLISH_CONFIG = PublishConfig(
    source=PublishSource.SUBMISSION,
    use_pid_service=True,
    use_datacite_service=False,
    use_rems_service=True,
    use_metax_service=True,
    use_bp_beacon_service=False,
    require_okm_field_of_science=True,
)

BP_PUBLISH_CONFIG = PublishConfig(
    source=PublishSource.OBJECT,
    object_type="dataset",
    use_pid_service=False,
    use_datacite_service=True,
    use_rems_service=True,
    use_metax_service=False,
    use_bp_beacon_service=True,
)

FEGA_PUBLISH_CONFIG = PublishConfig(
    source=PublishSource.OBJECT,
    object_type="dataset",
    use_pid_service=True,
    use_datacite_service=False,
    use_rems_service=True,
    use_metax_service=True,
    use_bp_beacon_service=False,
)


def get_publish_config(workflow: SubmissionWorkflow) -> PublishConfig:
    """
    Return the service configuration to use when publishing.

    :param workflow: the submission workflow
    :return: the service configuration.
    """
    if workflow == SubmissionWorkflow.SD:
        return SD_PUBLISH_CONFIG

    if workflow == SubmissionWorkflow.BP:
        return BP_PUBLISH_CONFIG

    if workflow == SubmissionWorkflow.FEGA:
        return FEGA_PUBLISH_CONFIG

    raise SystemException(f"Unsupported publish workflow: {workflow.value}")


OKM_SUBJECT_CODE = [
    "1",  # Natural sciences
    "111",  # Mathematics
    "112",  # Statistics and probability
    "113",  # Computer and information sciences
    "114",  # Physical sciences
    "115",  # Astronomy, Space science
    "116",  # Chemical sciences
    "1171",  # Geosciences
    "1172",  # Environmental sciences
    "1181",  # Ecology, evolutionary biology
    "1182",  # Biochemistry, cell and molecular biology
    "1183",  # Plant biology, microbiology, virology
    "1184",  # Genetics, developmental biology, physiology
    "119",  # Other natural sciences
    "2",  # Engineering and technology
    "211",  # Architecture
    "212",  # Civil and Construction engineering
    "213",  # Electronic, automation and communications engineering, electronics
    "214",  # Mechanical engineering
    "215",  # Chemical engineering
    "216",  # Materials engineering
    "217",  # Medical engineering
    "218",  # Environmental engineering
    "219",  # Environmental biotechnology
    "220",  # Industrial biotechnology
    "221",  # Nano-technology
    "222",  # Other engineering and technologies
    "3",  # Medical and health sciences
    "3111",  # Biomedicine
    "3112",  # Neurosciences
    "3121",  # Internal medicine
    "3122",  # Cancers
    "3123",  # Gynaecology and paediatrics
    "3124",  # Neurology and psychiatry
    "3125",  # Otorhinolaryngology, ophthalmology
    "3126",  # Surgery, anesthesiology, intensive care, radiology
    "313",  # Dentistry
    "3141",  # Health care science
    "3142",  # Public health care science, environmental and occupational health
    "315",  # Sport and fitness sciences
    "316",  # Nursing
    "317",  # Pharmacy
    "318",  # Medical biotechnology
    "319",  # Forensic science and other medical sciences
    "4",  # Agriculture and forestry
    "4111",  # Agronomy
    "4112",  # Forestry
    "412",  # Animal science, dairy science
    "413",  # Veterinary science
    "414",  # Agricultural biotechnology
    "415",  # Other agricultural sciences
    "5",  # Social sciences
    "511",  # Economics
    "512",  # Business and management
    "513",  # Law
    "5141",  # Sociology
    "5142",  # Social policy
    "515",  # Psychology
    "516",  # Educational sciences
    "517",  # Political science
    "518",  # Media and communications
    "519",  # Social and economic geography
    "520",  # Other social sciences
    "6",  # Humanities
    "611",  # Philosophy
    "6121",  # Languages
    "6122",  # Literature studies
    "6131",  # Theatre, dance, music, other performing arts
    "6132",  # Visual arts and design
    "614",  # Theology
    "615",  # History and archaeology
    "616",  # Other humanities
    "9",  # Other
    "999",  # Other
]


def format_subject_okm_field_of_science(subjects: list[Subject] | None) -> None:
    """
    Validate and format a list of subjects according to the OKM field of science classification.

    Raises a UserException if an invalid subject code is found.

    :param subjects: A list of Subjects to validate and format.
    :raises UserException: If a subject contains an invalid OKM subject code.
    """
    if subjects:
        for subject in subjects:
            subject_code = subject.subject.split(" - ")[0]
            if subject_code not in OKM_SUBJECT_CODE:
                raise UserException(f"Invalid OKM subject code: {subject_code}")
            subject.subjectScheme = "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus"
            subject.schemeUri = AnyUrl("http://www.yso.fi/onto/okm-tieteenala/conceptscheme")
            subject.valueUri = AnyUrl(f"http://www.yso.fi/onto/okm-tieteenala/ta{subject_code}")
            subject.classificationCode = subject_code
