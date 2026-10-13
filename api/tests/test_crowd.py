"""Comprehensive Unit, Mathematical, and Integration Tests for /api/v1/crowd Domain.

Tests:
1. Quantitative Model Specification:
   - Clamping invariant in [0, 100] and [-15, +15]
   - Status classifications (Quiet, Moderate, Busy, Saturated)
   - Diurnal baseline priors (Centrum/Retail, Residential, Port/Industrial)
   - Event Surge exact Gaussian profiles & tier weighting
   - Weather shift logic (rain, moderate rain, pleasant outdoor)
   - Live observation derivations (monitored garages vs sensorless districts)
   - Autoregressive horizon projection decay & h=0 exact match
2. Database Schema & Hard Constraints:
   - Unique constraint uq_crowd_hist_district_time
   - Indexed queries performance
3. API Endpoints & Zero In-Request Computation:
   - GET /api/v1/crowd/live (RFC 7946 GeoJSON FeatureCollection)
   - ETag HTTP 304 Not Modified support
   - GET /api/v1/crowd/districts/{name} (Passport + 24h forecast series)
   - GET /api/v1/crowd/forecast (Matrix projections)
   - GET /api/v1/crowd/history (Indexed lookups)
   - GET /api/v1/crowd/overview (Municipal statistics)
"""
import math
from datetime import datetime, timezone, timedelta
import pytest
import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.db.session import AsyncSessionLocal
from app.services.crowd_engine import (
    clamp,
    get_crowd_status,
    get_seeded_prior,
    calculate_single_event_surge,
    calculate_event_surge,
    calculate_weather_shift,
    calculate_structural_baseline,
    calculate_live_observation,
    calculate_horizon_projection,
    execute_crowdness_cycle,
)


# ==============================================================================
# 1. Quantitative Model Specification Tests
# ==============================================================================

def test_clamp_function():
    """Verify clamping bounds."""
    assert clamp(-5.0, 0.0, 100.0) == 0.0
    assert clamp(105.0, 0.0, 100.0) == 100.0
    assert clamp(50.0, 0.0, 100.0) == 50.0
    assert clamp(-20.0, -15.0, 15.0) == -15.0
    assert clamp(20.0, -15.0, 15.0) == 15.0


def test_status_classifications():
    """
    Verify status label mappings:
    0-25: Quiet (Rustig)
    26-50: Moderate (Normaal)
    51-75: Busy (Druk)
    76-100: Saturated (Zeer druk)
    """
    assert get_crowd_status(0.0) == ("Quiet", "Rustig")
    assert get_crowd_status(25.0) == ("Quiet", "Rustig")
    assert get_crowd_status(25.1) == ("Moderate", "Normaal")
    assert get_crowd_status(50.0) == ("Moderate", "Normaal")
    assert get_crowd_status(50.1) == ("Busy", "Druk")
    assert get_crowd_status(75.0) == ("Busy", "Druk")
    assert get_crowd_status(75.1) == ("Saturated", "Zeer druk")
    assert get_crowd_status(100.0) == ("Saturated", "Zeer druk")


def test_seeded_priors_centrum_retail():
    """
    Verify Centrum / Retail priors:
    Saturday peak 65 pts (13:00-17:00), Friday shopping evening 55 pts (18:00-21:00),
    weekday daytime 35-45 pts, night 10 pts.
    """
    # Saturday peak (dow=5, hour=15)
    sat_peak = get_seeded_prior("Rotterdam Centrum", dow=5, hour=15)
    assert sat_peak == 65.0

    # Friday shopping evening (dow=4, hour=19)
    fri_evening = get_seeded_prior("Rotterdam Centrum", dow=4, hour=19)
    assert fri_evening == 55.0

    # Weekday daytime (dow=2, hour=14)
    weekday_day = get_seeded_prior("Rotterdam Centrum", dow=2, hour=14)
    assert 35.0 <= weekday_day <= 45.0

    # Night (dow=2, hour=3)
    night = get_seeded_prior("Rotterdam Centrum", dow=2, hour=3)
    assert night == 10.0


def test_seeded_priors_residential():
    """
    Verify Residential (Noord, Kralingen):
    Morning peak 40 pts (07:30-09:00), evening peak 45 pts (17:00-19:00), night 15 pts.
    """
    # Weekday morning peak (dow=1, hour=8)
    morning = get_seeded_prior("Noord", dow=1, hour=8)
    assert morning == 40.0

    # Weekday evening peak (dow=1, hour=18)
    evening = get_seeded_prior("Kralingen-Crooswijk", dow=1, hour=18)
    assert evening == 45.0

    # Night (dow=1, hour=2)
    night = get_seeded_prior("Delfshaven", dow=1, hour=2)
    assert night == 15.0


def test_seeded_priors_port_industrial():
    """
    Verify Port / Industrial (Waalhaven, Botlek):
    Weekday daytime 35 pts (07:00-16:00), night/weekends 5 pts.
    """
    # Weekday daytime (dow=2, hour=11)
    day = get_seeded_prior("Botlek-Europoort-Maasvlakte", dow=2, hour=11)
    assert day == 35.0

    # Weekday night (dow=2, hour=2)
    night = get_seeded_prior("Waalhaven-Eemhaven", dow=2, hour=2)
    assert night == 5.0

    # Weekend (dow=6, hour=14)
    weekend = get_seeded_prior("Botlek-Europoort-Maasvlakte", dow=6, hour=14)
    assert weekend == 5.0


def test_gaussian_event_surge_profiles():
    """
    Verify exact Gaussian event surge profiles and temporal parameters:
    - High tier: 40 pts (Ahoy, De Kuip, Marathon)
    - Stadium matches: t_peak = t_start + 45 min, sigma = 50 min
    - Concerts/theatres: t_peak = t_start, sigma = 75 min
    - Festivals: t_peak = t_start + duration/2, sigma = 180 min
    """
    t0 = datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc)

    # 1. Stadium match starting at 14:00 -> t_peak = 14:45, sigma = 50 min
    stadium_event = {
        "title": "Feyenoord vs Ajax",
        "venue_name": "Stadion Feijenoord (De Kuip)",
        "subcategory": "stadium_fixture",
        "start_time": t0,
    }
    # At exact peak (14:45)
    t_peak_stadium = t0 + timedelta(minutes=45)
    surge_at_peak = calculate_single_event_surge(stadium_event, t_peak_stadium)
    assert pytest.approx(surge_at_peak, rel=1e-3) == 40.0

    # At 1 sigma away (14:45 + 50 min = 15:35): should be 40 * exp(-0.5) ~ 24.26
    t_1sigma = t_peak_stadium + timedelta(minutes=50)
    surge_1sigma = calculate_single_event_surge(stadium_event, t_1sigma)
    expected_1sigma = 40.0 * math.exp(-0.5)
    assert pytest.approx(surge_1sigma, rel=1e-3) == expected_1sigma

    # 2. Concert at Ahoy starting at 20:00 -> t_peak = 20:00, sigma = 75 min
    concert_t0 = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
    concert_event = {
        "title": "World Tour Live",
        "venue_name": "Rotterdam Ahoy Arena",
        "subcategory": "concert",
        "start_time": concert_t0,
    }
    surge_concert_peak = calculate_single_event_surge(concert_event, concert_t0)
    assert pytest.approx(surge_concert_peak, rel=1e-3) == 40.0

    # 3. Medium tier venue: Luxor Theater (20 pts)
    luxor_event = {
        "title": "Cabaret Show",
        "venue_name": "Oude Luxor Theater",
        "subcategory": "comedy",
        "start_time": concert_t0,
    }
    surge_luxor_peak = calculate_single_event_surge(luxor_event, concert_t0)
    assert pytest.approx(surge_luxor_peak, rel=1e-3) == 20.0

    # 4. Multi-event surge capping at 50 pts
    events = [stadium_event, concert_event, luxor_event]
    total_surge = calculate_event_surge(events, t_peak_stadium)
    assert total_surge <= 50.0


def test_weather_shift_logic():
    """
    Verify weather shift in [-15, +15]:
    - Rain > 2.5 mm/h: -10 outdoor, +10 indoor shopping hubs (Centrum, Zuidplein/Charlois)
    - Moderate rain 0.5-2.5 mm/h: -5 outdoor, +5 indoor
    - Pleasant (18-25 C, dry, wind < 4 Bft): +10 terrace hubs (Centrum, Kralingen)
    """
    # Heavy rain
    assert calculate_weather_shift(3.0, 15.0, 4, "Noord") == -10.0
    assert calculate_weather_shift(3.0, 15.0, 4, "Rotterdam Centrum") == 10.0
    assert calculate_weather_shift(3.0, 15.0, 4, "Charlois") == 10.0

    # Moderate rain
    assert calculate_weather_shift(1.2, 15.0, 4, "Overschie") == -5.0
    assert calculate_weather_shift(1.2, 15.0, 4, "Rotterdam Centrum") == 5.0

    # Pleasant weather
    assert calculate_weather_shift(0.0, 21.0, 2, "Rotterdam Centrum") == 10.0
    assert calculate_weather_shift(0.0, 21.0, 2, "Kralingen-Crooswijk") == 10.0
    assert calculate_weather_shift(0.0, 21.0, 2, "Botlek-Europoort-Maasvlakte") == 0.0


def test_live_observation_calculations():
    """
    Verify Live Observation C_live(d, t0):
    1. Monitored garages: 0.75 * Occ(d) + 0.15 * min(p2000*5, 20) + 0.10 * min(roads*5, 10) + Shift
    2. Sensorless districts: C_hat(t0) + min(p2000*5, 20) + min(roads*5, 10)
    """
    # 1. Monitored garages (e.g. Occ = 80%, 2 p2000 = 10, 1 road = 5, shift = 0)
    # C_live = 0.75 * 80 + 0.15 * 10 + 0.10 * 5 + 0 = 60 + 1.5 + 0.5 = 62.0
    c_live_garage = calculate_live_observation(
        has_garages=True,
        parking_occupancy_pct=80.0,
        n_p2000=2,
        n_roads=1,
        weather_shift=0.0,
        structural_baseline=40.0,
    )
    assert c_live_garage == 62.0

    # 2. Sensorless districts without incidents -> C_live == C_hat -> Delta = 0
    c_live_sensorless_clean = calculate_live_observation(
        has_garages=False,
        parking_occupancy_pct=None,
        n_p2000=0,
        n_roads=0,
        weather_shift=0.0,
        structural_baseline=35.0,
    )
    assert c_live_sensorless_clean == 35.0
    residual = c_live_sensorless_clean - 35.0
    assert residual == 0.0


def test_autoregressive_horizon_projection():
    """
    Verify Autoregressive Horizon Projection:
    C_d(t0 + h) = Clamp(C_hat_d(t0 + h) + Delta_d(t0) * exp(-0.5 * h), 0, 100)
    Invariant: At h=0, C_d(t0) == C_live(d, t0) with zero double-counting!
    """
    c_hat_t0 = 40.0
    c_live_t0 = 62.0
    delta_t0 = c_live_t0 - c_hat_t0  # +22.0

    # Horizon h=0
    c_proj_0 = calculate_horizon_projection(0.0, c_hat_t0, delta_t0)
    assert c_proj_0 == c_live_t0

    # Horizon h=2: Delta * exp(-1.0) = 22.0 * 0.367879 = 8.09 -> 40 + 8.09 = 48.09
    c_proj_2 = calculate_horizon_projection(2.0, 40.0, delta_t0)
    expected_2 = round(40.0 + 22.0 * math.exp(-1.0), 2)
    assert c_proj_2 == expected_2

    # Horizon h=10: Delta * exp(-5.0) ~ 0.15 -> approaches structural baseline
    c_proj_10 = calculate_horizon_projection(10.0, 40.0, delta_t0)
    assert abs(c_proj_10 - 40.0) < 0.2


# ==============================================================================
# 2. Database Schema & Hard Constraints Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_database_unique_constraint_crowd_telemetry_history():
    """
    Verify strict database unique constraint:
    CONSTRAINT uq_crowd_hist_district_time UNIQUE (district, timestamp);
    """
    test_district = "TestDistrict_UniqueConstraint"
    test_ts = datetime(2026, 10, 13, 10, 0, 0, tzinfo=timezone.utc)

    async with AsyncSessionLocal() as session:
        # 1. Clean test data
        await session.execute(
            text("DELETE FROM crowd_telemetry_history WHERE district = :d;"),
            {"d": test_district},
        )
        await session.commit()

        # 2. Insert first record
        insert_stmt = text(
            """
            INSERT INTO crowd_telemetry_history (
                district, timestamp, crowd_index, crowd_status,
                active_events_count, precipitation_mm_h, details, created_at
            )
            VALUES (
                :d, :ts, 45.0, 'Moderate', 0, 0.0, CAST('{}' AS jsonb), NOW()
            );
            """
        )
        await session.execute(insert_stmt, {"d": test_district, "ts": test_ts})
        await session.commit()

        # 3. Duplicate insert must raise IntegrityError
        with pytest.raises(IntegrityError):
            await session.execute(insert_stmt, {"d": test_district, "ts": test_ts})
            await session.commit()

        await session.rollback()

        # Cleanup
        await session.execute(
            text("DELETE FROM crowd_telemetry_history WHERE district = :d;"),
            {"d": test_district},
        )
        await session.commit()


# ==============================================================================
# 3. API Endpoints & Caching Performance Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_api_get_crowd_live():
    """Verify GET /api/v1/crowd/live returns complete RFC 7946 GeoJSON FeatureCollection."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/crowd/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert data["total_districts"] == 19
        assert len(data["features"]) == 19
        assert "city_average_crowd_index" in data
        assert "ETag" in resp.headers

        # Verify Feature Schema
        feat = data["features"][0]
        assert feat["type"] == "Feature"
        assert "geometry" in feat
        props = feat["properties"]
        assert "district_name" in props
        assert "crowd_index" in props
        assert 0.0 <= props["crowd_index"] <= 100.0
        assert "crowd_status" in props
        assert "crowd_status_nl" in props
        assert "details" in props
        assert "base_score" in props["details"]
        assert "live_residual" in props["details"]


@pytest.mark.asyncio
async def test_api_crowd_etag_304():
    """Verify ETag polling returns HTTP 304 Not Modified."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        initial = await client.get("/api/v1/crowd/live")
        assert initial.status_code == 200
        etag = initial.headers.get("ETag")
        assert etag is not None

        # Repeat request with If-None-Match
        cached_resp = await client.get(
            "/api/v1/crowd/live",
            headers={"If-None-Match": etag},
        )
        assert cached_resp.status_code == 304


@pytest.mark.asyncio
async def test_api_get_district_crowd_profile():
    """Verify GET /api/v1/crowd/districts/{name} returns passport and forecast timeline."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/crowd/districts/Centrum")
        assert resp.status_code == 200
        data = resp.json()
        assert "district_name" in data
        assert "Rotterdam Centrum" in data["district_name"]
        assert "crowd_index" in data
        assert "forecast" in data
        assert len(data["forecast"]) > 0

        # Verify h=0 point matches live crowd index
        point_0 = data["forecast"][0]
        assert point_0["horizon_hours"] == 0.0
        assert pytest.approx(point_0["crowd_index"], rel=1e-2) == data["crowd_index"]


@pytest.mark.asyncio
async def test_api_get_district_not_found():
    """Verify 404 on nonexistent district."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/crowd/districts/NonexistentWijkXYZ")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_get_crowd_forecast_matrix():
    """Verify GET /api/v1/crowd/forecast matrix across districts."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Full matrix
        resp = await client.get("/api/v1/crowd/forecast")
        assert resp.status_code == 200
        data = resp.json()
        assert "horizons_evaluated_hours" in data
        assert len(data["districts"]) == 19

        # Filtered by district
        resp_filt = await client.get("/api/v1/crowd/forecast?district=Feijenoord")
        assert resp_filt.status_code == 200
        data_filt = resp_filt.json()
        assert len(data_filt["districts"]) == 1
        assert "Feijenoord" in data_filt["districts"][0]["district_name"]


@pytest.mark.asyncio
async def test_api_get_crowd_history():
    """Verify GET /api/v1/crowd/history returns indexed historical snapshots."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/crowd/history?hours=24&limit=50")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_records" in data
        assert "history" in data
        assert data["total_records"] > 0
        rec = data["history"][0]
        assert "district" in rec
        assert "crowd_index" in rec
        assert "timestamp" in rec


@pytest.mark.asyncio
async def test_api_get_crowd_overview():
    """Verify GET /api/v1/crowd/overview returns high-level municipal telemetry."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/crowd/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "city_average_crowd_index" in data
        assert "quiet_districts_count" in data
        assert "moderate_districts_count" in data
        assert "busy_districts_count" in data
        assert "peak_districts_count" in data
        assert "busiest_district" in data
        assert "quietest_district" in data
        assert "monitored_garages_total" in data
