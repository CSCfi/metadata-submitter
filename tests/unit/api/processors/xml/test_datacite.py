from __future__ import annotations

from pathlib import Path

from pydantic_string_url import AnyUrl

from metadata_backend.api.models.datacite import DataCiteMetadata, Publisher
from metadata_backend.api.processors.xml.datacite import read_datacite_xml

TEST_FILE = Path(__file__).parent.parent.parent.parent.parent / "test_files" / "xml" / "datacite" / "datacite.xml"


def test_read_datacite_xml():
    xml = TEST_FILE.read_bytes()
    datacite = read_datacite_xml(xml)
    assert_datacite(datacite, saved=False)


def assert_datacite(datacite: DataCiteMetadata, saved: bool) -> None:
    # identifiers
    if not saved:
        assert datacite.identifiers is not None
        assert len(datacite.identifiers) == 1
        assert datacite.identifiers[0].identifier == "10.1234/example.doi"
        assert datacite.identifiers[0].identifierType == "DOI"

    # titles
    assert datacite.titles is not None
    assert datacite.titles[0].title == "Sample Dataset"

    # publication year
    assert datacite.publicationYear == 2022

    # version
    assert datacite.version == "1.0"

    # rights
    rights = datacite.rightsList[0]
    assert rights.rights == "Creative Commons Attribution 4.0 International"
    assert rights.rightsUri == "https://creativecommons.org/licenses/by/4.0/legalcode"
    assert rights.rightsIdentifier == "cc-by-4.0"
    assert rights.rightsIdentifierScheme == "SPDX"
    assert rights.schemeUri == "https://spdx.org/licenses/"

    # creators
    assert len(datacite.creators) == 1
    c = datacite.creators[0]
    assert c.givenName == "John"
    assert c.familyName == "Smith"
    # model validator should set name and nameType
    assert c.name == "Smith, John"
    assert c.nameType == "Personal"
    assert c.nameIdentifiers is not None
    assert c.nameIdentifiers[0].nameIdentifier == "https://orcid.org/0000-0002-1825-0097"
    assert c.nameIdentifiers[0].nameIdentifierScheme == "ORCID"
    assert str(c.nameIdentifiers[0].schemeUri) == "https://orcid.org"
    assert c.affiliation is not None
    assert c.affiliation[0].name == "Academy of Medicine"
    assert c.affiliation[0].affiliationIdentifier == "https://ror.org/00fnk0q46"
    assert c.affiliation[0].affiliationIdentifierScheme == "ROR"
    assert str(c.affiliation[0].schemeUri) == "https://www.ror.org/"

    # publisher
    assert datacite.publisher == Publisher(
        name="Attogen Biomedical Research",
        publisherIdentifier=AnyUrl("https://ror.org/01pbevv17"),
        publisherIdentifierScheme="ROR",
        schemeUri=AnyUrl("https://ror.org/"),
    )

    # contributors
    assert datacite.contributors is not None
    contrib = datacite.contributors[0]
    assert contrib.contributorType == "DataManager"
    assert contrib.givenName == "Jane"
    assert contrib.familyName == "Doe"

    # subjects
    assert datacite.subjects is not None
    s = datacite.subjects[0]
    assert s.subject.strip() == "Literature studies"
    assert s.subjectScheme == "OKM Ontology"
    assert str(s.schemeUri) == "http://www.yso.fi/onto/okm-tieteenala/conceptscheme"
    assert str(s.valueUri) == "http://www.yso.fi/onto/okm-tieteenala/ta6122"
    assert s.classificationCode == "6122"

    # dates
    assert datacite.dates is not None
    assert any(d.dateType == "Created" and d.date == "2020-01-01" for d in datacite.dates)
    assert any(
        d.dateType == "Updated" and d.date == "2022-01-01" and d.dateInformation == "Metadata updated"
        for d in datacite.dates
    )

    # language
    assert datacite.language == "en"

    # relatedIdentifiers
    assert datacite.relatedIdentifiers is not None
    ri = datacite.relatedIdentifiers[0]
    assert ri.relatedIdentifier == "10.2345/other.doi"
    assert ri.relatedIdentifierType == "DOI"
    assert ri.relationType == "IsCitedBy"
    assert ri.relatedMetadataScheme == "datacite"
    assert str(ri.schemeUri) == "http://example.org/scheme"
    assert ri.schemeType == "someType"
    assert ri.resourceTypeGeneral == "Dataset"

    # alternateIdentifiers
    assert datacite.alternateIdentifiers is not None
    assert datacite.alternateIdentifiers[0].alternateIdentifier == "abc-123"
    assert datacite.alternateIdentifiers[0].alternateIdentifierType == "LocalID"

    # sizes/formats
    assert datacite.sizes == ["1GB"]
    assert datacite.formats == ["text/csv"]

    # descriptions
    assert datacite.descriptions is not None
    desc = datacite.descriptions[0]
    assert "sample abstract description" in desc.description.lower()
    assert desc.descriptionType == "Abstract"
    assert desc.lang == "en"

    # geoLocations
    assert datacite.geoLocations is not None
    gl = datacite.geoLocations[0]
    assert gl.geoLocationPlace == "Helsinki"
    assert gl.geoLocationPoint is not None
    assert gl.geoLocationPoint.pointLatitude == 60.1699
    assert gl.geoLocationPoint.pointLongitude == 24.9384
    assert gl.geoLocationBox is not None
    assert gl.geoLocationBox.westBoundLongitude == 24.0
    assert gl.geoLocationBox.eastBoundLongitude == 25.0
    assert gl.geoLocationBox.southBoundLatitude == 60.0
    assert gl.geoLocationBox.northBoundLatitude == 61.0
    assert gl.geoLocationPolygon is not None
    assert len(gl.geoLocationPolygon) == 6
    expected_points = [
        (41.991, -71.032),
        (42.893, -69.622),
        (41.991, -68.211),
        (41.090, -69.622),
        (41.991, -71.032),
    ]
    for idx, (lat, lon) in enumerate(expected_points):
        assert gl.geoLocationPolygon[idx].polygonPoint.pointLatitude == lat
        assert gl.geoLocationPolygon[idx].polygonPoint.pointLongitude == lon
    assert gl.geoLocationPolygon[5].inPolygonPoint.pointLatitude == 41.500
    assert gl.geoLocationPolygon[5].inPolygonPoint.pointLongitude == -69.800

    # fundingReferences
    assert datacite.fundingReferences is not None
    fr = datacite.fundingReferences[0]
    assert fr.funderName == "Commission on Higher Education"
    assert fr.funderIdentifier == "https://ror.org/04s346m05"
    assert fr.funderIdentifierType == "ROR"
    assert fr.schemeUri == "http://example.org/schema/SA12345"
    assert fr.awardNumber == "GA12345"
    assert str(fr.awardUri) == "http://example.org/grant/GA12345"
    assert fr.awardTitle == "Climate Research Grant"
