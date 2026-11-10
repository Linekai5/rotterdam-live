"""Comprehensive Unit and Integration Tests for /api/v1/living Domain."""
import json
from unittest.mock import AsyncMock

import pytest
import httpx
from sqlalchemy import text

from app.main import app
from app.api.v1 import living as living_api
from app.db.session import AsyncSessionLocal
from app.ingestion.living_harvester import RotterdamLivingHarvester


@pytest.mark.asyncio
async def test_demographics_list():
    """Verify GET /api/v1/living/demographics returns all 19 districts with valid CBS demographics."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/living/demographics")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_districts" in data
        assert data["total_districts"] == 19
        assert "districts" in data
        assert len(data["districts"]) == 19

        first = data["districts"][0]
        assert "district_code" in first
        assert "district_name" in first
        assert "total_population" in first
        assert first["total_population"] > 0
        assert "age_brackets" in first
        assert "0-14" in first["age_brackets"]
        assert "15-24" in first["age_brackets"]
        assert "25-44" in first["age_brackets"]
        assert "45-64" in first["age_brackets"]
        assert "65+" in first["age_brackets"]
        assert "total_households" in first
        assert "average_household_size" in first


@pytest.mark.asyncio
async def test_demographics_filter_by_district():
    """Verify filtering demographics by district name or code."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Filter by common alias 'Centrum'
        resp = await client.get("/api/v1/living/demographics?district=Centrum")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_districts"] == 1
        d = data["districts"][0]
        assert d["district_code"] == "WK059901"
        assert d["district_name"] == "Rotterdam Centrum"
        assert d["total_population"] == 42925
        assert d["age_brackets"]["0-14"] == 3120

        # Filter by code
        resp_code = await client.get("/api/v1/living/demographics?district=WK059903")
        assert resp_code.status_code == 200
        d_code = resp_code.json()["districts"][0]
        assert d_code["district_name"] == "Delfshaven"


@pytest.mark.asyncio
async def test_demographics_overview():
    """Verify municipal-level high-level demographic and housing totals."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/living/demographics/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_city_population" in data
        assert data["total_city_population"] >= 600000
        assert "total_residential_units" in data
        assert data["total_residential_units"] >= 300000
        assert data["overall_density_km2"] == 3058
        assert "city_wide_age_breakdown" in data
        assert data["city_wide_age_breakdown"]["0-14"] > 0
        assert data["city_wide_households"] > 0
        assert data["average_household_size"] > 1.0
        assert data["single_person_pct"] > 0


@pytest.mark.asyncio
async def test_housing_list():
    """Verify GET /api/v1/living/housing returns residential stocks and era breakdowns."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/living/housing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_districts"] == 19
        assert data["total_residential_stock"] >= 340000
        assert len(data["districts"]) == 19

        item = data["districts"][0]
        assert "surface_area" in item
        assert "average_m2" in item["surface_area"]
        assert "median_m2" in item["surface_area"]
        assert "construction_eras" in item
        eras = item["construction_eras"]
        assert "pre_war" in eras
        assert "post_war_reconstruction" in eras
        assert "late_20th_century" in eras
        assert "modern" in eras
        assert "average_woz_value" in item
        assert "tenure_breakdown" in item
        assert "livability" in item
        assert "amenity_counts" in item


@pytest.mark.asyncio
async def test_housing_filter_by_district():
    """Verify filtering housing metrics by district."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/living/housing?district=Feijenoord")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_districts"] == 1
        d = data["districts"][0]
        assert d["district_code"] == "WK059910"
        assert d["district_name"] == "Feijenoord"
        assert d["total_residential_units"] > 40000
        assert d["average_woz_value"] == 311000
        assert d["amenity_counts"]["supermarkets"] == 24


@pytest.mark.asyncio
async def test_district_passport_success(monkeypatch):
    """Verify GET /api/v1/living/districts/{name}/passport returns RFC 7946 GeoJSON Feature."""
    # Exercise the current database join, independently of a previously cached
    # annual profile. Source statistics may change when ingestion runs.
    monkeypatch.setattr(living_api, "get_cached_json", AsyncMock(return_value=None))
    monkeypatch.setattr(living_api, "set_cached_json", AsyncMock())
    async with AsyncSessionLocal() as session:
        housing = (await session.execute(text("""
            SELECT total_residential_units, avg_surface_area_m2, amenity_counts, livability_index
            FROM district_housing_metrics WHERE district_code = 'WK059901'
        """))).mappings().one()
        demographics = (await session.execute(text("""
            SELECT total_population, age_0_14
            FROM district_demographics WHERE district_code = 'WK059901'
        """))).mappings().one()
        geometry = json.loads(await session.scalar(text("""
            SELECT ST_AsGeoJSON(geom) FROM rotterdam_districts WHERE code = 'WK059901'
        """)))
    amenity_counts = housing["amenity_counts"]
    if isinstance(amenity_counts, str):
        amenity_counts = json.loads(amenity_counts)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Test 1: Centrum
        resp = await client.get("/api/v1/living/districts/Centrum/passport")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "Feature"
        assert data["id"] == "WK059901"
        assert data["geometry"]["type"] == "MultiPolygon"
        assert len(data["geometry"]["coordinates"]) > 0
        assert data["geometry"] == geometry

        props = data["properties"]
        assert props["district_code"] == "WK059901"
        assert props["district_name"] == "Rotterdam Centrum"
        assert props["demographics"]["total_population"] == demographics["total_population"]
        assert props["demographics"]["age_brackets"]["0-14"] == demographics["age_0_14"]
        assert props["housing"]["total_residential_units"] == housing["total_residential_units"]
        assert props["housing"]["surface_area"]["average_m2"] == float(housing["avg_surface_area_m2"])
        assert props["amenities"]["supermarkets"] == amenity_counts["supermarkets"]
        assert props["amenities"]["cameras"] == amenity_counts["cameras"]
        assert props["housing"]["amenity_counts"] == props["amenities"]
        assert props["livability"]["overall_index"] == float(housing["livability_index"])

        # Test 2: Hyphenated name 'Kralingen-Crooswijk'
        resp_kc = await client.get("/api/v1/living/districts/kralingen-crooswijk/passport")
        assert resp_kc.status_code == 200
        assert resp_kc.json()["properties"]["district_code"] == "WK059908"

        # Test 3: District code direct lookup
        resp_code = await client.get("/api/v1/living/districts/WK059903/passport")
        assert resp_code.status_code == 200
        assert resp_code.json()["properties"]["district_name"] == "Delfshaven"


@pytest.mark.asyncio
async def test_district_passport_not_found():
    """Verify 404 error when querying an unknown district name."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/living/districts/utrecht_neude/passport")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_living_harvester_cycle():
    """Verify RotterdamLivingHarvester executes end-to-end without unhandled exceptions."""
    harvester = RotterdamLivingHarvester()
    try:
        res = await harvester.ingest()
        assert res["districts_processed"] == 19
        assert res["demographics_saved"] == 19
        assert res["housing_saved"] == 19
    finally:
        await harvester.close()
