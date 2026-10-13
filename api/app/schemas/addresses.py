"""Schemas for Official Kadaster BAG Addresses (Gemeentecode 0599 Rotterdam)."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from app.schemas.geojson import PointGeometry


class AddressProperties(BaseModel):
    """Structured properties for an official Kadaster BAG address."""
    address_id: str = Field(..., description="Official BAG Verblijfsobject ID (e.g. 0599010000...)")
    pand_id: Optional[str] = Field(None, description="Linked BAG Pand ID")
    street_name: str = Field(..., description="Official street name (openbare ruimte)")
    house_number: int = Field(..., description="House number")
    house_letter: Optional[str] = Field(None, description="House letter")
    house_addition: Optional[str] = Field(None, description="House number addition")
    postal_code: Optional[str] = Field(None, description="Formatted 6-character Dutch postal code")
    city: str = Field(default="Rotterdam", description="Municipality or town name")
    purpose: Optional[str] = Field(None, description="Official BAG gebruiksdoel (e.g. woonfunctie, winkelfunctie)")
    surface_area: Optional[int] = Field(None, description="Floor surface area in square meters (m²)")
    construction_year: Optional[int] = Field(None, description="Construction year of linked building")
    status: Optional[str] = Field(None, description="Verblijfsobject status")
    district: Optional[str] = Field(None, description="Spatially assigned Rotterdam municipal district")
    display_name: str = Field(..., description="Formatted full address string")


class AddressFeature(BaseModel):
    """RFC 7946 GeoJSON Feature for an official BAG address."""
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: PointGeometry
    properties: AddressProperties


class AddressFeatureCollection(BaseModel):
    """RFC 7946 GeoJSON FeatureCollection of Kadaster BAG addresses."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[AddressFeature] = Field(default_factory=list)
    total_count: Optional[int] = Field(None, description="Total matching records count")


class AddressStats(BaseModel):
    """Aggregate breakdown of BAG addresses in Rotterdam."""
    total_addresses: int
    purposes: Dict[str, int]
    districts: Dict[str, int]
