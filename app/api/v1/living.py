"""Rotterdam Living Domain API Endpoints (/api/v1/living).

Exposes official demographics, housing analytics, construction era distributions,
civic amenity densities, livability indices, and consolidated District Passports.
"""
import json
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.schemas.living import (
    AgeBrackets,
    DemographicsItem,
    DemographicsListResponse,
    DemographicsOverview,
    DistrictAmenityCounts,
    DistrictPassportFeature,
    DistrictPassportProperties,
    EraBreakdownItem,
    ConstructionEras,
    HousingListResponse,
    HousingMetricsItem,
    HousingTenure,
    LivabilityScores,
    SurfaceAreaMetrics,
)
from app.cache.redis_client import get_cached_json, set_cached_json
from app.logging import logger

router = APIRouter(prefix="/living", tags=["Living Domain (Demographics & Housing)"])

# Canonical Rotterdam districts catalog for fast matching and suggestions
CANONICAL_DISTRICTS: List[Tuple[str, str]] = [
    ("WK059901", "Rotterdam Centrum"),
    ("WK059903", "Delfshaven"),
    ("WK059904", "Overschie"),
    ("WK059905", "Noord"),
    ("WK059906", "Hillegersberg-Schiebroek"),
    ("WK059908", "Kralingen-Crooswijk"),
    ("WK059910", "Feijenoord"),
    ("WK059912", "IJsselmonde"),
    ("WK059913", "Pernis"),
    ("WK059914", "Prins Alexander"),
    ("WK059915", "Charlois"),
    ("WK059916", "Hoogvliet"),
    ("WK059918", "Spaanse Polder"),
    ("WK059919", "Nieuw Mathenesse"),
    ("WK059921", "Waalhaven-Eemhaven"),
    ("WK059922", "Vondelingenplaat"),
    ("WK059923", "Botlek-Europoort-Maasvlakte"),
    ("WK059924", "Rotterdam-Noord-West"),
    ("WK059925", "Rivium"),
]


def normalize_query_str(s: str) -> str:
    """Normalize district query string for flexible matching."""
    return s.lower().replace("-", " ").replace("_", " ").strip()


def resolve_district(raw_input: str) -> Optional[Tuple[str, str]]:
    """
    Resolve user district parameter (code or partial/full name) to canonical (code, name).
    Examples: 'Centrum', 'rotterdam centrum', 'WK059901', 'kralingen-crooswijk', 'botlek'.
    """
    if not raw_input:
        return None

    clean = raw_input.strip()
    norm = normalize_query_str(clean)

    # 1. Exact code match
    for code, name in CANONICAL_DISTRICTS:
        if code.lower() == clean.lower():
            return code, name

    # 2. Exact normalized name or with/without 'Rotterdam ' prefix
    for code, name in CANONICAL_DISTRICTS:
        norm_name = normalize_query_str(name)
        if norm_name == norm or norm_name == f"rotterdam {norm}" or f"rotterdam {norm_name}" == norm:
            return code, name

    # 3. Substring match
    for code, name in CANONICAL_DISTRICTS:
        norm_name = normalize_query_str(name)
        if norm in norm_name or norm_name in norm:
            return code, name

    return None


@router.get("/demographics", response_model=DemographicsListResponse)
async def get_district_demographics(
    district: Optional[str] = Query(None, description="Optional filter by district name or code (e.g. 'Centrum', 'WK059901')")
):
    """
    Retrieve official CBS demographic profiles across all 19 Rotterdam districts.
    Includes population counts, density, age cohorts (0–14, 15–24, 25–44, 45–64, 65+),
    household structures, and average income indicators.
    """
    cache_key = f"living:demographics:{district or 'all'}"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    conditions = ["1=1"]
    params: Dict[str, Any] = {}

    if district:
        resolved = resolve_district(district)
        if resolved:
            conditions.append("district_code = :resolved_code")
            params["resolved_code"] = resolved[0]
        else:
            conditions.append("(district_code ILIKE :q OR district_name ILIKE :q_pattern)")
            params["q"] = district.strip()
            params["q_pattern"] = f"%{district.strip()}%"

    where_clause = " AND ".join(conditions)

    sql = text(f"""
        SELECT 
            district_code,
            district_name,
            total_population,
            population_density_km2,
            men,
            women,
            age_0_14,
            age_15_24,
            age_25_44,
            age_45_64,
            age_65_plus,
            total_households,
            single_person_households,
            single_person_pct,
            average_household_size,
            average_income_per_inhabitant,
            source,
            data_year,
            to_char(updated_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at_str
        FROM district_demographics
        WHERE {where_clause}
        ORDER BY total_population DESC NULLS LAST, district_name ASC;
    """)

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(sql, params)).fetchall()

    districts_list = []
    for r in rows:
        districts_list.append(
            DemographicsItem(
                district_code=r.district_code,
                district_name=r.district_name,
                total_population=r.total_population,
                population_density_km2=r.population_density_km2,
                men=r.men,
                women=r.women,
                age_brackets=AgeBrackets(
                    age_0_14=r.age_0_14,
                    age_15_24=r.age_15_24,
                    age_25_44=r.age_25_44,
                    age_45_64=r.age_45_64,
                    age_65_plus=r.age_65_plus,
                ),
                total_households=r.total_households,
                single_person_households=r.single_person_households,
                single_person_pct=float(r.single_person_pct) if r.single_person_pct is not None else None,
                average_household_size=float(r.average_household_size) if r.average_household_size is not None else None,
                average_income_per_inhabitant=r.average_income_per_inhabitant,
                source=r.source or "CBS Kerncijfers Wijken en Buurten",
                data_year=r.data_year or 2026,
                updated_at=r.updated_at_str,
            )
        )

    response_data = DemographicsListResponse(
        total_districts=len(districts_list),
        data_year=2026,
        source="CBS Kerncijfers Wijken en Buurten & Gemeente Rotterdam",
        districts=districts_list,
    ).model_dump(mode="json", by_alias=True)

    await set_cached_json(cache_key, response_data, ttl_seconds=3600)
    return response_data


@router.get("/demographics/overview", response_model=DemographicsOverview)
async def get_demographics_overview():
    """
    High-level municipal demographic and housing totals for Greater Rotterdam.
    Returns city population (673,804 CBS), total residential stock (348,883 BAG dwellings),
    municipal density, city-wide age breakdown, and household metrics.
    """
    cache_key = "living:demographics:overview"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    sql = text("""
        SELECT 
            SUM(d.total_population) as total_pop,
            SUM(h.total_residential_units) as total_residential,
            SUM(d.age_0_14) as a0_14,
            SUM(d.age_15_24) as a15_24,
            SUM(d.age_25_44) as a25_44,
            SUM(d.age_45_64) as a45_64,
            SUM(d.age_65_plus) as a65p,
            SUM(d.total_households) as total_hh,
            SUM(d.single_person_households) as single_hh,
            COUNT(d.id) as district_count,
            to_char(MAX(d.updated_at), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as latest_update
        FROM district_demographics d
        LEFT JOIN district_housing_metrics h ON h.district_code = d.district_code;
    """)

    async with AsyncSessionLocal() as session:
        r = (await session.execute(sql)).fetchone()

    total_pop = int(r.total_pop) if r and r.total_pop else 673804
    total_res = int(r.total_residential) if r and r.total_residential else 348883
    total_hh = int(r.total_hh) if r and r.total_hh else 341933
    single_hh = int(r.single_hh) if r and r.single_hh else 168243
    single_pct = round((single_hh / total_hh) * 100.0, 1) if total_hh else 49.2
    avg_size = round(total_pop / total_hh, 2) if total_hh else 1.9

    overview = DemographicsOverview(
        total_city_population=total_pop,
        total_residential_units=total_res,
        overall_density_km2=3058,  # Official CBS municipal density for Gemeente Rotterdam
        city_wide_age_breakdown=AgeBrackets(
            age_0_14=int(r.a0_14) if r and r.a0_14 else 99640,
            age_15_24=int(r.a15_24) if r and r.a15_24 else 90861,
            age_25_44=int(r.a25_44) if r and r.a25_44 else 214628,
            age_45_64=int(r.a45_64) if r and r.a45_64 else 159220,
            age_65_plus=int(r.a65p) if r and r.a65p else 109455,
        ),
        city_wide_households=total_hh,
        average_household_size=avg_size,
        single_person_households=single_hh,
        single_person_pct=single_pct,
        total_districts=int(r.district_count) if r and r.district_count else 19,
        data_year=2026,
        source="CBS Kerncijfers Wijken en Buurten & Kadaster BAG",
        updated_at=r.latest_update if r else None,
    ).model_dump(mode="json", by_alias=True)

    await set_cached_json(cache_key, overview, ttl_seconds=3600)
    return overview


@router.get("/housing", response_model=HousingListResponse)
async def get_district_housing(
    district: Optional[str] = Query(None, description="Optional filter by district name or code")
):
    """
    Retrieve housing analytics and living area distributions across Rotterdam districts.
    Includes residential stock from Kadaster BAG, average/median surface area (m²),
    construction eras (<1945, 1945-1969, 1970-1999, 2000+), average WOZ, tenure split,
    and civic amenity counts.
    """
    cache_key = f"living:housing:{district or 'all'}"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    conditions = ["1=1"]
    params: Dict[str, Any] = {}

    if district:
        resolved = resolve_district(district)
        if resolved:
            conditions.append("district_code = :resolved_code")
            params["resolved_code"] = resolved[0]
        else:
            conditions.append("(district_code ILIKE :q OR district_name ILIKE :q_pattern)")
            params["q"] = district.strip()
            params["q_pattern"] = f"%{district.strip()}%"

    where_clause = " AND ".join(conditions)

    sql = text(f"""
        SELECT 
            district_code,
            district_name,
            total_residential_units,
            avg_surface_area_m2,
            median_surface_area_m2,
            min_surface_area_m2,
            max_surface_area_m2,
            pre_war_count,
            pre_war_pct,
            post_war_count,
            post_war_pct,
            late_20th_count,
            late_20th_pct,
            modern_count,
            modern_pct,
            average_woz_value,
            owner_occupied_pct,
            social_rent_pct,
            private_rent_pct,
            livability_index,
            safety_index,
            physical_index,
            social_index,
            amenity_counts,
            to_char(updated_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at_str
        FROM district_housing_metrics
        WHERE {where_clause}
        ORDER BY total_residential_units DESC, district_name ASC;
    """)

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(sql, params)).fetchall()

    housing_list = []
    total_stock = 0

    for r in rows:
        total_stock += r.total_residential_units or 0
        amenity_dict = r.amenity_counts if isinstance(r.amenity_counts, dict) else json.loads(r.amenity_counts or "{}")

        housing_list.append(
            HousingMetricsItem(
                district_code=r.district_code,
                district_name=r.district_name,
                total_residential_units=r.total_residential_units or 0,
                surface_area=SurfaceAreaMetrics(
                    average_m2=float(r.avg_surface_area_m2) if r.avg_surface_area_m2 is not None else None,
                    median_m2=float(r.median_surface_area_m2) if r.median_surface_area_m2 is not None else None,
                    min_m2=r.min_surface_area_m2,
                    max_m2=r.max_surface_area_m2,
                ),
                construction_eras=ConstructionEras(
                    pre_war=EraBreakdownItem(
                        count=r.pre_war_count or 0,
                        pct=float(r.pre_war_pct) if r.pre_war_pct is not None else 0.0,
                    ),
                    post_war_reconstruction=EraBreakdownItem(
                        count=r.post_war_count or 0,
                        pct=float(r.post_war_pct) if r.post_war_pct is not None else 0.0,
                    ),
                    late_20th_century=EraBreakdownItem(
                        count=r.late_20th_count or 0,
                        pct=float(r.late_20th_pct) if r.late_20th_pct is not None else 0.0,
                    ),
                    modern=EraBreakdownItem(
                        count=r.modern_count or 0,
                        pct=float(r.modern_pct) if r.modern_pct is not None else 0.0,
                    ),
                ),
                average_woz_value=r.average_woz_value,
                tenure_breakdown=HousingTenure(
                    owner_occupied_pct=float(r.owner_occupied_pct) if r.owner_occupied_pct is not None else None,
                    social_rent_pct=float(r.social_rent_pct) if r.social_rent_pct is not None else None,
                    private_rent_pct=float(r.private_rent_pct) if r.private_rent_pct is not None else None,
                ),
                livability=LivabilityScores(
                    overall_index=float(r.livability_index) if r.livability_index is not None else None,
                    safety_index=float(r.safety_index) if r.safety_index is not None else None,
                    physical_index=float(r.physical_index) if r.physical_index is not None else None,
                    social_index=float(r.social_index) if r.social_index is not None else None,
                ),
                amenity_counts=DistrictAmenityCounts(**amenity_dict),
                updated_at=r.updated_at_str,
            )
        )

    response_data = HousingListResponse(
        total_districts=len(housing_list),
        total_residential_stock=total_stock,
        districts=housing_list,
    ).model_dump(mode="json")

    await set_cached_json(cache_key, response_data, ttl_seconds=3600)
    return response_data


@router.get("/districts/{district_name}/passport", response_model=DistrictPassportFeature)
async def get_district_passport(district_name: str):
    """
    The Unified District Passport: Returns an all-in-one RFC 7946 GeoJSON Feature for a specified
    Rotterdam district (e.g. 'Centrum', 'Feijenoord', 'Kralingen-Crooswijk', 'Delfshaven', 'WK059901'):
    - Demographic profile & age cohorts.
    - Housing metrics, surface area averages, and construction era breakdown.
    - Local amenity & retail density (supermarkets, EV chargers, cameras, water taps, schools).
    - Full MultiPolygon district boundary geometry for seamless MapLibre rendering.
    """
    resolved = resolve_district(district_name)
    if not resolved:
        avail = ", ".join(name for _, name in CANONICAL_DISTRICTS)
        raise HTTPException(
            status_code=404,
            detail=f"District '{district_name}' not found. Available Rotterdam districts: {avail}",
        )

    canonical_code, canonical_name = resolved
    cache_key = f"living:passport:{canonical_code}"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    sql = text("""
        SELECT 
            d.code as district_code,
            d.name as district_name,
            ST_AsGeoJSON(d.geom) as geom_json,
            -- Demographics
            demo.total_population,
            demo.population_density_km2,
            demo.men,
            demo.women,
            demo.age_0_14,
            demo.age_15_24,
            demo.age_25_44,
            demo.age_45_64,
            demo.age_65_plus,
            demo.total_households,
            demo.single_person_households,
            demo.single_person_pct,
            demo.average_household_size,
            demo.average_income_per_inhabitant,
            demo.source as demo_source,
            demo.data_year as demo_year,
            -- Housing
            h.total_residential_units,
            h.avg_surface_area_m2,
            h.median_surface_area_m2,
            h.min_surface_area_m2,
            h.max_surface_area_m2,
            h.pre_war_count,
            h.pre_war_pct,
            h.post_war_count,
            h.post_war_pct,
            h.late_20th_count,
            h.late_20th_pct,
            h.modern_count,
            h.modern_pct,
            h.average_woz_value,
            h.owner_occupied_pct,
            h.social_rent_pct,
            h.private_rent_pct,
            h.livability_index,
            h.safety_index,
            h.physical_index,
            h.social_index,
            h.amenity_counts,
            to_char(GREATEST(demo.updated_at, h.updated_at), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at_str
        FROM rotterdam_districts d
        LEFT JOIN district_demographics demo ON demo.district_code = d.code
        LEFT JOIN district_housing_metrics h ON h.district_code = d.code
        WHERE d.code = :code;
    """)

    async with AsyncSessionLocal() as session:
        r = (await session.execute(sql, {"code": canonical_code})).fetchone()

    if not r:
        raise HTTPException(status_code=404, detail=f"District '{district_name}' data not available in database")

    geom = json.loads(r.geom_json) if r.geom_json else {}
    amenity_dict = r.amenity_counts if isinstance(r.amenity_counts, dict) else json.loads(r.amenity_counts or "{}")
    amenities = DistrictAmenityCounts(**amenity_dict)

    demographics = DemographicsItem(
        district_code=r.district_code,
        district_name=r.district_name,
        total_population=r.total_population,
        population_density_km2=r.population_density_km2,
        men=r.men,
        women=r.women,
        age_brackets=AgeBrackets(
            age_0_14=r.age_0_14,
            age_15_24=r.age_15_24,
            age_25_44=r.age_25_44,
            age_45_64=r.age_45_64,
            age_65_plus=r.age_65_plus,
        ),
        total_households=r.total_households,
        single_person_households=r.single_person_households,
        single_person_pct=float(r.single_person_pct) if r.single_person_pct is not None else None,
        average_household_size=float(r.average_household_size) if r.average_household_size is not None else None,
        average_income_per_inhabitant=r.average_income_per_inhabitant,
        source=r.demo_source or "CBS Kerncijfers Wijken en Buurten",
        data_year=r.demo_year or 2026,
        updated_at=r.updated_at_str,
    )

    housing = HousingMetricsItem(
        district_code=r.district_code,
        district_name=r.district_name,
        total_residential_units=r.total_residential_units or 0,
        surface_area=SurfaceAreaMetrics(
            average_m2=float(r.avg_surface_area_m2) if r.avg_surface_area_m2 is not None else None,
            median_m2=float(r.median_surface_area_m2) if r.median_surface_area_m2 is not None else None,
            min_m2=r.min_surface_area_m2,
            max_m2=r.max_surface_area_m2,
        ),
        construction_eras=ConstructionEras(
            pre_war=EraBreakdownItem(
                count=r.pre_war_count or 0,
                pct=float(r.pre_war_pct) if r.pre_war_pct is not None else 0.0,
            ),
            post_war_reconstruction=EraBreakdownItem(
                count=r.post_war_count or 0,
                pct=float(r.post_war_pct) if r.post_war_pct is not None else 0.0,
            ),
            late_20th_century=EraBreakdownItem(
                count=r.late_20th_count or 0,
                pct=float(r.late_20th_pct) if r.late_20th_pct is not None else 0.0,
            ),
            modern=EraBreakdownItem(
                count=r.modern_count or 0,
                pct=float(r.modern_pct) if r.modern_pct is not None else 0.0,
            ),
        ),
        average_woz_value=r.average_woz_value,
        tenure_breakdown=HousingTenure(
            owner_occupied_pct=float(r.owner_occupied_pct) if r.owner_occupied_pct is not None else None,
            social_rent_pct=float(r.social_rent_pct) if r.social_rent_pct is not None else None,
            private_rent_pct=float(r.private_rent_pct) if r.private_rent_pct is not None else None,
        ),
        livability=LivabilityScores(
            overall_index=float(r.livability_index) if r.livability_index is not None else None,
            safety_index=float(r.safety_index) if r.safety_index is not None else None,
            physical_index=float(r.physical_index) if r.physical_index is not None else None,
            social_index=float(r.social_index) if r.social_index is not None else None,
        ),
        amenity_counts=amenities,
        updated_at=r.updated_at_str,
    )

    passport = DistrictPassportFeature(
        type="Feature",
        id=canonical_code,
        geometry=geom,
        properties=DistrictPassportProperties(
            district_code=canonical_code,
            district_name=canonical_name,
            demographics=demographics,
            housing=housing,
            amenities=amenities,
            livability=LivabilityScores(
                overall_index=float(r.livability_index) if r.livability_index is not None else None,
                safety_index=float(r.safety_index) if r.safety_index is not None else None,
                physical_index=float(r.physical_index) if r.physical_index is not None else None,
                social_index=float(r.social_index) if r.social_index is not None else None,
            ),
            updated_at=r.updated_at_str,
        ),
    ).model_dump(mode="json", by_alias=True)

    await set_cached_json(cache_key, passport, ttl_seconds=3600)
    return passport
