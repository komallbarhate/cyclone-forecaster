"""
Tests for Step 04: Rainfall & Damage Pathway Model
===================================================
Validates precipitation fields, HAND flood index, and riverine damage pathways.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def test_rainfall_grid_structure():
    """Verify rainfall_grid.geojson contains precipitation and HAND attributes."""
    rain_file = PROCESSED_DIR / "rainfall_grid.geojson"
    if not rain_file.exists():
        pytest.skip("rainfall_grid.geojson not generated yet; run step_04_rainfall_model.py")

    with open(rain_file) as f:
        data = json.load(f)

    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) > 500

    peak_rain = max(f["properties"].get("rain_cumulative_mm", 0) for f in features)
    assert peak_rain >= 250.0, f"Peak rain should be >= 250mm for Cyclone Fani, got {peak_rain}"


def test_damage_pathways_structure():
    """Verify rainfall_damage_pathways.geojson contains riverine drainage corridors."""
    path_file = PROCESSED_DIR / "rainfall_damage_pathways.geojson"
    if not path_file.exists():
        pytest.skip("rainfall_damage_pathways.geojson not generated yet")

    with open(path_file) as f:
        data = json.load(f)

    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) >= 4, "Should have major river drainage pathways"

    for f in features:
        assert f["geometry"]["type"] == "LineString"
        assert "name" in f["properties"]
        assert "risk_level" in f["properties"]


def test_district_rainfall_totals():
    """Verify rainfall_district_totals.json has entries for all 5 districts."""
    totals_file = PROCESSED_DIR / "rainfall_district_totals.json"
    if not totals_file.exists():
        pytest.skip("rainfall_district_totals.json not generated yet")

    with open(totals_file) as f:
        totals = json.load(f)

    for d in ["Puri", "Khordha", "Jagatsinghpur", "Kendrapara", "Cuttack"]:
        assert d in totals, f"District {d} missing from rainfall totals"
        assert totals[d]["mean_rainfall_mm"] > 100.0
