"""Tests for external data feed parsers and resilience."""
import pytest
from app.ingestion.p2000 import P2000Ingestor
from app.ingestion.mobility import MobilityIngestor
from app.ingestion.environment import EnvironmentIngestor, wmo_weather_description
from app.ingestion.news import NewsIngestor, detect_rotterdam_neighborhood


def test_wmo_weather_description():
    assert wmo_weather_description(0) == "Helder"
    assert wmo_weather_description(61) == "Lichte regen"
    assert wmo_weather_description(95) == "Onweer"


def test_detect_rotterdam_neighborhood():
    lon, lat, district = detect_rotterdam_neighborhood("Ongeval op de Coolsingel in het centrum")
    assert district == "Rotterdam Centrum"

    lon, lat, district = detect_rotterdam_neighborhood("Feest in Delfshaven aan de haven")
    assert district == "Delfshaven"

    lon, lat, district = detect_rotterdam_neighborhood("Geen specifieke locatie gemeld")
    assert district == "Rotterdam"


@pytest.mark.asyncio
async def test_open_meteo_live_fetch():
    ingestor = EnvironmentIngestor()
    client = await ingestor.get_client()
    try:
        resp = await client.get(
            "https://api.open-meteo.com/v1/forecast?latitude=51.9244&longitude=4.4777&current=temperature_2m"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "temperature_2m" in data.get("current", {})
    finally:
        await ingestor.close()
