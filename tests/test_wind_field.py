"""
Tests for Step 02: Holland Parametric Wind Field
=================================================
Validates Holland (1980) wind field physics, the WMO 1-min→10-min conversion
factor, spatial grid output, district time series, and the computed vs IBTrACS
peak consistency check via wind_meta.json.
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


def test_surface_wind_factor_is_wmo():
    """SURFACE_WIND_FACTOR must be 0.93 per Harper et al. (2010) WMO/TD-1555.

    Harper, B.A., Kepert, J.D., and Ginger, J.D. (2010). Guidelines for
    Converting Between Various Wind Averaging Periods in Tropical Cyclone
    Conditions. WMO/TD-No.1555. World Meteorological Organization.
    https://library.wmo.int/doc_num.php?explnum_id=290

    Harper et al. recommend 0.93 for open-ocean exposure (marine boundary
    layer), consistent with IBTrACS JTWC observations recorded over ocean.
    The legacy value of 0.88 (pre-2010 WMO practice) under-estimates the
    10-min equivalent by ~5% and is superseded by the 2010 guidance.
    """
    from pipeline.step_02_wind_field import SURFACE_WIND_FACTOR
    assert SURFACE_WIND_FACTOR == pytest.approx(0.93, abs=1e-6), (
        f"Expected 0.93 (Harper et al. 2010 WMO/TD-1555, open-ocean), got "
        f"{SURFACE_WIND_FACTOR}. The legacy 0.88 under-estimates by ~5%; "
        "0.93 is the current WMO recommendation for JTWC 1-min winds."
    )


def test_holland_b_units():
    """B parameter must use Pa (not hPa) for ΔP and m/s for Vmax."""
    from pipeline.step_02_wind_field import holland_b, PENV_HPA, RHO_AIR
    import math

    # Fani at peak: mslp=932 hPa, vmax=115 kt
    b = holland_b(mslp_hpa=932.0, vmax_kt=115.0)
    # B should be in [1.0, 2.5] per Holland (1980); typical tropical cyclone ~1.2–1.8
    assert 1.0 <= b <= 2.5, f"B={b:.4f} out of valid range [1.0, 2.5]"
    # For Fani-like parameters, B should be around 1.3–1.6
    assert 1.1 <= b <= 1.8, f"B={b:.4f} implausible for Fani parameters (expected ~1.3–1.6)"


def test_holland_physics_at_rmw():
    """At r=RMW, surface wind should be close to vmax * SURFACE_WIND_FACTOR."""
    from pipeline.step_02_wind_field import holland_wind_speed, SURFACE_WIND_FACTOR

    # Fani near-landfall: vmax=191 km/h (1-min), rmw=22 km, mslp=934 hPa
    vmax_ms = 191.0 / 3.6
    expected_surface_ms = vmax_ms * SURFACE_WIND_FACTOR  # 10-min equivalent

    v_rmw_ms = holland_wind_speed(
        r_km=22.0, rmw_km=22.0, vmax_ms=vmax_ms, mslp_hpa=934.0, lat=19.8
    )
    # Allow ±15% tolerance (gradient wind reconstruction from B, not exact inversion)
    lo = expected_surface_ms * 0.85
    hi = expected_surface_ms * 1.15
    assert lo <= v_rmw_ms <= hi, (
        f"Wind at RMW: {v_rmw_ms*3.6:.1f} km/h, "
        f"expected {lo*3.6:.1f}–{hi*3.6:.1f} km/h "
        f"(vmax×0.88 = {expected_surface_ms*3.6:.1f} km/h)"
    )


def test_holland_far_field_decay():
    """Wind at large radius should be substantially weaker than at RMW.
    
    Using 200 km (~9×RMW for Fani's 22 km RMW) — Holland profile decays
    sharply beyond 5×RMW; expect < 60% of RMW wind at 200 km.
    """
    from pipeline.step_02_wind_field import holland_wind_speed

    vmax_ms = 191.0 / 3.6
    v_rmw = holland_wind_speed(22.0, 22.0, vmax_ms, 934.0, 19.8)
    v_far = holland_wind_speed(200.0, 22.0, vmax_ms, 934.0, 19.8)  # ~9×RMW
    assert v_far < v_rmw * 0.60, (
        f"Far-field wind at 200 km: {v_far*3.6:.1f} km/h should be < 60% of RMW "
        f"wind {v_rmw*3.6:.1f} km/h (Holland profile decays sharply beyond ~5×RMW)"
    )


def test_holland_eye_decay():
    """Wind inside the eye (r << RMW) should be much weaker than at RMW."""
    from pipeline.step_02_wind_field import holland_wind_speed

    vmax_ms = 191.0 / 3.6
    v_rmw = holland_wind_speed(22.0, 22.0, vmax_ms, 934.0, 19.8)
    v_eye = holland_wind_speed(3.0, 22.0, vmax_ms, 934.0, 19.8)
    assert v_eye < v_rmw * 0.7, (
        f"Eye wind {v_eye*3.6:.1f} km/h should be < 70% of RMW wind {v_rmw*3.6:.1f} km/h"
    )


def test_wind_max_geojson_structure():
    """wind_max.geojson must exist with polygon cells and a plausible peak."""
    wind_file = PROCESSED_DIR / "wind_max.geojson"
    if not wind_file.exists():
        pytest.skip("wind_max.geojson not yet generated; run step_02_wind_field")

    with open(wind_file) as f:
        data = json.load(f)

    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) > 20, f"Should have multiple grid cells, got {len(features)}"

    max_v = max(
        f["properties"].get("wind_kmh", f["properties"].get("vmax_kmh", 0))
        for f in features
    )
    # With WMO 0.88 factor, in-AOI peak should be ≥ 155 km/h for Fani
    assert max_v >= 155.0, (
        f"Peak wind {max_v:.1f} km/h too low for Cyclone Fani with WMO factor. "
        "Check SURFACE_WIND_FACTOR (must be 0.88) and hours_filter."
    )
    # Should not implausibly exceed IBTrACS 1-min vmax (214.9 km/h)
    assert max_v <= 230.0, f"Peak wind {max_v:.1f} km/h implausibly high"


def test_wind_meta_consistency():
    """wind_meta.json must cite Harper et al. 2010 WMO/TD-1555 and show consistent Vmax provenance."""
    meta_file = PROCESSED_DIR / "wind_meta.json"
    if not meta_file.exists():
        pytest.skip("wind_meta.json not yet generated; run step_02_wind_field")

    with open(meta_file) as f:
        meta = json.load(f)

    # Factor and citation
    assert "wind_conversion_factor" in meta, "Missing wind_conversion_factor"
    assert meta["wind_conversion_factor"] == pytest.approx(0.93, abs=1e-6), (
        f"wind_meta factor {meta['wind_conversion_factor']} != 0.93 (Harper et al. 2010)"
    )
    assert "wind_conversion_citation" in meta, (
        "wind_meta.json must include wind_conversion_citation (Harper et al. 2010 WMO/TD-1555)"
    )
    assert "WMO/TD" in meta["wind_conversion_citation"] and "Harper" in meta["wind_conversion_citation"], (
        f"Citation must name Harper et al. and WMO/TD-1555, got: {meta['wind_conversion_citation'][:80]}"
    )

    # IBTrACS vmax provenance — raw_obs is canonical
    assert "ibtracs_vmax_kmh_1min_raw_obs" in meta, (
        "Missing ibtracs_vmax_kmh_1min_raw_obs (raw 3-hourly obs peak, canonical)"
    )
    assert "ibtracs_vmax_kmh_1min_splined" in meta, (
        "Missing ibtracs_vmax_kmh_1min_splined (spline interpolation peak, reference only)"
    )
    raw_obs = meta["ibtracs_vmax_kmh_1min_raw_obs"]
    splined = meta["ibtracs_vmax_kmh_1min_splined"]
    # Both should be in a physically plausible range for Fani
    assert 200.0 <= raw_obs <= 230.0, f"Raw obs peak {raw_obs} km/h out of range for Fani"
    # Splined should be within 10 km/h of raw (overshoot expected but bounded)
    assert abs(splined - raw_obs) <= 10.0, (
        f"Splined peak {splined} km/h differs from raw {raw_obs} km/h by more than 10 km/h"
    )

    # Plausibility ratio (grid peak / 10-min canonical)
    assert "grid_peak_vs_ibtracs_10min_ratio" in meta
    ratio = meta["grid_peak_vs_ibtracs_10min_ratio"]
    assert ratio >= 0.65, (
        f"Grid peak / IBTrACS 10-min ratio = {ratio:.3f} < 0.65. "
        "Model is severely under-estimating in-AOI wind speed."
    )

    # IBTrACS source must be consistent with track_meta
    assert "ibtracs_citation" in meta, "wind_meta must include ibtracs_citation for traceability"


def test_wind_district_ts(scenario):
    """wind_district_ts.json must have all districts; Puri peak ≥ 155 km/h."""
    ts_file = PROCESSED_DIR / "wind_district_ts.json"
    if not ts_file.exists():
        pytest.skip("wind_district_ts.json not yet generated")

    with open(ts_file) as f:
        ts_data = json.load(f)

    for dist in scenario["districts"]:
        assert dist in ts_data, f"District {dist} missing from wind time series"
        entries = ts_data[dist]
        assert len(entries) > 10, f"District {dist} should have multiple hourly steps"
        for entry in entries:
            assert "time_utc" in entry
            assert "wind_kmh" in entry
            assert entry["wind_kmh"] >= 0

    # Puri is the closest district to landfall — must show strong winds
    puri_peak = max(s["wind_kmh"] for s in ts_data.get("Puri", [{"wind_kmh": 0}]))
    assert puri_peak >= 155.0, (
        f"Puri peak wind {puri_peak:.1f} km/h too low. "
        "Expected ≥ 155 km/h for the storm's closest district."
    )
