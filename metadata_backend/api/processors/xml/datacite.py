"""
Read DataCite XML.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from lxml.etree import _Element as Element  # noqa

from ...models.datacite import (
    Affiliation,
    AlternateIdentifier,
    Contributor,
    Creator,
    DataCiteMetadata,
    Date,
    Description,
    FundingReference,
    GeoLocation,
    GeoLocationBox,
    GeoLocationPoint,
    GeoLocationPolygonPoint,
    Identifier,
    NameIdentifier,
    Publisher,
    RelatedIdentifier,
    ResourceType,
    Rights,
    Subject,
    Title,
)
from .processors import XmlProcessor

DATACITE_XML_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "schemas" / "xml" / "datacite" / "4.5"

DATACITE_NAMESPACE = {"d": "http://datacite.org/schema/kernel-4"}

DATACITE_PATH = "/d:resource"


def _elem(node: Element | list[Element] | None) -> Element | None:
    """Return element  if the element exists.

    :param node: An XML element, a list of elements with one XML element, or None.
    :returns: The element if it exists, otherwise None.
    """
    if isinstance(node, list):
        if len(node) > 1:
            raise SystemError(f"At most one element expected: {[element.tag for element in node]}")
        return node[0] if node else None

    return node


def _elem_text(node: Element | list[Element] | None) -> str | None:
    """Return element text if the element or element value exists.

    :param node: An XML element, a list of elements with one XML element, or None.
    :returns: The element text if it exists, otherwise None.
    """
    elem = _elem(node)

    if elem is None or elem.text is None:
        return None

    return cast(str, elem.text.strip()) or None


def _attr_text(node: Element | list[Element] | None, attr: str) -> str | None:
    """Return attribute text if the attribute or attribute value exists.

    :param node: An XML element, a list of elements with one XML element, or None.
    :param attr: The attribute.
    :returns: the attribute text if it exists, otherwise None.
    """
    elem = _elem(node)

    if elem is None:
        return None

    val = elem.get(attr)
    return cast(str, val.strip()) if val else None


def read_datacite_xml(source: str | bytes) -> DataCiteMetadata:
    """Read DataCite XML and return datacite metadata.

    :param source: The DataCite XML.
    :returns: datacite metadata.
    """
    xml = XmlProcessor.parse_xml(source)

    XmlProcessor.validate_schema(xml, str(DATACITE_XML_SCHEMA_DIR), "metadata.xsd")

    def _xpath(el: Element, path: str) -> list[Element]:
        """
        Find elements using namespace-aware XPATH.
        """
        return cast(list[Element], el.xpath(path, namespaces=DATACITE_NAMESPACE))

    # identifiers
    identifiers = []
    for identifier_elem in _xpath(xml, f"{DATACITE_PATH}/d:identifier"):
        identifiers.append(
            Identifier(
                identifier=_elem_text(identifier_elem), identifierType=_attr_text(identifier_elem, "identifierType")
            )
        )

    # publicationYear
    publication_year = _elem_text(_xpath(xml, f"{DATACITE_PATH}/d:publicationYear"))

    # version
    version = _elem_text(_xpath(xml, f"{DATACITE_PATH}/d:version"))

    # rights
    rights_list = []
    for rights_elem in _xpath(xml, f"{DATACITE_PATH}/d:rightsList/d:rights"):
        rights_list.append(
            Rights(
                rights=_elem_text(rights_elem),
                rightsUri=_attr_text(rights_elem, "rightsURI"),
                rightsIdentifier=_attr_text(rights_elem, "rightsIdentifier"),
                rightsIdentifierScheme=_attr_text(rights_elem, "rightsIdentifierScheme"),
                schemeUri=_attr_text(rights_elem, "schemeURI"),
            )
        )

    # resourceType
    resource_type = None
    resource_type_elem = _elem(_xpath(xml, f"{DATACITE_PATH}/d:resourceType"))
    if resource_type_elem is not None:
        resource_type = ResourceType(
            resourceType=_elem_text(resource_type_elem),
            resourceTypeGeneral=_attr_text(resource_type_elem, "resourceTypeGeneral"),
        )

    # titles
    titles = []
    for title_elem in _xpath(xml, f"{DATACITE_PATH}/d:titles/d:title"):
        titles.append(Title(title=_elem_text(title_elem), titleType=_attr_text(title_elem, "titleType")))

    # creators
    creators = []
    for creator_elem in _xpath(xml, f"{DATACITE_PATH}/d:creators/d:creator"):
        name_identifiers = []
        for name_identifier_elem in _xpath(creator_elem, "d:nameIdentifier"):
            name_identifiers.append(
                NameIdentifier(
                    nameIdentifier=_elem_text(name_identifier_elem),
                    nameIdentifierScheme=_attr_text(name_identifier_elem, "nameIdentifierScheme"),
                    schemeUri=_attr_text(name_identifier_elem, "schemeURI"),
                )
            )

        affiliations = []
        for affiliation_element in _xpath(creator_elem, "d:affiliation"):
            affiliations.append(
                Affiliation(
                    name=_elem_text(affiliation_element),
                    affiliationIdentifier=_attr_text(affiliation_element, "affiliationIdentifier"),
                    affiliationIdentifierScheme=_attr_text(affiliation_element, "affiliationIdentifierScheme"),
                    schemeUri=_attr_text(affiliation_element, "schemeURI"),
                )
            )

        creator = Creator(
            name=_elem_text(_xpath(creator_elem, "d:creatorName")),
            givenName=_elem_text(_xpath(creator_elem, "d:givenName")),
            familyName=_elem_text(_xpath(creator_elem, "d:familyName")),
            nameIdentifiers=name_identifiers or None,
            affiliation=affiliations or None,
        )
        creators.append(creator)

    # publisher
    publisher_elem = _elem(_xpath(xml, f"{DATACITE_PATH}/d:publisher"))
    publisher = Publisher(
        name=_elem_text(publisher_elem),
        publisherIdentifier=_attr_text(publisher_elem, "publisherIdentifier"),
        publisherIdentifierScheme=_attr_text(publisher_elem, "publisherIdentifierScheme"),
        schemeUri=_attr_text(publisher_elem, "schemeURI"),
    )

    # contributors
    contributors = []
    for contributor_elem in _xpath(xml, f"{DATACITE_PATH}/d:contributors/d:contributor"):
        name_identifiers = []
        for name_identifier_elem in _xpath(contributor_elem, "d:nameIdentifier"):
            name_identifiers.append(
                NameIdentifier(
                    nameIdentifier=_elem_text(name_identifier_elem),
                    nameIdentifierScheme=_attr_text(name_identifier_elem, "nameIdentifierScheme"),
                    schemeUri=_attr_text(name_identifier_elem, "schemeURI"),
                )
            )

        affiliations = []
        for affiliation_element in _xpath(contributor_elem, "d:affiliation"):
            affiliations.append(
                Affiliation(
                    name=_elem_text(affiliation_element),
                    affiliationIdentifier=_attr_text(affiliation_element, "affiliationIdentifier"),
                    affiliationIdentifierScheme=_attr_text(affiliation_element, "affiliationIdentifierScheme"),
                    schemeUri=_attr_text(affiliation_element, "schemeURI"),
                )
            )

        contributors.append(
            Contributor(
                name=_elem_text(_xpath(contributor_elem, "d:contributorName")),
                contributorType=_attr_text(contributor_elem, "contributorType"),
                givenName=_elem_text(_xpath(contributor_elem, "d:givenName")),
                familyName=_elem_text(_xpath(contributor_elem, "d:familyName")),
                nameIdentifiers=name_identifiers or None,
                affiliation=affiliations or None,
            )
        )

    # subjects
    subjects = []
    for subject_element in _xpath(xml, f"{DATACITE_PATH}/d:subjects/d:subject"):
        subjects.append(
            Subject(
                subject=_elem_text(subject_element),
                subjectScheme=_attr_text(subject_element, "subjectScheme"),
                schemeUri=_attr_text(subject_element, "schemeURI"),
                valueUri=_attr_text(subject_element, "valueURI"),
                classificationCode=_attr_text(subject_element, "classificationCode"),
            )
        )

    # dates
    dates = []
    for date_elem in _xpath(xml, f"{DATACITE_PATH}/d:dates/d:date"):
        dates.append(
            Date(
                date=_elem_text(date_elem),
                dateType=_attr_text(date_elem, "dateType"),
                dateInformation=_attr_text(date_elem, "dateInformation"),
            )
        )

    # language
    language = _elem_text(_xpath(xml, f"{DATACITE_PATH}/d:language"))

    # related identifiers
    related_identifiers = []
    for related_identifier_elem in _xpath(xml, f"{DATACITE_PATH}/d:relatedIdentifiers/d:relatedIdentifier"):
        related_identifiers.append(
            RelatedIdentifier(
                relatedIdentifier=_elem_text(related_identifier_elem),
                relatedIdentifierType=_attr_text(related_identifier_elem, "relatedIdentifierType"),
                relationType=_attr_text(related_identifier_elem, "relationType"),
                relatedMetadataScheme=_attr_text(related_identifier_elem, "relatedMetadataScheme"),
                schemeUri=_attr_text(related_identifier_elem, "schemeURI"),
                schemeType=_attr_text(related_identifier_elem, "schemeType"),
                resourceTypeGeneral=_attr_text(related_identifier_elem, "resourceTypeGeneral"),
            )
        )

    # alternate identifiers
    alternate_identifiers = []
    for alternative_identifier_elem in _xpath(xml, f"{DATACITE_PATH}/d:alternateIdentifiers/d:alternateIdentifier"):
        alternate_identifiers.append(
            AlternateIdentifier(
                alternateIdentifier=_elem_text(alternative_identifier_elem),
                alternateIdentifierType=_attr_text(alternative_identifier_elem, "alternateIdentifierType"),
            )
        )

    # sizes
    sizes = [_elem_text(n) for n in _xpath(xml, f"{DATACITE_PATH}/d:sizes/d:size") if _elem_text(n)] or None

    # formats
    formats = [_elem_text(n) for n in _xpath(xml, f"{DATACITE_PATH}/d:formats/d:format") if _elem_text(n)] or None

    # descriptions
    descriptions = []
    for description_elem in _xpath(xml, f"{DATACITE_PATH}/d:descriptions/d:description"):
        descriptions.append(
            Description(
                description=_elem_text(description_elem),
                descriptionType=_attr_text(description_elem, "descriptionType"),
                lang=description_elem.get("{http://www.w3.org/XML/1998/namespace}lang"),
            )
        )

    # geoLocations
    geolocations = []
    for geo_location_elem in _xpath(xml, f"{DATACITE_PATH}/d:geoLocations/d:geoLocation"):
        point = None
        box = None
        polygon = None
        if _xpath(geo_location_elem, "d:geoLocationPoint"):
            e = _xpath(geo_location_elem, "d:geoLocationPoint")[0]
            point = GeoLocationPoint(
                pointLatitude=_elem_text(_xpath(e, "d:pointLatitude")),
                pointLongitude=_elem_text(_xpath(e, "d:pointLongitude")),
            )
        if _xpath(geo_location_elem, "d:geoLocationBox"):
            e = _xpath(geo_location_elem, "d:geoLocationBox")[0]
            box = GeoLocationBox(
                westBoundLongitude=_elem_text(_xpath(e, "d:westBoundLongitude")),
                eastBoundLongitude=_elem_text(_xpath(e, "d:eastBoundLongitude")),
                southBoundLatitude=_elem_text(_xpath(e, "d:southBoundLatitude")),
                northBoundLatitude=_elem_text(_xpath(e, "d:northBoundLatitude")),
            )
        if _xpath(geo_location_elem, "d:geoLocationPolygon/d:polygonPoint"):
            polygon = []
            for e in _xpath(geo_location_elem, "d:geoLocationPolygon/d:polygonPoint"):
                polygon.append(
                    GeoLocationPolygonPoint(
                        polygonPoint=GeoLocationPoint(
                            pointLatitude=_elem_text(_xpath(e, "d:pointLatitude")),
                            pointLongitude=_elem_text(_xpath(e, "d:pointLongitude")),
                        )
                    )
                )
            for e in _xpath(geo_location_elem, "d:geoLocationPolygon/d:inPolygonPoint"):
                polygon.append(
                    GeoLocationPolygonPoint(
                        inPolygonPoint=GeoLocationPoint(
                            pointLatitude=_elem_text(_xpath(e, "d:pointLatitude")),
                            pointLongitude=_elem_text(_xpath(e, "d:pointLongitude")),
                        )
                    )
                )
                break
        geolocations.append(
            GeoLocation(
                geoLocationPlace=_elem_text(_xpath(geo_location_elem, "d:geoLocationPlace")),
                geoLocationPoint=point,
                geoLocationBox=box,
                geoLocationPolygon=polygon,
            )
        )

    # fundingReferences
    funding_references = []

    for funding_reference_elem in _xpath(xml, f"{DATACITE_PATH}/d:fundingReferences/d:fundingReference"):
        funder_identifier = None
        funder_identifier_type = None
        scheme_uri = None
        if _xpath(funding_reference_elem, "d:funderIdentifier"):
            e = _xpath(funding_reference_elem, "d:funderIdentifier")[0]
            funder_identifier = _elem_text(e)
            funder_identifier_type = _attr_text(e, "funderIdentifierType")
            scheme_uri = _attr_text(e, "schemeURI")

        funding_references.append(
            FundingReference(
                funderName=_elem_text(_xpath(funding_reference_elem, "d:funderName")),
                funderIdentifier=funder_identifier,
                funderIdentifierType=funder_identifier_type,
                schemeUri=scheme_uri,
                awardNumber=_elem_text(_xpath(funding_reference_elem, "d:awardNumber")),
                awardUri=_attr_text(_xpath(funding_reference_elem, "d:awardNumber"), "awardURI"),
                awardTitle=_elem_text(_xpath(funding_reference_elem, "d:awardTitle")),
            )
        )

    # Build final model
    metadata = DataCiteMetadata(
        identifiers=identifiers or None,
        publicationYear=publication_year,
        version=version,
        rightsList=rights_list,
        types=resource_type,
        titles=titles or None,
        creators=creators,
        publisher=publisher,
        contributors=contributors or None,
        subjects=subjects or None,
        dates=dates or None,
        language=language,
        relatedIdentifiers=related_identifiers or None,
        alternateIdentifiers=alternate_identifiers or None,
        sizes=sizes,
        formats=formats,
        descriptions=descriptions or None,
        geoLocations=geolocations or None,
        fundingReferences=funding_references or None,
    )

    return metadata
