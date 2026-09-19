"""
Tests for configuration and settings.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def test_scenario_yaml_loads(scenario_config: dict) -> None:
    """Fani scenario YAML loads and has required top-level keys."""
    required_keys = [
        "name", "basin", "storm_id", "aoi_bbox", "landfall",
        "districts", "surge", "rainfall", "sar", "insurance",
    ]
    for key in required_keys:
        assert key in scenario_config, f"Missing key: {key}"


def test_aoi_bbox_valid(scenario_config: dict) -> None:
    """AOI bounding box has 4 values and valid ranges."""
    bbox = scenario_config["aoi_bbox"]
    assert len(bbox) == 4, "AOI bbox must have 4 values"
    lon_min, lat_min, lon_max, lat_max = bbox
    assert -180 <= lon_min < lon_max <= 180, "Longitude range invalid"
    assert -90 <= lat_min < lat_max <= 90, "Latitude range invalid"


def test_landfall_in_aoi(scenario_config: dict) -> None:
    """Landfall coordinates are within or near the AOI."""
    bbox = scenario_config["aoi_bbox"]
    landfall = scenario_config["landfall"]
    lon_min, lat_min, lon_max, lat_max = bbox
    lat = landfall["lat"]
    lon = landfall["lon"]
    # Allow 1 degree buffer (storm centre may be slightly outside AOI)
    assert lon_min - 1 <= lon <= lon_max + 1, f"Landfall lon {lon} outside AOI"
    assert lat_min - 1 <= lat <= lat_max + 1, f"Landfall lat {lat} outside AOI"


def test_districts_non_empty(scenario_config: dict) -> None:
    """Districts list is non-empty."""
    assert len(scenario_config["districts"]) > 0


def test_insurance_tiers_payout_order(scenario_config: dict) -> None:
    """Insurance tiers are in descending payout order."""
    tiers = scenario_config["insurance"]["tiers"]
    payouts = [t["payout_pct"] for t in tiers]
    assert payouts == sorted(payouts, reverse=True), "Tiers not in descending payout order"


def test_surge_thresholds_positive(scenario_config: dict) -> None:
    """Surge model thresholds are positive numbers."""
    surge = scenario_config["surge"]
    assert surge["inland_attenuation_per_km"] > 0
    assert surge["max_inland_km"] > 0
    assert surge["substation_flood_threshold_m"] > 0


def test_settings_loads() -> None:
    """Settings module loads without error."""
    from config.settings import get_settings
    s = get_settings()
    assert s.default_scenario == "fani_2019"
    assert s.dry_run is True  # Default should be safe


def test_processed_dir_created() -> None:
    """Settings creates the processed dir."""
    from config.settings import get_settings
    s = get_settings()
    assert s.processed_dir.exists()
