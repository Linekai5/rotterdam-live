"""Unit tests for Geocoding and Address parsing."""
import pytest
from app.services.geocoder import geocoder
from app.ingestion.p2000 import extract_address_query, parse_p2000_service, parse_p2000_severity


def test_p2000_address_extraction_postcode():
    raw_title = "a1 ambu 17109 spangesekade 3027gj rotterdam rottdm bon 158515"
    raw_desc = "Ambulance met spoed naar Spangesekade in Rotterdam"
    query = extract_address_query(raw_title, raw_desc)
    assert "3027gj" in query.lower() or "spangesekade" in query.lower()


def test_p2000_service_classification():
    assert parse_p2000_service("a1 ambu 17109 spangesekade") == "ambulance"
    assert parse_p2000_service("prio 1 brandweer keilestraat") == "brandweer"
    assert parse_p2000_service("politie naar brielselaan") == "politie"
    assert parse_p2000_service("lifeliner 2 opgeroepen") == "traumahelikopter"


def test_p2000_severity_classification():
    sev, prio = parse_p2000_severity("a1 ambu met spoed")
    assert sev == 5
    assert prio == 1

    sev, prio = parse_p2000_severity("a2 ambu met gepaste spoed")
    assert sev == 4
    assert prio == 2

    sev, prio = parse_p2000_severity("b1 ambu rustig")
    assert sev == 3


@pytest.mark.asyncio
async def test_geocoder_fallback():
    lon, lat = await geocoder.geocode("")
    assert 4.0 <= lon <= 5.0
    assert 51.5 <= lat <= 52.5
