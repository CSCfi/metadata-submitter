async def test_ror_service(monkeypatch):
    """Test ROR using production service."""

    monkeypatch.setenv("ROR_URL", "https://api.ror.org/v2/")

    from metadata_backend.services.ror_service import RorServiceHandler

    service = RorServiceHandler()

    # Match.
    org = "Helsinki University Hospital"
    result = await service.is_ror_organisation(org)
    assert result == "Helsinki University Hospital"
    result = await service.is_ror_organisation(org.lower())
    assert result == "Helsinki University Hospital"
    result = await service.is_ror_organisation(org.upper())
    assert result == "Helsinki University Hospital"
    # Returns multiple matches that contain "Academy of Medicine".
    result = await service.is_ror_organisation("Academy of Medicine")
    assert result == "Academy of Medicine"

    # Too many matches.
    org = "HUS"
    result = await service.is_ror_organisation(org)
    assert result is None  # Too many matches.

    # No Match.
    result = await service.is_ror_organisation("UnknownOrganisation")
    assert result is None
