"""
Tests for Step 03 & Step 05: Storm Surge Physics & SAR Validation
==================================================================
Validates physical laws (inverse barometer, wind setup),
bathtub inundation depths, and Sentinel-1 SAR validation metrics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def test_inverse_barometer_formula():
    """Verify Inverse Barometer calculation: ~1 cm sea level rise per 1 hPa pressure deficit."""
    from pipeline.step_03_surge_model import compute_inverse_barometer

    # 1010 hPa env, 932 hPa center -> 78 hPa deficit
    eta_ib = compute_inverse_barometer(mslp_hpa=932.0, coeff=0.01, p_env=1010.0)
    assert 0.75 <= eta_ib <= 0.82, f"Expected ~0.78m IB surge, got {eta_ib}"

    # No deficit -> 0 rise
    eta_zero = compute_inverse_barometer(mslp_hpa=1015.0, coeff=0.01, p_env=1010.0)
    assert eta_zero == 0.0


def test_wind_setup_physics():
    """Verify wind setup scales with U^2 and cosine of onshore angle."""
    from pipeline.step_03_surge_model import compute_wind_setup

    # Onshore wind (aligned, cos = 1)
    setup_aligned = compute_wind_setup(
        wind_kmh=150.0,
        wind_dir_deg=145.0,
        coast_normal_deg=145.0,
        shelf_depth_m=15.0,
        fetch_km=60.0,
        wind_setup_coeff=3.0e-6,
    )
    assert setup_aligned > 1.0, f"Expected significant setup for 150 km/h onshore wind, got {setup_aligned}"

    # Offshore wind (opposite, cos = 0 clipped)
    setup_offshore = compute_wind_setup(
        wind_kmh=150.0,
        wind_dir_deg=325.0,
        coast_normal_deg=145.0,
        shelf_depth_m=15.0,
        fetch_km=60.0,
        wind_setup_coeff=3.0e-6,
    )
    assert setup_offshore == 0.0, f"Offshore wind should have 0 onshore setup, got {setup_offshore}"


def test_surge_outputs_and_depths():
    """Verify surge_hourly.geojson and surge_inundation.geojson exist and have realistic values."""
    hourly_file = PROCESSED_DIR / "surge_hourly.geojson"
    inund_file = PROCESSED_DIR / "surge_inundation.geojson"

    if not hourly_file.exists() or not inund_file.exists():
        pytest.skip("Surge output files not generated yet; run step_03_surge_model.py")

    with open(hourly_file) as f:
        hourly_data = json.load(f)
    assert hourly_data.get("type") == "FeatureCollection"
    assert len(hourly_data.get("features", [])) > 50

    # Max surge should be between 3.5m and 5.0m for Cyclone Fani
    max_surge = max(f["properties"].get("surge_total_m", 0) for f in hourly_data["features"])
    assert 3.5 <= max_surge <= 5.5, f"Expected realistic peak surge 3.5-5.5m, got {max_surge}"

    with open(inund_file) as f:
        inund_data = json.load(f)
    assert len(inund_data.get("features", [])) > 100
    for f in inund_data["features"][:10]:
        assert f["geometry"]["type"] == "Polygon"
        assert "depth_m" in f["properties"]
        assert f["properties"]["depth_m"] > 0.1


def test_sar_validation_metrics():
    """Verify metrics.json contains valid IoU, Precision, Recall, F1, calibration comparison, and track error."""
    metrics_file = PROCESSED_DIR / "metrics.json"
    if not metrics_file.exists():
        pytest.skip("metrics.json not generated yet; run step_05_sar_validation.py")

    with open(metrics_file) as f:
        metrics = json.load(f)

    aoi = metrics.get("aoi_metrics", {})
    assert aoi.get("iou", 0) > 0.5, f"IoU should exceed 0.5, got {aoi.get('iou')}"
    assert aoi.get("f1", 0) > 0.7, f"F1 should exceed 0.7, got {aoi.get('f1')}"
    assert aoi.get("precision", 0) > 0.7
    assert aoi.get("recall", 0) > 0.8

    # Verify calibration documented
    calib = metrics.get("calibration", {})
    assert "metrics_before" in calib
    assert "metrics_after" in calib
    assert calib.get("delta_f1", 0) > 0, "Calibration should improve F1"

    # Verify track error documented
    track_err = metrics.get("track_error", {})
    assert "cross_track_error_km" in track_err
    assert track_err["cross_track_error_km"] < 60.0
