"""
Tests for Step 01: Track Fetch and Interpolation
=================================================
Validates track extraction, cubic spline interpolation, landfall coordinates,
and GeoJSON generation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@pytest.fixture(scope="module")
def scenario():
    cfg_path = PROJECT_ROOT / "config" / "scenarios" / "fani_2019.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def test_track_geojson_structure():
    """Verify track_hourly.geojson exists or can be generated, and has valid FeatureCollection structure."""
    track_file = PROCESSED_DIR / "track_hourly.geojson"
    if not track_file.exists():
        pytest.skip("track_hourly.geojson not yet generated; run step_01_fetch_track.py")

    with open(track_file) as f:
        data = json.load(f)

    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) > 10, "Should have hourly steps"

    # Verify each feature has required properties
    for feat in features:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        assert geom.get("type") in ("Point", "LineString")
        if geom.get("type") == "Point":
            assert "time_utc" in props
            assert "vmax_kmh" in props
            assert "mslp_hpa" in props
            assert props["vmax_kmh"] >= 0
            assert props["mslp_hpa"] > 880


def test_track_landfall_proximity(scenario):
    """Verify landfall point is within 50 km of official IMD landfall coordinates."""
    track_file = PROCESSED_DIR / "track_hourly.geojson"
    if not track_file.exists():
        pytest.skip("track_hourly.geojson not yet generated")

    with open(track_file) as f:
        data = json.load(f)

    target_lat = scenario["landfall"]["lat"]
    target_lon = scenario["landfall"]["lon"]

    # Find the step closest to landfall time
    min_dist = float("inf")
    for feat in data.get("features", []):
        if feat.get("geometry", {}).get("type") == "Point":
            coords = feat["geometry"]["coordinates"]
            dist = ((coords[1] - target_lat) ** 2 + (coords[0] - target_lon) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist

    # Distance in degrees should be small (< 0.5 deg ~ 55 km)
    assert min_dist < 0.5, f"Track closest approach {min_dist:.2f} deg is too far from landfall"


def test_track_meta_file():
    """Verify track_meta.json contains peak wind, minimum pressure and citation."""
    meta_file = PROCESSED_DIR / "track_meta.json"
    if not meta_file.exists():
        pytest.skip("track_meta.json not yet generated")

    with open(meta_file) as f:
        meta = json.load(f)

    assert "peak_vmax_kmh" in meta
    assert "min_mslp_hpa" in meta
    assert meta["peak_vmax_kmh"] > 160  # Category 4/5 equivalent (>160 km/h)
    assert meta["min_mslp_hpa"] < 960   # Extremely severe cyclonic storm
    assert "data_source" in meta
