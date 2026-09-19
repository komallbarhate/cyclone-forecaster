"""
Tests for Step 06: OSM Critical Infrastructure Extraction
===========================================================
Validates point extraction for substations, hospitals, shelters,
and arterial road network (trunk, primary, secondary per Amendment 7).
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


def test_infra_geojson_structure(scenario):
    """Verify infra.geojson exists and contains substations, hospitals, and shelters."""
    infra_file = PROCESSED_DIR / "infra.geojson"
    if not infra_file.exists():
        pytest.skip("infra.geojson not yet generated; run step_06_osm_infra.py")

    with open(infra_file) as f:
        data = json.load(f)

    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) >= 15, "Should have critical infrastructure points across districts"

    types_found = {f["properties"].get("type") for f in features}
    assert "substation" in types_found, "Must include power substations"
    assert "hospital" in types_found, "Must include hospitals"
    assert "shelter" in types_found, "Must include cyclone shelters"

    districts_found = {f["properties"].get("district") for f in features}
    for d in scenario["districts"]:
        assert d in districts_found, f"District {d} missing from critical infrastructure"


def test_arterial_roads_structure():
    """Verify roads.geojson contains only trunk, primary, or secondary highways per Amendment 7."""
    roads_file = PROCESSED_DIR / "roads.geojson"
    if not roads_file.exists():
        pytest.skip("roads.geojson not yet generated; run step_06_osm_infra.py")

    with open(roads_file) as f:
        data = json.load(f)

    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) >= 5, "Should have arterial road segments"

    allowed_types = {"trunk", "primary", "secondary", "trunk_link", "primary_link"}
    for f in features:
        highway_type = f["properties"].get("highway")
        assert highway_type in allowed_types, f"Non-arterial road type found: {highway_type}"


def test_infra_meta_file():
    """Verify infra_meta.json has valid counts and AOI bounding box."""
    meta_file = PROCESSED_DIR / "infra_meta.json"
    if not meta_file.exists():
        pytest.skip("infra_meta.json not yet generated")

    with open(meta_file) as f:
        meta = json.load(f)

    assert meta.get("substations", 0) > 0
    assert meta.get("hospitals", 0) > 0
    assert meta.get("shelters", 0) > 0
    assert meta.get("arterial_roads", 0) > 0
