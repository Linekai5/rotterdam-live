"""Live smoke tests for all external open data feeds."""
import pytest
from app.ingestion.p2000 import P2000Ingestor
from app.ingestion.mobility import MobilityIngestor
from app.ingestion.news import NewsIngestor
from app.ingestion.environment import EnvironmentIngestor
from app.services.geocoder import geocoder


@pytest.mark.asyncio
async def test_p2000_rss_fetch():
    ingestor = P2000Ingestor()
    client = await ingestor.get_client()
    try:
        resp = await client.get(
            "https://alarmeringen.nl/feeds/region/rotterdam-rijnmond.rss",
            headers={"User-Agent": "curl/8.5.0", "Accept": "*/*"}
        )
        if resp.status_code == 403:
            pytest.skip("Alarmeringen.nl Akamai WAF blocked datacenter IP (403 Forbidden)")
        assert resp.status_code == 200
        assert "<rss" in resp.text
        assert "rotterdam" in resp.text.lower()
    finally:
        await ingestor.close()


@pytest.mark.asyncio
async def test_pdok_locatieserver_geocoding():
    lon, lat = await geocoder.geocode("Coolsingel 40 Rotterdam")
    assert 4.40 <= lon <= 4.55
    assert 51.85 <= lat <= 51.98


@pytest.mark.asyncio
async def test_rijnmond_rss_live():
    ingestor = NewsIngestor()
    client = await ingestor.get_client()
    try:
        resp = await client.get("https://www.rijnmond.nl/rss/nieuws")
        assert resp.status_code == 200
        assert "<rss" in resp.text
    finally:
        await ingestor.close()


@pytest.mark.asyncio
async def test_donkey_republic_gbfs_live():
    ingestor = MobilityIngestor()
    client = await ingestor.get_client()
    try:
        resp = await client.get(
            "https://stables.donkey.bike/api/public/gbfs/2/donkey_rotterdam_den_haag/nl/station_information.json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "stations" in data.get("data", {})
    finally:
        await ingestor.close()


@pytest.mark.asyncio
async def test_openov_gtfs_rt_live():
    ingestor = MobilityIngestor()
    client = await ingestor.get_client()
    try:
        resp = await client.get("https://gtfs.openov.nl/gtfs-rt/alerts.pb")
        assert resp.status_code == 200
        assert len(resp.content) > 10000
    finally:
        await ingestor.close()
