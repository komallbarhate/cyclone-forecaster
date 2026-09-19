"""
Tests for Step 02: Holland Parametric Wind Field
=================================================
Validates Holland (1980) wind field physics, asymmetry calculation,
spatial grid output, and district time series.
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


def test_holland_physics_imports():
    """Verify Holland wind calculation function can be imported and runs."""
    from pipeline.step_02_wind_field import holland_wind_speed

    # Test at RMW: should be close to surface vmax (~140-180 km/h)
    vmax_ms = 180.0 / 3.6  # 50 m/s
    v_rmw_ms = holland_wind_speed(r_km=35.0, rmw_km=35.0, vmax_ms=vmax_ms, mslp_hpa=935.0, lat=19.8)
    v_rmw_kmh = v_rmw_ms * 3.6
    assert 130.0 <= v_rmw_kmh <= 190.0, f"Expected wind near vmax at RMW, got {v_rmw_kmh}"

    # Test far field: should drop off substantially
    v_far_ms = holland_wind_speed(r_km=200.0, rmw_km=35.0, vmax_ms=vmax_ms, mslp_hpa=935.0, lat=19.8)
    assert v_far_ms < v_rmw_ms * 0.6, f"Expected far-field wind to drop below 60% of peak, got {v_far_ms * 3.6}"

    # Test center (eye): should drop towards zero
    v_eye_ms = holland_wind_speed(r_km=5.0, rmw_km=35.0, vmax_ms=vmax_ms, mslp_hpa=935.0, lat=19.8)
    assert v_eye_ms < v_rmw_ms * 0.7, f"Expected eye wind to drop, got {v_eye_ms * 3.6}"


def test_wind_max_geojson_structure():
    """Verify wind_max.geojson exists and contains polygon grid cells with wind fields."""
    wind_file = PROCESSED_DIR / "wind_max.geojson"
    if not wind_file.exists():
        pytest.skip("wind_max.geojson not yet generated; run step_02_wind_field.py")

    with open(wind_file) as f:
        data = json.load(f)

    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) > 20, "Should have multiple grid cells"

    max_v = max(f["properties"].get("wind_kmh", f["properties"].get("vmax_kmh", 0)) for f in features)
    assert max_v > 120.0, f"Peak wind speed {max_v} km/h too low for Cyclone Fani"


def test_wind_district_ts(scenario):
    """Verify wind_district_ts.json contains time series for all scenario districts."""
    ts_file = PROCESSED_DIR / "wind_district_ts.json"
    if not ts_file.exists():
        pytest.skip("wind_district_ts.json not yet generated")

    with open(ts_file) as f:
        ts_data = json.load(f)

    for dist in scenario["districts"]:
        assert dist in ts_data, f"District {dist} missing from wind time series"
        entries = ts_data[dist]
        assert len(entries) > 10, f"District {dist} should have multiple hourly steps"
        # Check that each entry has time and wind
        for entry in entries:
            assert "time_utc" in entry
            assert "wind_kmh" in entry
            assert entry["wind_kmh"] >= 0
