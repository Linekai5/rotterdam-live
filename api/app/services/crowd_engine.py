"""Production-Grade Crowdness Engine & Real-Time Forecaster (Platform v1.9.0).

Quantitative model implementation:
- Diurnal Baseline B_d(dow, hour) in [0, 75] with 3-week EMA and seeded priors
- Event Surge with Exact Gaussian Profiles in [0, 50]
- Weather Shift in [-15, +15]
- Live Observation C_live(d, t0) with parking occupancy or structural baseline
- Live Residual Delta_d(t0) = C_live(d, t0) - C_hat_d(t0)
- Autoregressive Horizon Projection C_d(t0 + h) = Clamp(C_hat_d(t0 + h) + Delta_d(t0) * exp(-0.5 * h), 0, 100)
- Zero in-request computation invariant: API reads pre-compiled JSON snapshots from Redis / PostgreSQL.
"""
import json
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import logger
from app.schemas.crowd import (
    CrowdMetricsDetails,
    CrowdForecastPoint,
    DistrictCrowdProperties,
    DistrictCrowdFeature,
    CrowdLiveFeatureCollection,
    DistrictCrowdDetailResponse,
    DistrictForecastMatrixItem,
    CrowdForecastMatrixResponse,
    CrowdOverviewStats,
)
from app.cache.redis_client import get_redis_client, set_cached_json, get_cached_json


# ==============================================================================
# 1. Mathematical Utility Functions & Classifications
# ==============================================================================

def clamp(val: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """Clamp a floating point value to [min_val, max_val]."""
    return max(min_val, min(max_val, val))


def get_crowd_status(index: float) -> Tuple[str, str]:
    """
    Map normalized crowdness index to (English, Dutch) status category:
    - 0 - 25: Quiet (Rustig)
    - 26 - 50: Moderate (Normaal)
    - 51 - 75: Busy (Druk)
    - 76 - 100: Saturated / Peak (Zeer druk / Piek)
    """
    if index <= 25.0:
        return "Quiet", "Rustig"
    elif index <= 50.0:
        return "Moderate", "Normaal"
    elif index <= 75.0:
        return "Busy", "Druk"
    else:
        return "Saturated", "Zeer druk"


# District Classifications for Rotterdam
INDOOR_SHOPPING_HUBS = {"Rotterdam Centrum", "Centrum", "Charlois"}
RECREATIONAL_TERRACE_HUBS = {"Rotterdam Centrum", "Centrum", "Kralingen-Crooswijk", "Kralingen"}
RETAIL_CENTRUM_DISTRICTS = {"Rotterdam Centrum", "Centrum", "Feijenoord"}
PORT_INDUSTRIAL_DISTRICTS = {
    "Botlek-Europoort-Maasvlakte",
    "Botlek",
    "Waalhaven-Eemhaven",
    "Waalhaven",
    "Vondelingenplaat",
    "Spaanse Polder",
    "Nieuw Mathenesse",
    "Rivium",
    "Rotterdam-Noord-West",
    "Rotterdam Haven",
}
RESIDENTIAL_DISTRICTS = {
    "Noord",
    "Kralingen-Crooswijk",
    "Kralingen",
    "Delfshaven",
    "Hillegersberg-Schiebroek",
    "Hoogvliet",
    "IJsselmonde",
    "Prins Alexander",
    "Overschie",
    "Pernis",
}


# ==============================================================================
# 2. Diurnal Baseline B_d(dow, hour) in [0, 75]
# ==============================================================================

def get_seeded_prior(district_name: str, dow: int, hour: int) -> float:
    """
    Calculate seeded diurnal prior baseline B_d_prior(dow, hour) in [0, 75].
    dow: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday.
    hour: 0..23

    Specification:
    - Centrum / Retail: Saturday peak 65 pts (13:00-17:00), Friday shopping evening 55 pts (18:00-21:00),
      weekday daytime 35-45 pts, night 10 pts.
    - Residential (Noord, Kralingen): Morning peak 40 pts (07:30-09:00), evening peak 45 pts (17:00-19:00), night 15 pts.
    - Port / Industrial (Waalhaven, Botlek): Weekday daytime 35 pts (07:00-16:00), night/weekends 5 pts.
    """
    # 1. Centrum / Retail
    if district_name in RETAIL_CENTRUM_DISTRICTS:
        if dow == 5:  # Saturday
            if 13 <= hour <= 17:
                score = 65.0  # Saturday peak 65 pts
            elif 10 <= hour < 13 or 18 <= hour <= 20:
                score = 52.0
            elif 23 <= hour or hour < 7:
                score = 10.0  # night 10 pts
            else:
                score = 35.0
        elif dow == 4:  # Friday
            if 18 <= hour <= 21:
                score = 55.0  # Friday shopping evening (koopavond)
            elif 9 <= hour < 18:
                score = 42.0  # weekday daytime 35-45 pts
            elif 23 <= hour or hour < 7:
                score = 10.0  # night 10 pts
            else:
                score = 30.0
        elif dow == 6:  # Sunday
            if 12 <= hour <= 18:
                score = 45.0  # Sunday shopping afternoon
            elif 23 <= hour or hour < 8:
                score = 10.0  # night 10 pts
            else:
                score = 25.0
        else:  # Monday - Thursday
            if 9 <= hour <= 18:
                score = 40.0  # weekday daytime 35-45 pts
            elif 23 <= hour or hour < 7:
                score = 10.0  # night 10 pts
            elif 7 <= hour < 9 or 19 <= hour < 23:
                score = 25.0
            else:
                score = 20.0

    # 2. Port / Industrial
    elif district_name in PORT_INDUSTRIAL_DISTRICTS:
        if dow < 5:  # Weekday
            if 7 <= hour <= 16:
                score = 35.0  # Weekday daytime 35 pts (07:00-16:00)
            elif 20 <= hour or hour < 5:
                score = 5.0   # night 5 pts
            else:
                score = 15.0
        else:  # Weekends
            score = 5.0       # weekends 5 pts

    # 3. Residential (Default)
    else:
        if dow < 5:  # Weekdays
            if 7 <= hour <= 8:
                score = 40.0  # Morning peak 40 pts (07:30-09:00)
            elif 17 <= hour <= 19:
                score = 45.0  # Evening peak 45 pts (17:00-19:00)
            elif 22 <= hour or hour < 6:
                score = 15.0  # night 15 pts
            elif 9 <= hour < 17:
                score = 25.0  # daytime off-peak
            else:
                score = 30.0
        else:  # Weekends
            if 22 <= hour or hour < 7:
                score = 15.0  # night 15 pts
            elif 10 <= hour <= 18:
                score = 32.0  # weekend daytime
            else:
                score = 22.0

    return clamp(score, 0.0, 75.0)


async def calculate_diurnal_baseline(
    session: AsyncSession,
    district_name: str,
    target_time: datetime,
) -> float:
    """
    Calculate B_d(dow, hour) in [0, 75].
    Uses 3-week Exponential Moving Average (EMA) from crowd_telemetry_history if >= 14 days of history.
    Otherwise falls back to seeded priors.
    """
    dow = target_time.weekday()  # 0=Monday..6=Sunday
    hour = target_time.hour

    try:
        query = text(
            """
            SELECT crowd_index, timestamp
            FROM crowd_telemetry_history
            WHERE district = :district
              AND EXTRACT(DOW FROM timestamp) = :pg_dow
              AND EXTRACT(HOUR FROM timestamp) = :hour
              AND timestamp >= :cutoff
            ORDER BY timestamp ASC;
            """
        )
        pg_dow = (dow + 1) % 7  # PostgreSQL DOW: 0=Sunday, 1=Monday
        cutoff = target_time - timedelta(days=21)

        result = await session.execute(
            query,
            {
                "district": district_name,
                "pg_dow": pg_dow,
                "hour": hour,
                "cutoff": cutoff,
            },
        )
        rows = result.fetchall()

        # Check if historical records span >= 14 distinct days
        if rows:
            unique_days = len({r[1].date() for r in rows})
            if unique_days >= 14:
                # 3-week Exponential Moving Average (EMA)
                alpha = 2.0 / (len(rows) + 1.0)
                ema = rows[0][0]
                for val, _ in rows[1:]:
                    ema = alpha * val + (1.0 - alpha) * ema
                return clamp(round(float(ema), 2), 0.0, 75.0)
    except Exception as e:
        logger.debug("Failed querying EMA history for {}: {}", district_name, e)

    # Use seeded prior
    prior = get_seeded_prior(district_name, dow, hour)
    return clamp(round(prior, 2), 0.0, 75.0)


# ==============================================================================
# 3. Event Surge with Exact Gaussian Profiles in [0, 50]
# ==============================================================================

def calculate_single_event_surge(
    event: Dict[str, Any],
    target_time: datetime,
) -> float:
    """
    Calculate single event surge contribution using Gaussian temporal profile:
    TierPoints(e) * exp( - (t - t_peak,e)^2 / (2 * sigma_e^2) )
    """
    title = (event.get("title") or "").lower()
    venue = (event.get("venue_name") or "").lower()
    subcat = (event.get("subcategory") or "").lower()
    start_time: datetime = event.get("start_time")
    if not start_time:
        return 0.0

    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=timezone.utc)

    # 1. Tier Points: HIGH=40, MEDIUM=20, LOW=8
    high_match = any(k in venue or k in title for k in ["ahoy", "kuip", "feijenoord", "marathon", "north sea jazz"])
    med_match = any(k in venue or k in title for k in ["luxor", "doelen", "kasteel", "woudestein", "maassilo", "sparta", "excelsior", "roel langerakpark"])

    if high_match:
        tier_points = 40.0
    elif med_match:
        tier_points = 20.0
    else:
        tier_points = 8.0

    # 2. Gaussian Temporal Parameters
    is_stadium = subcat == "stadium_fixture" or any(k in venue or k in title for k in ["kuip", "kasteel", "woudestein", "feyenoord", "sparta", "excelsior"])
    is_concert_theatre = subcat in ("concert", "theatre", "comedy") or any(k in venue for k in ["ahoy", "luxor", "doelen", "theater"])
    is_festival = subcat == "festival" or "festival" in title or "carnaval" in title or "marathon" in title

    if is_stadium:
        # Football matches: t_peak = t_start + 45 min, sigma = 50 min
        t_peak = start_time + timedelta(minutes=45)
        sigma = 50.0
    elif is_concert_theatre:
        # Concerts & Theatres: t_peak = t_start, sigma = 75 min
        t_peak = start_time
        sigma = 75.0
    elif is_festival:
        # Festivals & Outdoor Events: t_peak = t_start + (duration / 2), sigma = 180 min
        end_time = event.get("end_time")
        if end_time:
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            duration_minutes = max(60.0, (end_time - start_time).total_seconds() / 60.0)
        else:
            duration_minutes = 360.0  # default 6 hours
        t_peak = start_time + timedelta(minutes=duration_minutes / 2.0)
        sigma = 180.0
    else:
        # Default / Other: t_peak = t_start, sigma = 60 min
        t_peak = start_time
        sigma = 60.0

    delta_minutes = (target_time - t_peak).total_seconds() / 60.0
    # Optimization: if |delta| > 4 * sigma, contribution is negligible (< 0.0003)
    if abs(delta_minutes) > 4.0 * sigma:
        return 0.0

    exponent = - (delta_minutes ** 2) / (2.0 * (sigma ** 2))
    surge = tier_points * math.exp(exponent)
    return surge


def calculate_event_surge(
    events: List[Dict[str, Any]],
    target_time: datetime,
) -> float:
    """
    EventSurge_d(t) = min(50, sum_{e in E_d} TierPoints(e) * exp(- (t - t_peak)^2 / (2 * sigma^2)))
    """
    total_surge = 0.0
    for e in events:
        total_surge += calculate_single_event_surge(e, target_time)

    return clamp(round(total_surge, 2), 0.0, 50.0)


# ==============================================================================
# 4. Weather Shift in [-15, +15] hard points
# ==============================================================================

def calculate_weather_shift(
    precipitation_mm_h: float,
    temperature_c: Optional[float],
    wind_bft: Optional[int],
    district_name: str,
) -> float:
    """
    WeatherShift_d(t) in [-15, +15] hard points:
    - Rain > 2.5 mm/h: -10 pts for outdoor districts; +10 pts for indoor shopping hubs (Centrum, Zuidplein / Charlois)
    - Moderate rain (0.5 - 2.5 mm/h): -5 pts outdoor, +5 pts indoor hubs
    - Pleasant (18 - 25 °C, dry, wind < 4 Bft): +10 pts for recreational/terrace hubs (Centrum, Kralingen)
    """
    is_indoor_hub = district_name in INDOOR_SHOPPING_HUBS
    is_terrace_hub = district_name in RECREATIONAL_TERRACE_HUBS

    # Heavy rain > 2.5 mm/h
    if precipitation_mm_h > 2.5:
        shift = 10.0 if is_indoor_hub else -10.0
    # Moderate rain (0.5 - 2.5 mm/h)
    elif precipitation_mm_h >= 0.5:
        shift = 5.0 if is_indoor_hub else -5.0
    # Pleasant (18 - 25 °C, dry, wind < 4 Bft)
    elif (
        temperature_c is not None
        and 18.0 <= temperature_c <= 25.0
        and precipitation_mm_h < 0.5
        and (wind_bft is None or wind_bft < 4)
    ):
        shift = 10.0 if is_terrace_hub else 0.0
    else:
        shift = 0.0

    return clamp(round(shift, 2), -15.0, 15.0)


# ==============================================================================
# 5. Structural Baseline & Live Observation
# ==============================================================================

def calculate_structural_baseline(
    diurnal_baseline: float,
    event_surge: float,
    weather_shift: float,
) -> float:
    """
    C_base_hat_d(t) = B_d(dow, hour) + EventSurge_d(t) + WeatherShift_d(t)
    """
    return round(diurnal_baseline + event_surge + weather_shift, 2)


def calculate_live_observation(
    has_garages: bool,
    parking_occupancy_pct: Optional[float],
    n_p2000: int,
    n_roads: int,
    weather_shift: float,
    structural_baseline: float,
) -> float:
    """
    Live Observation C_live(d, t0):
    1. For districts with monitored parking garages (N_garages > 0):
       C_live = Clamp(0.75 * Occ(d) + 0.15 * min(N_p2000 * 5, 20) + 0.10 * min(N_roads * 5, 10) + WeatherShift_d(t0), 0, 100)
    2. For districts without monitored garages (N_garages == 0):
       C_live = Clamp(C_base_hat_d(t0) + min(N_p2000 * 5, 20) + min(N_roads * 5, 10), 0, 100)
    """
    p2000_comp = min(n_p2000 * 5.0, 20.0)
    roads_comp = min(n_roads * 5.0, 10.0)

    if has_garages and parking_occupancy_pct is not None:
        c_live = 0.75 * parking_occupancy_pct + 0.15 * p2000_comp + 0.10 * roads_comp + weather_shift
    else:
        c_live = structural_baseline + p2000_comp + roads_comp

    return clamp(round(c_live, 2), 0.0, 100.0)


# ==============================================================================
# 6. Autoregressive Horizon Projection C_d(t0 + h)
# ==============================================================================

def calculate_horizon_projection(
    horizon_hours: float,
    structural_baseline_h: float,
    live_residual: float,
) -> float:
    """
    Autoregressive Horizon Projection at horizon h hours (t = t0 + h):
    C_d(t0 + h) = Clamp(C_base_hat_d(t0 + h) + Delta_d(t0) * exp(-0.5 * h), 0, 100)
    Guarantees that at h=0, C_d(t0) == C_live(d, t0).
    """
    residual_term = live_residual * math.exp(-0.5 * horizon_hours)
    projected = structural_baseline_h + residual_term
    return clamp(round(projected, 2), 0.0, 100.0)


# ==============================================================================
# 7. Complete Background Ingestion Cycle (Worker Execution Engine)
# ==============================================================================

async def fetch_current_weather(session: AsyncSession) -> Dict[str, Any]:
    """Fetch latest weather metrics from Redis or database."""
    weather = {
        "temperature_c": 19.5,
        "precipitation_mm_h": 0.0,
        "wind_bft": 4,
        "condition": "Zwaar bewolkt",
    }

    # Try Redis cached live weather first
    try:
        cached_live = await get_cached_json("weather:live:rotterdam")
        if cached_live:
            if "temperature" in cached_live and cached_live["temperature"] is not None:
                weather["temperature_c"] = float(cached_live["temperature"])
            if cached_live.get("precipitation", {}).get("current_mm_h") is not None:
                weather["precipitation_mm_h"] = float(cached_live["precipitation"]["current_mm_h"])
            if cached_live.get("wind", {}).get("bft") is not None:
                weather["wind_bft"] = int(cached_live["wind"]["bft"])
            if "summary" in cached_live:
                weather["condition"] = cached_live["summary"]
            return weather
    except Exception as e:
        logger.debug("Could not read weather from Redis: {}", e)

    # Fallback to database live_events weather
    try:
        stmt = text(
            """
            SELECT details FROM live_events
            WHERE subcategory = 'weather' AND (details->>'temperature') IS NOT NULL
            ORDER BY timestamp DESC LIMIT 1;
            """
        )
        res = await session.execute(stmt)
        row = res.fetchone()
        if row and row[0]:
            dtl = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            if "temperature" in dtl and dtl["temperature"] is not None:
                weather["temperature_c"] = float(dtl["temperature"])
            if "precipitation_mm_h" in dtl and dtl["precipitation_mm_h"] is not None:
                weather["precipitation_mm_h"] = float(dtl["precipitation_mm_h"])
            if "windspeed_bft" in dtl and dtl["windspeed_bft"] is not None:
                weather["wind_bft"] = int(dtl["windspeed_bft"])
            if "weather_description" in dtl:
                weather["condition"] = dtl["weather_description"]
    except Exception as e:
        logger.debug("Could not read weather from live_events: {}", e)

    return weather


async def execute_crowdness_cycle(session: AsyncSession) -> Dict[str, Any]:
    """
    Executes the 100% background mathematical derivations for all 19 districts:
    1. Loads canonical district polygons from rotterdam_districts.
    2. Spatially associates live parking garages, emergencies, and roadworks.
    3. Loads active & upcoming events with Gaussian temporal profiles within 1.5km buffer.
    4. Calculates C_live, C_base_hat, Live Residual Delta_d(t0).
    5. Calculates 24-hour autoregressive forecast projection series.
    6. Persists snapshots to crowd_telemetry_history (truncated to 15-minute slot).
    7. Compiles pre-rendered JSON snapshots into Redis for sub-5ms client queries.
    """
    now = datetime.now(timezone.utc)
    # Truncate timestamp to 15-minute slot
    slot_minute = (now.minute // 15) * 15
    slot_time = now.replace(minute=slot_minute, second=0, microsecond=0)

    # 1. Fetch official districts with boundaries
    dist_stmt = text(
        """
        SELECT id, code, name, district_type, properties, ST_AsGeoJSON(geom) as geom_json
        FROM rotterdam_districts
        ORDER BY name ASC;
        """
    )
    dist_rows = (await session.execute(dist_stmt)).fetchall()
    if not dist_rows:
        logger.warning("No districts found in rotterdam_districts for crowd cycle.")
        return {"status": "no_districts", "count": 0}

    # 2. Fetch current weather
    weather = await fetch_current_weather(session)
    precip = weather["precipitation_mm_h"]
    temp = weather["temperature_c"]
    wind = weather["wind_bft"]
    weather_cond = weather["condition"]

    # 3. Spatially query parking garages
    parking_stmt = text(
        """
        SELECT 
            d.name as district_name,
            count(p.id) as garage_count,
            sum((p.details->>'occupied_spaces')::numeric) as total_occ,
            sum((p.details->>'total_capacity')::numeric) as total_cap
        FROM rotterdam_districts d
        JOIN live_events p ON ST_Within(p.geom, d.geom) AND p.subcategory = 'parking'
        GROUP BY d.name;
        """
    )
    parking_res = (await session.execute(parking_stmt)).fetchall()
    parking_map: Dict[str, Dict[str, Any]] = {}
    for r in parking_res:
        d_name, g_count, occ, cap = r[0], int(r[1]), float(r[2] or 0), float(r[3] or 1)
        occ_pct = round((occ / cap) * 100.0, 1) if cap > 0 else 0.0
        parking_map[d_name] = {
            "garage_count": g_count,
            "total_occupied": occ,
            "total_capacity": cap,
            "occupancy_pct": occ_pct,
        }

    # 4. Spatially query active emergencies (P2000)
    emerg_stmt = text(
        """
        SELECT d.name, count(e.id) as emerg_count
        FROM rotterdam_districts d
        LEFT JOIN live_events e ON ST_Within(e.geom, d.geom)
            AND e.category = 'emergency'
            AND (e.expires_at IS NULL OR e.expires_at > NOW())
        GROUP BY d.name;
        """
    )
    emerg_map = {r[0]: int(r[1]) for r in (await session.execute(emerg_stmt)).fetchall()}

    # 5. Spatially query active roadworks
    roads_stmt = text(
        """
        SELECT d.name, count(r.id) as roads_count
        FROM rotterdam_districts d
        LEFT JOIN live_events r ON ST_Within(r.geom, d.geom)
            AND r.subcategory = 'roadworks'
            AND (r.expires_at IS NULL OR r.expires_at > NOW())
        GROUP BY d.name;
        """
    )
    roads_map = {r[0]: int(r[1]) for r in (await session.execute(roads_stmt)).fetchall()}

    # 6. Fetch events in or within 1.5km buffer (~0.018 degrees) of districts
    # Query events active around now (-12h to +36h)
    events_stmt = text(
        """
        SELECT 
            d.name as district_name,
            e.id, e.title, e.subcategory, e.venue_name, e.start_time, e.end_time
        FROM rotterdam_districts d
        JOIN rotterdam_events e 
          ON (e.district = d.name OR ST_DWithin(e.geom, d.geom, 0.018))
         AND e.is_active = true
         AND e.start_time >= :time_start
         AND e.start_time <= :time_end
        ORDER BY e.start_time ASC;
        """
    )
    time_start = now - timedelta(hours=12)
    time_end = now + timedelta(hours=36)
    events_res = (
        await session.execute(
            events_stmt,
            {"time_start": time_start, "time_end": time_end},
        )
    ).fetchall()

    district_events: Dict[str, List[Dict[str, Any]]] = {r[2]: [] for r in dist_rows}
    for r in events_res:
        d_name = r[0]
        if d_name in district_events:
            district_events[d_name].append(
                {
                    "id": r[1],
                    "title": r[2],
                    "subcategory": r[3],
                    "venue_name": r[4],
                    "start_time": r[5],
                    "end_time": r[6],
                }
            )

    # 7. Evaluate each district
    evaluated_features: List[Dict[str, Any]] = []
    district_details_dict: Dict[str, Dict[str, Any]] = {}
    matrix_items: List[Dict[str, Any]] = []

    total_crowd_index = 0.0
    highest_index = -1.0
    busiest_d = None
    lowest_index = 101.0
    quietest_d = None

    hist_records = []

    horizons_hours = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 24.0]

    for d_row in dist_rows:
        d_id, d_code, d_name, d_type, d_props, geom_str = d_row
        geom = json.loads(geom_str) if geom_str else None

        # Components at t0
        p_info = parking_map.get(d_name)
        has_garages = p_info is not None and p_info["garage_count"] > 0
        occ_pct = p_info["occupancy_pct"] if has_garages else None

        n_p2000 = emerg_map.get(d_name, 0)
        n_roads = roads_map.get(d_name, 0)
        events_list = district_events.get(d_name, [])

        # Structural Baseline at t0
        diurnal_t0 = await calculate_diurnal_baseline(session, d_name, now)
        surge_t0 = calculate_event_surge(events_list, now)
        shift_t0 = calculate_weather_shift(precip, temp, wind, d_name)
        c_base_hat_t0 = calculate_structural_baseline(diurnal_t0, surge_t0, shift_t0)

        # Live Observation C_live(d, t0)
        c_live_t0 = calculate_live_observation(
            has_garages=has_garages,
            parking_occupancy_pct=occ_pct,
            n_p2000=n_p2000,
            n_roads=n_roads,
            weather_shift=shift_t0,
            structural_baseline=c_base_hat_t0,
        )

        # Live Residual Delta_d(t0)
        delta_t0 = round(c_live_t0 - c_base_hat_t0, 2)

        c_status_en, c_status_nl = get_crowd_status(c_live_t0)

        # Track stats
        total_crowd_index += c_live_t0
        if c_live_t0 > highest_index:
            highest_index = c_live_t0
            busiest_d = d_name
        if c_live_t0 < lowest_index:
            lowest_index = c_live_t0
            quietest_d = d_name

        # Compute Forecast Timeline (horizons_hours)
        forecast_points: List[Dict[str, Any]] = []
        for h in horizons_hours:
            target_t = now + timedelta(hours=h)
            diurnal_h = get_seeded_prior(d_name, target_t.weekday(), target_t.hour)
            surge_h = calculate_event_surge(events_list, target_t)
            # Weather shift for forecast uses current weather persistence
            shift_h = calculate_weather_shift(precip, temp, wind, d_name)
            c_base_hat_h = calculate_structural_baseline(diurnal_h, surge_h, shift_h)
            c_projected_h = calculate_horizon_projection(h, c_base_hat_h, delta_t0)
            status_en_h, status_nl_h = get_crowd_status(c_projected_h)
            residual_term_h = round(delta_t0 * math.exp(-0.5 * h), 2)

            forecast_points.append(
                {
                    "horizon_hours": h,
                    "target_time": target_t.isoformat(),
                    "crowd_index": c_projected_h,
                    "crowd_status": status_en_h,
                    "crowd_status_nl": status_nl_h,
                    "base_score": diurnal_h,
                    "event_surge": surge_h,
                    "weather_shift": shift_h,
                    "residual_contribution": residual_term_h,
                }
            )

        details_dict = {
            "base_score": diurnal_t0,
            "event_surge": surge_t0,
            "weather_shift": shift_t0,
            "live_residual": delta_t0,
            "structural_baseline": c_base_hat_t0,
            "parking_occupancy_avg_pct": occ_pct,
            "monitored_garages_count": p_info["garage_count"] if p_info else 0,
            "active_events_count": len(events_list),
            "emergency_count": n_p2000,
            "roadworks_count": n_roads,
            "precipitation_mm_h": precip,
            "temperature_c": temp,
            "wind_bft": wind,
            "weather_condition": weather_cond,
        }

        # Format GeoJSON Feature
        feature = {
            "type": "Feature",
            "id": d_code,
            "geometry": geom,
            "properties": {
                "district_code": d_code,
                "district_name": d_name,
                "crowd_index": c_live_t0,
                "crowd_status": c_status_en,
                "crowd_status_nl": c_status_nl,
                "has_monitored_garages": has_garages,
                "parking_occupancy_avg_pct": occ_pct,
                "active_events_count": len(events_list),
                "precipitation_mm_h": precip,
                "temperature_c": temp,
                "details": details_dict,
                "timestamp": slot_time.isoformat(),
                "updated_at": now.isoformat(),
            },
        }
        evaluated_features.append(feature)

        # Single District Detail Snapshot
        district_details_dict[d_name] = {
            "district_code": d_code,
            "district_name": d_name,
            "crowd_index": c_live_t0,
            "crowd_status": c_status_en,
            "crowd_status_nl": c_status_nl,
            "has_monitored_garages": has_garages,
            "parking_occupancy_avg_pct": occ_pct,
            "active_events_count": len(events_list),
            "precipitation_mm_h": precip,
            "temperature_c": temp,
            "details": details_dict,
            "timestamp": slot_time.isoformat(),
            "forecast": forecast_points,
        }

        matrix_items.append(
            {
                "district_code": d_code,
                "district_name": d_name,
                "current_index": c_live_t0,
                "current_status": c_status_en,
                "current_status_nl": c_status_nl,
                "horizons": forecast_points,
            }
        )

        hist_records.append(
            {
                "district": d_name,
                "timestamp": slot_time,
                "crowd_index": c_live_t0,
                "crowd_status": c_status_en,
                "parking_occupancy_avg_pct": occ_pct,
                "active_events_count": len(events_list),
                "precipitation_mm_h": precip,
                "temperature_c": temp,
                "details": json.dumps(details_dict),
            }
        )

    # 8. Upsert crowd_telemetry_history in PostgreSQL
    upsert_stmt = text(
        """
        INSERT INTO crowd_telemetry_history (
            district, timestamp, crowd_index, crowd_status,
            parking_occupancy_avg_pct, active_events_count,
            precipitation_mm_h, temperature_c, details, created_at
        )
        VALUES (
            :district, :timestamp, :crowd_index, :crowd_status,
            :parking_occupancy_avg_pct, :active_events_count,
            :precipitation_mm_h, :temperature_c, CAST(:details AS jsonb), NOW()
        )
        ON CONFLICT (district, timestamp) DO UPDATE SET
            crowd_index = EXCLUDED.crowd_index,
            crowd_status = EXCLUDED.crowd_status,
            parking_occupancy_avg_pct = EXCLUDED.parking_occupancy_avg_pct,
            active_events_count = EXCLUDED.active_events_count,
            precipitation_mm_h = EXCLUDED.precipitation_mm_h,
            temperature_c = EXCLUDED.temperature_c,
            details = EXCLUDED.details;
        """
    )
    for rec in hist_records:
        await session.execute(upsert_stmt, rec)
    await session.commit()
    logger.info("Persisted {} crowd telemetry history records to PostgreSQL", len(hist_records))

    # 9. Compile pre-rendered JSON snapshots for Redis (< 5ms response time)
    n_districts = len(dist_rows)
    avg_index = round(total_crowd_index / n_districts, 1) if n_districts > 0 else 0.0

    # Master GeoJSON FeatureCollection
    master_feature_collection = {
        "type": "FeatureCollection",
        "features": evaluated_features,
        "total_districts": n_districts,
        "timestamp": slot_time.isoformat(),
        "city_average_crowd_index": avg_index,
        "busiest_district": busiest_d,
        "quietest_district": quietest_d,
    }
    await set_cached_json("crowd:live:rotterdam", master_feature_collection, ttl_seconds=180)

    # Individual district snapshots
    for d_name, d_data in district_details_dict.items():
        cache_key = f"crowd:district:{d_name.lower()}"
        await set_cached_json(cache_key, d_data, ttl_seconds=180)
        # Also cache under alias without 'rotterdam '
        if d_name.lower().startswith("rotterdam "):
            alias = d_name.lower().replace("rotterdam ", "")
            await set_cached_json(f"crowd:district:{alias}", d_data, ttl_seconds=180)

    # Forecast Matrix
    forecast_matrix = {
        "timestamp": slot_time.isoformat(),
        "horizons_evaluated_hours": horizons_hours,
        "districts": matrix_items,
    }
    await set_cached_json("crowd:forecast:all", forecast_matrix, ttl_seconds=180)

    # Overview Stats
    quiet_cnt = sum(1 for f in evaluated_features if f["properties"]["crowd_index"] <= 25.0)
    mod_cnt = sum(1 for f in evaluated_features if 25.0 < f["properties"]["crowd_index"] <= 50.0)
    busy_cnt = sum(1 for f in evaluated_features if 50.0 < f["properties"]["crowd_index"] <= 75.0)
    peak_cnt = sum(1 for f in evaluated_features if f["properties"]["crowd_index"] > 75.0)

    total_garages = sum(p["garage_count"] for p in parking_map.values())
    tot_occ = sum(p["total_occupied"] for p in parking_map.values())
    tot_cap = sum(p["total_capacity"] for p in parking_map.values())
    citywide_parking_occ = round((tot_occ / tot_cap) * 100.0, 1) if tot_cap > 0 else None

    overview_stats = {
        "timestamp": slot_time.isoformat(),
        "city_average_crowd_index": avg_index,
        "quiet_districts_count": quiet_cnt,
        "moderate_districts_count": mod_cnt,
        "busy_districts_count": busy_cnt,
        "peak_districts_count": peak_cnt,
        "busiest_district": busiest_d,
        "busiest_district_index": highest_index,
        "quietest_district": quietest_d,
        "quietest_district_index": lowest_index,
        "monitored_garages_total": total_garages,
        "citywide_parking_occupancy_pct": citywide_parking_occ,
        "active_events_total": len(events_res),
    }
    await set_cached_json("crowd:overview", overview_stats, ttl_seconds=180)

    logger.info(
        "Crowdness engine cycle finished: city avg index={}, busiest='{}' ({}), quietest='{}' ({})",
        avg_index,
        busiest_d,
        highest_index,
        quietest_d,
        lowest_index,
    )
    return {
        "status": "success",
        "districts_evaluated": n_districts,
        "city_average_crowd_index": avg_index,
        "busiest_district": busiest_d,
        "quietest_district": quietest_d,
        "timestamp": slot_time.isoformat(),
    }
