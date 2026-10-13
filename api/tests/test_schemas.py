"""Unit tests for strict GeoJSON and Canonical Event schemas."""
from datetime import datetime, timezone
import pytest
from app.schemas.geojson import (
    PointGeometry,
    PolygonGeometry,
    CanonicalEventProperties,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
)


def test_point_geometry_valid():
    pt = PointGeometry(coordinates=[4.4777, 51.9244])
    assert pt.type == "Point"
    assert pt.coordinates == [4.4777, 51.9244]


def test_canonical_properties_validation():
    props = CanonicalEventProperties(
        id="p2000-12345",
        category="emergency",
        subcategory="brandweer",
        severity=3,
        timestamp=datetime.now(timezone.utc),
        district="Centrum",
        title="Binnenbrand Keilestraat",
        details={"prio": 1},
    )
    assert props.id == "p2000-12345"
    assert props.category == "emergency"
    assert props.severity == 3


def test_geojson_feature_and_collection():
    pt = PointGeometry(coordinates=[4.4777, 51.9244])
    props = CanonicalEventProperties(
        id="p2000-12345",
        category="emergency",
        subcategory="brandweer",
        severity=3,
        timestamp=datetime.now(timezone.utc),
        district="Centrum",
        title="Binnenbrand Keilestraat",
        details={"prio": 1},
    )
    feature = GeoJSONFeature(type="Feature", geometry=pt, properties=props)
    collection = GeoJSONFeatureCollection(type="FeatureCollection", features=[feature])

    dumped = collection.model_dump()
    assert dumped["type"] == "FeatureCollection"
    assert len(dumped["features"]) == 1
    assert dumped["features"][0]["geometry"]["type"] == "Point"
    assert dumped["features"][0]["properties"]["category"] == "emergency"
