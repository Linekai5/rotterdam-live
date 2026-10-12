"""Schemas for Rotterdam Retail Infrastructure & Commercial Facilities."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from app.schemas.geojson import PointGeometry


class RetailProperties(BaseModel):
    """Structured properties for a verified commercial shop or retail venue."""
    id: str = Field(..., description="Unique venue identifier (e.g. retail-osm-node-123)")
    name: str = Field(..., description="Trade name of store or venue")
    brand: Optional[str] = Field(None, description="Retail brand or corporate chain name")
    shop_type: str = Field(..., description="Retail subcategory (supermarket, clothes, bakery, chemist, etc.)")
    street_name: Optional[str] = Field(None, description="Street name")
    house_number: Optional[str] = Field(None, description="House number")
    postal_code: Optional[str] = Field(None, description="Postal code")
    city: str = Field(default="Rotterdam", description="City / municipality")
    district: Optional[str] = Field(None, description="Official Rotterdam municipal district")
    bag_address_id: Optional[str] = Field(None, description="Linked official Kadaster BAG address ID")
    bag_pand_id: Optional[str] = Field(None, description="Linked official Kadaster BAG building pand ID")
    opening_hours: Optional[str] = Field(None, description="Standardized opening hours specification")
    phone: Optional[str] = Field(None, description="Contact telephone number")
    website: Optional[str] = Field(None, description="Official website URL")
    wheelchair: Optional[str] = Field(None, description="Wheelchair accessibility status")
    details: Dict[str, Any] = Field(default_factory=dict, description="Raw source attributes and metadata")


class RetailFeature(BaseModel):
    """RFC 7946 GeoJSON Feature for a retail facility."""
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: PointGeometry
    properties: RetailProperties


class RetailFeatureCollection(BaseModel):
    """RFC 7946 GeoJSON FeatureCollection of retail venues."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[RetailFeature] = Field(default_factory=list)
    total_count: Optional[int] = Field(None, description="Total matching records count")


class RetailStats(BaseModel):
    """Aggregate statistics for retail infrastructure across Rotterdam."""
    total_venues: int
    categories: Dict[str, int]
    districts: Dict[str, int]
    supermarkets_count: int
    bag_linked_count: int
