"""
Step 02 — Holland (1980) Parametric Wind Field
================================================
Computes the parametric wind field along the hourly track using the
Holland (1980) model with translation-speed asymmetry correction.

Produces:
  - data/processed/wind_max.geojson        — GeoJSON of grid cells with max sustained wind
  - data/processed/wind_district_ts.json   — Hourly wind time series at district centroids
  - data/processed/wind_meta.json          — Model run metadata

References:
  Holland, G.J. (1980). An analytic model of the wind and pressure profiles
  in hurricanes. *Mon. Wea. Rev.*, 108, 1212–1218.
  https://doi.org/10.1175/1520-0493(1980)108<1212:AAMOTWAPPH>2.0.CO;2

Usage:
    python -m pipeline.step_02_wind_field [--scenario fani_2019] [--force]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import yaml
from shapely.geometry import mapping, Point, Polygon

from pipeline.utils.geo import make_grid, feature_collection, bearing_deg
from pipeline.utils.logger import get_logger

log = get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Physical constants
RHO_AIR = 1.15           # kg/m³ — air density at sea level (standard)
PENV_HPA = 1010.0        # hPa — environmental (far-field) pressure
CORIOL_LAT = 20.0        # degrees — reference latitude for Coriolis (Odisha coast)
OMEGA = 7.2921e-5        # rad/s — Earth rotation rate
FCOR = 2 * OMEGA * math.sin(math.radians(CORIOL_LAT))  # Coriolis parameter

# 1-min → 10-min sustained wind conversion factor
# Reference: Harper, B.A., Kepert, J.D., and Ginger, J.D. (2010). Guidelines for
#   Converting Between Various Wind Averaging Periods in Tropical Cyclone Conditions.
#   WMO/TD-No.1555. World Meteorological Organization, Geneva.
#   https://library.wmo.int/doc_num.php?explnum_id=290
#
# Harper et al. (2010) recommend 0.93 for open-ocean exposure (marine boundary layer),
# which is the correct baseline for IBTrACS JTWC observations (recorded over ocean).
# The legacy value of 0.88 (pre-2010 WMO practice) was found to under-estimate the
# 10-min equivalent by approximately 5% and is superseded by the 2010 guidance.
# We use 0.93 consistently with IBTrACS JTWC 1-min reporting convention.
SURFACE_WIND_FACTOR = 0.93  # 1-min → 10-min (Harper et al. 2010, WMO/TD-1555, open-ocean)
ASYMMETRY_FRACTION = 0.20   # Fraction of translation speed added to right-of-track (NH)

# Saffir-Simpson equivalent category thresholds (km/h, 10-min)
WIND_CATEGORIES = [
    (166, 5, "Category 5"),
    (130, 4, "Category 4"),
    (111, 3, "Category 3"),
    (89, 2, "Category 2"),
    (63, 1, "Category 1"),
    (0, 0, "Tropical Storm / Depression"),
]


class TrackPoint(NamedTuple):
    """A single hourly track observation."""
    lat: float
    lon: float
    vmax_kt: float
    vmax_kmh: float
    mslp_hpa: float
    rmw_km: float
    trans_speed_kmh: float
    trans_direction_deg: float
    hours_to_landfall: float
    time_utc: str


def load_hourly_track(processed_dir: Path) -> list[TrackPoint]:
    """
    Load the hourly track GeoJSON produced by step 01.

    Parameters
    ----------
    processed_dir : Path
        Directory containing track_hourly.geojson.

    Returns
    -------
    list[TrackPoint]
    """
    track_path = processed_dir / "track_hourly.geojson"
    if not track_path.exists():
        raise FileNotFoundError(
            f"Hourly track not found at {track_path}. Run step 01 first."
        )
    with open(track_path) as f:
        gj = json.load(f)

    points = []
    for feat in gj["features"]:
        p = feat["properties"]
        lon, lat = feat["geometry"]["coordinates"]
        points.append(TrackPoint(
            lat=lat,
            lon=lon,
            vmax_kt=p.get("vmax_kt", 0),
            vmax_kmh=p.get("vmax_kmh", 0),
            mslp_hpa=p.get("mslp_hpa", 1010.0),
            rmw_km=p.get("rmw_km", 35.0),
            trans_speed_kmh=p.get("trans_speed_kmh", 0),
            trans_direction_deg=p.get("trans_direction_deg", 0),
            hours_to_landfall=p.get("hours_to_landfall", 0),
            time_utc=p.get("time_utc", ""),
        ))
    return points


def holland_b(mslp_hpa: float, vmax_kt: float) -> float:
    """
    Estimate Holland B shape parameter.

    Uses the formula from Holland (1980):
        B = ρ_air × e × Vmax² / ΔP
    where ΔP = (Penv - Pc) in Pa.

    Parameters
    ----------
    mslp_hpa : float
        Central pressure in hPa.
    vmax_kt : float
        Maximum sustained wind speed in knots (10-min).

    Returns
    -------
    float
        Holland B parameter, clipped to [1.0, 2.5].
    """
    dp_pa = max((PENV_HPA - mslp_hpa) * 100, 100)  # Pa; avoid division by zero
    vmax_ms = vmax_kt * 0.5144  # kt → m/s
    b = RHO_AIR * math.e * vmax_ms**2 / dp_pa
    return float(np.clip(b, 1.0, 2.5))


def holland_wind_speed(
    r_km: float,
    rmw_km: float,
    vmax_ms: float,
    mslp_hpa: float,
    lat: float,
) -> float:
    """
    Compute Holland (1980) gradient wind speed at radius r from storm centre.

    Parameters
    ----------
    r_km : float
        Distance from storm centre in kilometres.
    rmw_km : float
        Radius of maximum winds in kilometres.
    vmax_ms : float
        Maximum sustained wind speed in m/s (10-min).
    mslp_hpa : float
        Central pressure in hPa.
    lat : float
        Latitude (for Coriolis).

    Returns
    -------
    float
        Surface wind speed in m/s (10-min, at 10 m above ground).
    """
    if r_km < 1e-3:
        return 0.0

    r_m = r_km * 1000
    rmw_m = rmw_km * 1000
    dp_pa = max((PENV_HPA - mslp_hpa) * 100, 1)
    b = holland_b(mslp_hpa, vmax_ms / 0.5144)

    # Coriolis parameter at this latitude
    fcor = 2 * OMEGA * math.sin(math.radians(abs(lat)))

    # Holland (1980) Eq. 4
    term1 = (b / (RHO_AIR)) * dp_pa * (rmw_m / r_m)**b * math.exp(-(rmw_m / r_m)**b)
    term2 = (r_m * fcor / 2)**2
    v_gradient = math.sqrt(max(term1 + term2, 0)) - r_m * fcor / 2

    # Apply surface reduction factor
    v_surface = v_gradient * SURFACE_WIND_FACTOR
    return max(v_surface, 0.0)


def apply_translation_asymmetry(
    wind_ms: float,
    r_km: float,
    rmw_km: float,
    bearing_to_point: float,
    trans_speed_kmh: float,
    trans_direction: float,
) -> float:
    """
    Apply translation-speed asymmetry to the symmetric Holland wind field.

    The storm's forward motion adds wind on the right-of-track side
    (in Northern Hemisphere) and subtracts on the left.

    Parameters
    ----------
    wind_ms : float
        Symmetric Holland wind speed (m/s).
    r_km : float
        Distance from storm centre (km).
    rmw_km : float
        Radius of maximum winds (km).
    bearing_to_point : float
        Bearing from storm centre to grid point (degrees, 0=N, 90=E).
    trans_speed_kmh : float
        Storm translation speed (km/h).
    trans_direction : float
        Storm motion direction (degrees, toward which the storm is moving).

    Returns
    -------
    float
        Asymmetry-corrected wind speed (m/s).
    """
    trans_ms = trans_speed_kmh / 3.6  # km/h → m/s

    # Angle between storm motion and bearing to point
    delta_angle = (bearing_to_point - trans_direction) % 360
    # Right-of-track: delta_angle ~ 90° → cos(delta_angle - 90°) = sin(delta_angle)
    # Asymmetry factor = sin of angle between point and right-of-track
    asymmetry_factor = math.sin(math.radians(delta_angle))

    # Fraction falls off with distance from RMW
    r_factor = max(1.0 - (r_km - rmw_km) / (5 * rmw_km), 0.0) if r_km > rmw_km else 1.0

    correction = ASYMMETRY_FRACTION * trans_ms * asymmetry_factor * r_factor
    return max(wind_ms + correction, 0.0)


def wind_category(vmax_kmh: float) -> str:
    """Return wind category label for a given max wind speed (km/h)."""
    for threshold, cat, label in WIND_CATEGORIES:
        if vmax_kmh >= threshold:
            return label
    return "Calm"


def compute_wind_grid(
    track_points: list[TrackPoint],
    bbox: list[float],
    resolution_m: float,
    hours_filter: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute maximum wind speed over the event period at each grid cell.

    Parameters
    ----------
    track_points : list[TrackPoint]
        Hourly track observations.
    bbox : list[float]
        [lon_min, lat_min, lon_max, lat_max].
    resolution_m : float
        Grid resolution in metres.
    hours_filter : tuple[float, float]
        (start_hours_to_landfall, end_hours_to_landfall) — filter track points.

    Returns
    -------
    lats, lons, max_wind_kmh : np.ndarray
        2-D arrays of cell-centre latitudes, longitudes, and max wind speed (km/h).
    """
    lats, lons = make_grid(bbox, resolution_m)
    max_wind = np.zeros_like(lats, dtype=float)

    # Filter track points to event window
    pts = [
        p for p in track_points
        if hours_filter[0] <= p.hours_to_landfall <= hours_filter[1]
    ]
    log.info(f"Computing wind grid: {lats.shape} grid, {len(pts)} track points")

    for i, pt in enumerate(pts):
        if i % 12 == 0:
            log.info(f"  Progress: {i}/{len(pts)} track points (h={pt.hours_to_landfall:.0f})")

        if pt.vmax_kmh < 20:  # Skip very weak / post-landfall decay
            continue

        vmax_ms = pt.vmax_kmh / 3.6

        # Vectorised distance calculation (haversine approximation)
        dlat = np.radians(lats - pt.lat)
        dlon = np.radians(lons - pt.lon)
        a = (np.sin(dlat / 2)**2 +
             np.cos(np.radians(pt.lat)) * np.cos(np.radians(lats)) * np.sin(dlon / 2)**2)
        r_km = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

        # Bearing from storm centre to each grid point
        x = np.sin(dlon) * np.cos(np.radians(lats))
        y = (np.cos(np.radians(pt.lat)) * np.sin(np.radians(lats)) -
             np.sin(np.radians(pt.lat)) * np.cos(np.radians(lats)) * np.cos(dlon))
        bearing_to_grid = (np.degrees(np.arctan2(x, y)) + 360) % 360

        # Holland wind at each cell (vectorised)
        b = holland_b(pt.mslp_hpa, pt.vmax_kt)
        rmw_m = pt.rmw_km * 1000
        r_m = r_km * 1000
        dp_pa = max((PENV_HPA - pt.mslp_hpa) * 100, 1)
        fcor_loc = 2 * OMEGA * np.sin(np.radians(np.abs(lats)))

        ratio = np.where(r_m > 0, rmw_m / r_m, 0)
        term1 = (b / RHO_AIR) * dp_pa * ratio**b * np.exp(-ratio**b)
        term2 = (r_m * fcor_loc / 2)**2
        v_gradient = np.sqrt(np.maximum(term1 + term2, 0)) - r_m * fcor_loc / 2
        v_surface = np.maximum(v_gradient, 0) * SURFACE_WIND_FACTOR

        # Translation asymmetry (vectorised)
        trans_ms = pt.trans_speed_kmh / 3.6
        delta_angle = (bearing_to_grid - pt.trans_direction_deg) % 360
        asym_factor = np.sin(np.radians(delta_angle))
        r_factor = np.where(
            r_km > pt.rmw_km,
            np.maximum(1.0 - (r_km - pt.rmw_km) / (5 * pt.rmw_km), 0.0),
            1.0,
        )
        v_surface += ASYMMETRY_FRACTION * trans_ms * asym_factor * r_factor
        v_surface = np.maximum(v_surface, 0)

        max_wind = np.maximum(max_wind, v_surface)

    return lats, lons, max_wind * 3.6  # m/s → km/h


def compute_district_timeseries(
    track_points: list[TrackPoint],
    district_centroids: dict[str, tuple[float, float]],
) -> dict[str, list[dict]]:
    """
    Compute hourly wind speed at each district centroid.

    Parameters
    ----------
    track_points : list[TrackPoint]
        Hourly track observations.
    district_centroids : dict[str, tuple[float, float]]
        {district_name: (lat, lon)} mapping.

    Returns
    -------
    dict[str, list[dict]]
        {district_name: [{time_utc, hours_to_landfall, wind_kmh}, ...]}
    """
    results = {d: [] for d in district_centroids}

    for pt in track_points:
        for district, (dlat, dlon) in district_centroids.items():
            dlat_r = math.radians(dlat - pt.lat)
            dlon_r = math.radians(dlon - pt.lon)
            a = (math.sin(dlat_r / 2)**2 +
                 math.cos(math.radians(pt.lat)) * math.cos(math.radians(dlat)) *
                 math.sin(dlon_r / 2)**2)
            r_km = 2 * 6371.0 * math.asin(math.sqrt(max(a, 0)))

            bearing = (math.degrees(math.atan2(
                math.sin(math.radians(dlon - pt.lon)) * math.cos(math.radians(dlat)),
                math.cos(math.radians(pt.lat)) * math.sin(math.radians(dlat)) -
                math.sin(math.radians(pt.lat)) * math.cos(math.radians(dlat)) * math.cos(math.radians(dlon - pt.lon))
            )) + 360) % 360

            w_ms = holland_wind_speed(r_km, pt.rmw_km, pt.vmax_kmh / 3.6, pt.mslp_hpa, dlat)
            w_ms = apply_translation_asymmetry(
                w_ms, r_km, pt.rmw_km, bearing, pt.trans_speed_kmh, pt.trans_direction_deg
            )

            results[district].append({
                "time_utc": pt.time_utc,
                "hours_to_landfall": round(pt.hours_to_landfall, 1),
                "wind_kmh": round(w_ms * 3.6, 1),
                "wind_category": wind_category(w_ms * 3.6),
                "distance_km": round(r_km, 1),
            })

    return results


def run(scenario: str = "fani_2019", force: bool = False) -> bool:
    """Run the wind field computation step."""
    config_path = PROJECT_ROOT / "config" / "scenarios" / f"{scenario}.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    wind_max_out = PROCESSED_DIR / "wind_max.geojson"
    wind_ts_out = PROCESSED_DIR / "wind_district_ts.json"
    wind_meta_out = PROCESSED_DIR / "wind_meta.json"

    if wind_max_out.exists() and wind_ts_out.exists() and not force:
        log.info("Wind field outputs exist; use --force to re-run")
        return True

    # Load track
    track_points = load_hourly_track(PROCESSED_DIR)
    log.info(f"Loaded {len(track_points)} hourly track points")

    # IBTrACS peak vmax — two values with explicit provenance:
    #   raw_obs:  maximum from 3-hourly IBTrACS observations (track_meta.json)
    #             This is the canonical, authoritative JTWC 1-min value.
    #   splined:  maximum from cubic-spline hourly interpolation (track_hourly.geojson)
    #             May differ slightly from raw_obs due to spline overshoot between
    #             discrete observations; used only as a cross-check.
    # All ratio/threshold computations use raw_obs as the canonical reference.
    track_meta_path = PROCESSED_DIR / "track_meta.json"
    if not track_meta_path.exists():
        raise FileNotFoundError(
            f"track_meta.json not found at {track_meta_path}. Run step_01 first."
        )
    with open(track_meta_path) as _f:
        track_meta = json.load(_f)
    ibtracs_vmax_raw_kmh = float(track_meta["peak_vmax_kmh"])  # raw 3-hourly obs
    ibtracs_vmax_splined_kmh = max(pt.vmax_kmh for pt in track_points)  # spline interpolation
    ibtracs_vmax_10min = ibtracs_vmax_raw_kmh * SURFACE_WIND_FACTOR  # canonical 10-min
    log.info(
        f"IBTrACS raw-obs peak: {ibtracs_vmax_raw_kmh:.1f} km/h (1-min, JTWC, canonical)"
    )
    log.info(
        f"IBTrACS splined peak: {ibtracs_vmax_splined_kmh:.1f} km/h "
        f"(cubic-spline artifact, for reference only)"
    )
    log.info(
        f"WMO 10-min equivalent (raw × {SURFACE_WIND_FACTOR}): {ibtracs_vmax_10min:.1f} km/h"
    )

    bbox = config["aoi_bbox"]
    resolution_m = config.get("grid_resolution_m", 500)
    start_h = config["timeline"]["start_hours"]
    end_h = config["timeline"]["end_hours"]

    # Compute grid max wind
    lats, lons, max_wind_kmh = compute_wind_grid(
        track_points, bbox, resolution_m, (start_h, end_h)
    )

    # --- Plausibility check ------------------------------------------------
    # The AOI (lat 19.6–20.7) lies north of the storm's peak intensity location
    # (lat ~18.5). The in-AOI track reaches ~185 km/h (1-min), giving a 10-min
    # equivalent of ~172 km/h. The grid peak should be ≥ 65% of the canonical
    # IBTrACS 10-min vmax (computed from raw-obs peak × WMO factor).
    grid_peak = float(max_wind_kmh.max())
    min_expected = ibtracs_vmax_10min * 0.65  # ≥ 65% of canonical 10-min peak
    if grid_peak < min_expected:
        raise RuntimeError(
            f"FAIL: Grid peak {grid_peak:.1f} km/h < {min_expected:.1f} km/h "
            f"(65% of IBTrACS canonical 10-min {ibtracs_vmax_10min:.1f} km/h). "
            "Check SURFACE_WIND_FACTOR, hours_filter, or track data."
        )
    log.info(f"[PASS] Grid peak {grid_peak:.1f} km/h >= {min_expected:.1f} km/h threshold")
    # -----------------------------------------------------------------------

    # Save as GeoJSON (polygon cells coloured by wind speed)
    log.info("Building wind max GeoJSON...")
    features = []
    stride = 2
    raw_dlat = abs(lats[1, 0] - lats[0, 0]) if lats.shape[0] > 1 else 0.005
    raw_dlon = abs(lons[0, 1] - lons[0, 0]) if lons.shape[1] > 1 else 0.005
    cell_dlat = raw_dlat * stride / 2
    cell_dlon = raw_dlon * stride / 2

    for i in range(0, lats.shape[0], stride):
        for j in range(0, lats.shape[1], stride):
            w = float(np.max(max_wind_kmh[i : i + stride, j : j + stride]))
            if w < 20:  # skip calm cells
                continue
            lat_c, lon_c = float(lats[i, j]), float(lons[i, j])
            box = [
                [lon_c - cell_dlon, lat_c - cell_dlat],
                [lon_c + cell_dlon, lat_c - cell_dlat],
                [lon_c + cell_dlon, lat_c + cell_dlat],
                [lon_c - cell_dlon, lat_c + cell_dlat],
                [lon_c - cell_dlon, lat_c - cell_dlat],
            ]
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [box]},
                "properties": {
                    "wind_kmh": round(w, 1),
                    "vmax_kmh": round(w, 1),
                    "wind_category": wind_category(w),
                },
            })

    gj = feature_collection(features)
    with open(wind_max_out, "w") as f:
        json.dump(gj, f)
    log.info(f"Saved wind max grid: {wind_max_out} ({len(features)} non-calm cells)")

    # Compute district time series
    # District centroids (lat, lon) — approximate administrative centroids for Odisha
    # districts in the AOI. These are used for point wind estimates; full spatial
    # district boundaries are derived from OSM in step_06_osm_infra.py.
    district_centroids = {
        "Puri": (19.81, 85.83),
        "Khordha": (20.18, 85.62),
        "Jagatsinghpur": (20.27, 86.17),
        "Kendrapara": (20.50, 86.42),
        "Cuttack": (20.46, 85.88),
    }
    log.info("Computing district wind time series...")
    ts = compute_district_timeseries(track_points, district_centroids)

    with open(wind_ts_out, "w") as f:
        json.dump(ts, f, indent=2)
    log.info(f"Saved district wind time series: {wind_ts_out}")

    # District summary
    district_peaks: dict[str, float] = {}
    for district, series in ts.items():
        max_w = max((s["wind_kmh"] for s in series), default=0.0)
        district_peaks[district] = round(max_w, 1)
        log.info(f"  {district}: peak wind {max_w:.1f} km/h")

    # --- Write metadata JSON ------------------------------------------------
    meta = {
        "model": "Holland (1980) parametric wind field",
        "wind_conversion_factor": SURFACE_WIND_FACTOR,
        "wind_conversion_factor_value": SURFACE_WIND_FACTOR,
        "wind_conversion_citation": (
            "Harper, B.A., Kepert, J.D., and Ginger, J.D. (2010). Guidelines for "
            "Converting Between Various Wind Averaging Periods in Tropical Cyclone "
            "Conditions. WMO/TD-No.1555. World Meteorological Organization, Geneva. "
            "https://library.wmo.int/doc_num.php?explnum_id=290"
        ),
        "wind_conversion_rationale": (
            "Harper et al. (2010) recommend 0.93 for open-ocean exposure (marine "
            "boundary layer), consistent with IBTrACS JTWC observations recorded "
            "over ocean. The legacy value of 0.88 (pre-2010 WMO practice) was "
            "found to under-estimate the 10-min equivalent by approximately 5%."
        ),
        "asymmetry_fraction": ASYMMETRY_FRACTION,
        "asymmetry_note": "Translation-speed asymmetry, right-of-track positive (NH)",
        "ibtracs_vmax_kmh_1min_raw_obs": round(ibtracs_vmax_raw_kmh, 1),
        "ibtracs_vmax_kmh_1min_raw_obs_note": (
            "Maximum from 3-hourly IBTrACS observations (track_meta.json). "
            "This is the canonical JTWC 1-min value; used as reference for all ratios."
        ),
        "ibtracs_vmax_kmh_1min_splined": round(ibtracs_vmax_splined_kmh, 1),
        "ibtracs_vmax_kmh_1min_splined_note": (
            "Maximum from cubic-spline hourly interpolation (track_hourly.geojson). "
            "May differ from raw_obs due to spline overshoot between discrete "
            "3-hourly observations; for reference only, not used in ratios."
        ),
        "ibtracs_vmax_kmh_10min_wmo": round(ibtracs_vmax_10min, 1),
        "ibtracs_vmax_kmh_10min_wmo_note": (
            f"raw_obs × {SURFACE_WIND_FACTOR} (Harper et al. 2010 WMO/TD-1555)"
        ),
        "grid_peak_kmh": round(grid_peak, 1),
        "grid_peak_vs_ibtracs_10min_ratio": round(grid_peak / ibtracs_vmax_10min, 3),
        "grid_peak_note": (
            "AOI (lat 19.6–20.7) is north of the storm's absolute intensity peak "
            "(lat ~18.5, raw vmax 213 km/h). The in-AOI track peaks at ~185 km/h "
            "(1-min); grid peak reflects that in-AOI intensity."
        ),
        "district_peaks_kmh": district_peaks,
        "track_points_total": len(track_points),
        "track_points_in_window": sum(
            1 for p in track_points if start_h <= p.hours_to_landfall <= end_h
        ),
        "window_hours": [start_h, end_h],
        "scenario": scenario,
        "ibtracs_source": track_meta.get("data_source", "NOAA IBTrACS v04r00"),
        "ibtracs_citation": track_meta.get(
            "citation",
            "Knapp et al. (2010) BAMS https://doi.org/10.1175/2009BAMS2755.1"
        ),
    }
    with open(wind_meta_out, "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Saved wind metadata: {wind_meta_out}")
    # -----------------------------------------------------------------------

    return True


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Step 02: Holland Wind Field")
    parser.add_argument("--scenario", default="fani_2019")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    import sys
    sys.exit(0 if run(scenario=args.scenario, force=args.force) else 1)
