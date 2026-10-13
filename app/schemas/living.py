"""Pydantic schemas for the Rotterdam Live /living domain.

Demographics, Housing Analytics, Livability Indices, and District Passports.
"""
from typing import Any, Dict, List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AgeBrackets(BaseModel):
    """CBS standard age brackets."""
    age_0_14: Optional[int] = Field(
        None, alias="0-14", validation_alias=AliasChoices("0-14", "0_14", "age_0_14"), description="Age 0 to 14"
    )
    age_15_24: Optional[int] = Field(
        None, alias="15-24", validation_alias=AliasChoices("15-24", "15_24", "age_15_24"), description="Age 15 to 24"
    )
    age_25_44: Optional[int] = Field(
        None, alias="25-44", validation_alias=AliasChoices("25-44", "25_44", "age_25_44"), description="Age 25 to 44"
    )
    age_45_64: Optional[int] = Field(
        None, alias="45-64", validation_alias=AliasChoices("45-64", "45_64", "age_45_64"), description="Age 45 to 64"
    )
    age_65_plus: Optional[int] = Field(
        None, alias="65+", validation_alias=AliasChoices("65+", "65_plus", "age_65_plus"), description="Age 65 and older"
    )

    model_config = ConfigDict(populate_by_name=True)


class DemographicsItem(BaseModel):
    """Demographics profile for a single Rotterdam district."""
    district_code: str = Field(..., description="Official CBS district code (e.g. 'WK059901')")
    district_name: str = Field(..., description="Official district name (e.g. 'Rotterdam Centrum')")
    total_population: Optional[int] = Field(None, description="Current population count")
    population_density_km2: Optional[int] = Field(None, description="Inhabitants per square kilometer")
    men: Optional[int] = Field(None, description="Male population count")
    women: Optional[int] = Field(None, description="Female population count")
    age_brackets: AgeBrackets = Field(default_factory=AgeBrackets, description="Age distribution breakdown")
    total_households: Optional[int] = Field(None, description="Total households count")
    single_person_households: Optional[int] = Field(None, description="Single-person households count")
    single_person_pct: Optional[float] = Field(None, description="Percentage of single-person households")
    average_household_size: Optional[float] = Field(None, description="Average number of persons per household")
    average_income_per_inhabitant: Optional[int] = Field(None, description="Average income per inhabitant in Euros")
    source: str = Field("CBS Kerncijfers Wijken en Buurten", description="Data authority source")
    data_year: int = Field(2026, description="Reference data publication year")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)")

    model_config = ConfigDict(populate_by_name=True)


class DemographicsListResponse(BaseModel):
    """Response containing demographic profiles across Rotterdam districts."""
    total_districts: int = Field(..., description="Number of districts returned")
    data_year: int = Field(2026, description="Data publication year")
    source: str = Field("CBS Kerncijfers Wijken en Buurten & Gemeente Rotterdam", description="Data authority")
    districts: List[DemographicsItem] = Field(..., description="List of district demographic profiles")


class DemographicsOverview(BaseModel):
    """Municipal-level high-level demographic and housing summary for Rotterdam."""
    total_city_population: int = Field(..., description="Total official population of Rotterdam municipality")
    total_residential_units: int = Field(..., description="Total residential dwellings registered in Kadaster BAG")
    overall_density_km2: int = Field(..., description="Municipal population density per km2")
    city_wide_age_breakdown: AgeBrackets = Field(..., description="Municipal age distribution across standard CBS brackets")
    city_wide_households: int = Field(..., description="Total households in the municipality")
    average_household_size: float = Field(..., description="Average household size across Rotterdam")
    single_person_households: int = Field(..., description="Total single-person households")
    single_person_pct: float = Field(..., description="Percentage of single-person households")
    total_districts: int = Field(19, description="Total canonical districts in Rotterdam")
    data_year: int = Field(2026, description="Reference publication year")
    source: str = Field("CBS Kerncijfers Wijken en Buurten & Kadaster BAG", description="Data authorities")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class SurfaceAreaMetrics(BaseModel):
    """Dwelling living area statistics in square meters."""
    average_m2: Optional[float] = Field(None, description="Mean surface area in m2")
    median_m2: Optional[float] = Field(None, description="Median surface area in m2")
    min_m2: Optional[int] = Field(None, description="Minimum dwelling surface area in m2")
    max_m2: Optional[int] = Field(None, description="Maximum dwelling surface area in m2")


class EraBreakdownItem(BaseModel):
    """Construction era housing unit count and percentage."""
    count: int = Field(0, description="Dwellings constructed in era")
    pct: float = Field(0.0, description="Percentage of residential stock")


class ConstructionEras(BaseModel):
    """Historical construction eras breakdown for residential buildings."""
    pre_war: EraBreakdownItem = Field(default_factory=EraBreakdownItem, description="Pre-war (< 1945)")
    post_war_reconstruction: EraBreakdownItem = Field(
        default_factory=EraBreakdownItem, description="Post-war reconstruction (1945–1969)"
    )
    late_20th_century: EraBreakdownItem = Field(
        default_factory=EraBreakdownItem, description="Late 20th century (1970–1999)"
    )
    modern: EraBreakdownItem = Field(default_factory=EraBreakdownItem, description="Modern era (2000–present)")


class HousingTenure(BaseModel):
    """Housing ownership and rental split."""
    owner_occupied_pct: Optional[float] = Field(None, description="Owner-occupied percentage (Koopwoningen %)")
    social_rent_pct: Optional[float] = Field(None, description="Social rent / housing corporation %")
    private_rent_pct: Optional[float] = Field(None, description="Private rent percentage %")


class LivabilityScores(BaseModel):
    """Gemeente Rotterdam Wijkprofiel Livability index scores (baseline ~100)."""
    overall_index: Optional[float] = Field(None, description="Overall district livability index score")
    safety_index: Optional[float] = Field(None, description="Safety index score (Veiligheidsindex)")
    physical_index: Optional[float] = Field(None, description="Physical environment index (Fysieke index)")
    social_index: Optional[float] = Field(None, description="Social cohesion index (Sociale index)")


class DistrictAmenityCounts(BaseModel):
    """Count of amenities and civic infrastructure within district boundaries."""
    supermarkets: int = Field(0, description="Supermarkets count")
    retail_stores: int = Field(0, description="Total verified commercial retail storefronts")
    schools: int = Field(0, description="Educational facilities (BAG onderwijsfunctie)")
    healthcare: int = Field(0, description="Healthcare clinics & hospitals (BAG gezondheidszorgfunctie)")
    sports: int = Field(0, description="Sports complexes & facilities (BAG sportfunctie)")
    ev_chargers: int = Field(0, description="Public EV charging stations")
    cameras: int = Field(0, description="Outdoor security & traffic cameras")
    water_taps: int = Field(0, description="Public drinking water fountains (Evides)")
    toilets: int = Field(0, description="Public toilets and urinals")
    aeds: int = Field(0, description="Public automated external defibrillators")


class HousingMetricsItem(BaseModel):
    """Detailed housing metrics and livability indicators for a single district."""
    district_code: str = Field(..., description="Official CBS district code")
    district_name: str = Field(..., description="District name")
    total_residential_units: int = Field(..., description="Total residential dwellings registered in Kadaster BAG")
    surface_area: SurfaceAreaMetrics = Field(default_factory=SurfaceAreaMetrics, description="Living area in m2")
    construction_eras: ConstructionEras = Field(default_factory=ConstructionEras, description="Building eras breakdown")
    average_woz_value: Optional[int] = Field(None, description="Official average WOZ property value in Euros")
    tenure_breakdown: HousingTenure = Field(default_factory=HousingTenure, description="Housing tenure breakdown")
    livability: LivabilityScores = Field(default_factory=LivabilityScores, description="Wijkprofiel livability scores")
    amenity_counts: DistrictAmenityCounts = Field(default_factory=DistrictAmenityCounts, description="Amenity access counts")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)")


class HousingListResponse(BaseModel):
    """Response containing housing metrics across all Rotterdam districts."""
    total_districts: int = Field(..., description="Number of districts returned")
    total_residential_stock: int = Field(..., description="Total residential dwellings across Rotterdam")
    districts: List[HousingMetricsItem] = Field(..., description="District housing metrics")


class DistrictPassportProperties(BaseModel):
    """Aggregated properties in the District Passport GeoJSON Feature."""
    district_code: str = Field(..., description="Official district code")
    district_name: str = Field(..., description="District name")
    demographics: DemographicsItem = Field(..., description="Demographic profile")
    housing: HousingMetricsItem = Field(..., description="Housing metrics & eras")
    amenities: DistrictAmenityCounts = Field(..., description="Local amenity counts")
    livability: LivabilityScores = Field(..., description="Livability index scores")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class DistrictPassportFeature(BaseModel):
    """The Unified District Passport formatted as an RFC 7946 GeoJSON Feature."""
    type: str = Field("Feature", description="GeoJSON type")
    id: str = Field(..., description="Feature ID (district code)")
    geometry: Dict[str, Any] = Field(..., description="MultiPolygon district boundary geometry in WGS84")
    properties: DistrictPassportProperties = Field(..., description="Consolidated passport properties")
