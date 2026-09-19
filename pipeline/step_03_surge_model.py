"""
Step 03 — Storm Surge & Coastal Inundation Model
=================================================
Simulates coastal storm surge and inland flood propagation using:
  1. Inverse Barometer Effect: Δη_IB = 0.01 m/hPa * (P_env - P_c)
  2. Wind Setup: Δη_wind = C_w * (U_10^2 * Fetch) / (g * H_shelf)
  3. Astronomical Tide: INCOIS tidal prediction offset (1.2 m at landfall)
  4. Inland Bathtub Attenuation: Depth(d) = max(0, Surge_peak - Elev - α * d)
     where α is the inland attenuation coefficient (calibrated in Step 05).

Produces:
  - data/processed/surge_hourly.geojson      (hourly peak surge points along coastline)
  - data/processed/surge_inundation.geojson   (inland flood polygons with depth)
  - data/processed/surge_district_ts.json    (district-level surge time series)
  - data/processed/surge_meta.json           (simulation parameters & peak surge)

Usage:
    python pipeline/step_03_surge_model.py [--scenario fani_2019] [--force]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import yaml
from shapely.geometry import Polygon, MultiPolygon, Point, mapping

from pipeline.utils.geo import (
    feature_collection,
    point_feature,
    polygon_feature,
    haversine_km,
    bearing_deg,
    make_grid,
)
from pipeline.utils.logger import get_logger

log = get_logger(__name__)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
GRAVITY = 9.80665  # m/s²
RHO_WATER = 1025.0  # kg/m³ seawater density
RHO_AIR = 1.15     # kg/m³ air density
P_ENV_DEFAULT = 1010.0  # hPa far-field MSLP

# Representative coastal points along Odisha coast (Puri to Kendrapara / Mahanadi Delta)
# [lon, lat, district_name, coastal_normal_azimuth_deg]
COASTAL_POINTS = [
    [85.45, 19.68, "Puri", 135.0],        # Chilika mouth / Satapada
    [85.65, 19.75, "Puri", 140.0],        # Brahmagiri coast
    [85.83, 19.80, "Puri", 145.0],        # Puri Beach (near landfall)
    [86.05, 19.87, "Puri", 150.0],        # Konark / Chandrabhaga
    [86.27, 19.98, "Puri", 140.0],        # Astaranga coast
    [86.44, 20.16, "Jagatsinghpur", 130.0], # Ersama coastal stretch
    [86.67, 20.29, "Jagatsinghpur", 120.0], # Paradip Port
    [86.72, 20.48, "Kendrapara", 110.0],    # Mahakalpara / Hukitola
    [86.78, 20.65, "Kendrapara", 100.0],    # Rajanagar / Bhitarkanika mouth
]


def load_scenario(scenario_name: str) -> dict[str, Any]:
    cfg_path = PROJECT_ROOT / "config" / "scenarios" / f"{scenario_name}.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def compute_inverse_barometer(mslp_hpa: float, coeff: float = 0.01, p_env: float = P_ENV_DEFAULT) -> float:
    """
    Inverse barometer surge component:
    Δη_IB = coeff * (P_env - P_c)
    Typically ~1 cm per hPa pressure deficit.
    """
    dp = max(0.0, p_env - mslp_hpa)
    return coeff * dp


def compute_wind_setup(
    wind_kmh: float,
    wind_dir_deg: float,
    coast_normal_deg: float,
    shelf_depth_m: float = 15.0,
    fetch_km: float = 60.0,
    wind_setup_coeff: float = 3.0e-6,
) -> float:
    """
    Wind setup component:
    Δη_wind = coeff * U10^2 * Fetch / (g * Depth) * cos(theta)
    where theta is angle between wind direction and onshore coastal normal.
    coeff ~ (rho_air * Cd) / rho_water ~ 3.0e-6
    """
    u10_ms = (wind_kmh / 3.6)
    d_theta = math.radians(abs(wind_dir_deg - coast_normal_deg))
    cos_align = max(0.0, math.cos(d_theta))

    # Base setup formula
    fetch_m = fetch_km * 1000.0
    setup = (wind_setup_coeff * (u10_ms ** 2) * fetch_m) / (GRAVITY * shelf_depth_m) * cos_align
    return max(0.0, setup)


def compute_total_surge_at_coast(
    mslp_hpa: float,
    wind_kmh: float,
    wind_dir_deg: float,
    coast_normal_deg: float,
    cfg_surge: dict[str, Any],
) -> dict[str, float]:
    """Calculate total storm surge = IB + Wind Setup + Astronomical Tide."""
    ib_coeff = cfg_surge.get("inverse_barometer_coeff", 0.01)
    ws_coeff = cfg_surge.get("wind_setup_coeff", 0.0003)
    depth = cfg_surge.get("shelf_depth_m", 15.0)
    fetch = cfg_surge.get("fetch_km", 500.0)
    tide = cfg_surge.get("tide_height_m", 1.2)

    eta_ib = compute_inverse_barometer(mslp_hpa, coeff=ib_coeff)
    eta_wind = compute_wind_setup(wind_kmh, wind_dir_deg, coast_normal_deg, depth, fetch, ws_coeff)
    eta_total = eta_ib + eta_wind + tide

    return {
        "surge_total_m": round(eta_total, 2),
        "surge_ib_m": round(eta_ib, 2),
        "surge_wind_m": round(eta_wind, 2),
        "tide_m": round(tide, 2),
    }


def compute_inland_flood_depth(
    surge_peak_m: float,
    elevation_m: float,
    distance_to_coast_km: float,
    attenuation_per_km: float = 0.10,
    max_inland_km: float = 30.0,
) -> float:
    """
    Bathtub inundation with inland attenuation:
    Depth = max(0, Surge_peak - Elevation - α * distance)
    """
    if distance_to_coast_km > max_inland_km:
        return 0.0
    attenuated_surge = surge_peak_m - (attenuation_per_km * distance_to_coast_km)
    flood_depth = attenuated_surge - elevation_m
    return max(0.0, flood_depth)


def run(
    scenario: str = "fani_2019",
    attenuation_coeff: float | None = None,
    force: bool = False,
) -> bool:
    """Run storm surge simulation and inundation calculation."""
    surge_hourly_out = PROCESSED_DIR / "surge_hourly.geojson"
    surge_inundation_out = PROCESSED_DIR / "surge_inundation.geojson"
    surge_ts_out = PROCESSED_DIR / "surge_district_ts.json"
    surge_meta_out = PROCESSED_DIR / "surge_meta.json"

    if not force and surge_hourly_out.exists() and surge_inundation_out.exists() and not attenuation_coeff:
        log.info("Surge model outputs already exist; use --force to re-run.")
        return True

    config = load_scenario(scenario)
    cfg_surge = config.get("surge", {})
    alpha = attenuation_coeff if attenuation_coeff is not None else cfg_surge.get("inland_attenuation_per_km", 0.10)
    max_inland_km = cfg_surge.get("max_inland_km", 30.0)

    # Load hourly track
    track_path = PROCESSED_DIR / "track_hourly.geojson"
    if not track_path.exists():
        raise FileNotFoundError(f"Track file {track_path} not found. Run step_01_fetch_track.py first.")

    with open(track_path) as f:
        track_data = json.load(f)

    # Extract point features
    track_point_features = [
        f
        for f in track_data.get("features", [])
        if f.get("geometry", {}).get("type") == "Point"
    ]

    # Find landfall / peak intensity steps (T-18 to T+18)
    hourly_surge_features = []
    peak_surge_by_point = {idx: 0.0 for idx in range(len(COASTAL_POINTS))}

    for f in track_point_features:
        pt = f["properties"]
        t_landfall = pt.get("hours_to_landfall", 0.0)
        if abs(t_landfall) > 18:
            continue  # only simulate around landfall window

        mslp = pt.get("mslp_hpa", 950.0)
        vmax = pt.get("vmax_kmh", 150.0)
        time_utc = pt.get("time_utc", "")
        eye_lon, eye_lat = f["geometry"]["coordinates"]

        # For each coastal point, compute wind direction and surge
        for idx, (cp_lon, cp_lat, dist_name, c_norm) in enumerate(COASTAL_POINTS):
            dist_to_eye = haversine_km(cp_lat, cp_lon, eye_lat, eye_lon)
            # Tangential wind direction around storm eye in Northern Hemisphere (anticlockwise cyclonic)
            bearing_to_eye = bearing_deg(cp_lat, cp_lon, eye_lat, eye_lon)
            # Tangential wind is roughly perpendicular to radial vector (bearing + 90 deg)
            wind_dir = (bearing_to_eye + 90.0) % 360.0

            # Scale wind by distance from eye (Holland profile proxy)
            rmw = config.get("landfall", {}).get("rmw_km", 35.0)
            if dist_to_eye < rmw:
                local_wind = vmax * (dist_to_eye / max(rmw, 1.0))
            else:
                local_wind = vmax * ((rmw / dist_to_eye) ** 0.5)

            surge_res = compute_total_surge_at_coast(
                mslp_hpa=mslp,
                wind_kmh=local_wind,
                wind_dir_deg=wind_dir,
                coast_normal_deg=c_norm,
                cfg_surge=cfg_surge,
            )

            total_surge = surge_res["surge_total_m"]
            if total_surge > peak_surge_by_point[idx]:
                peak_surge_by_point[idx] = total_surge

            hourly_surge_features.append(
                point_feature(
                    lat=cp_lat,
                    lon=cp_lon,
                    properties={
                        "station_id": f"coast_{idx}",
                        "district": dist_name,
                        "time_utc": time_utc,
                        "hours_to_landfall": t_landfall,
                        **surge_res,
                    },
                )
            )

    # Save hourly surge points
    with open(surge_hourly_out, "w") as f:
        json.dump(feature_collection(hourly_surge_features), f, indent=2)
    log.info(f"Saved {len(hourly_surge_features)} hourly surge observations to {surge_hourly_out}")

    # Build 2D inland flood inundation polygons
    # Synthetic coastal elevation model: Odisha coastal plains are low-lying (0.5m - 6.0m elevation within 25km)
    log.info("Generating inland storm surge inundation polygons...")
    inundation_features = []

    # Grid over coastal corridor
    bbox = config.get("aoi_bbox", [84.9, 19.6, 86.5, 20.7])
    # Resolution ~ 1km grid for inundation polygons
    res_m = 1000
    lats, lons = make_grid(bbox, resolution_m=res_m)
    stride_lat = abs(lats[1, 0] - lats[0, 0]) / 2
    stride_lon = abs(lons[0, 1] - lons[0, 0]) / 2

    # Precalculate nearest coastal point and distance for each grid cell
    max_peak_surge = max(peak_surge_by_point.values()) if peak_surge_by_point else 3.5

    district_flood_summary = {d: {"peak_surge_m": 0.0, "max_depth_m": 0.0, "flooded_area_sqkm": 0.0} for d in config.get("districts", [])}

    for i in range(lats.shape[0]):
        for j in range(lats.shape[1]):
            c_lat = float(lats[i, j])
            c_lon = float(lons[i, j])

            # Find distance to nearest coastal station
            min_dist_km = float("inf")
            best_station_surge = 0.0
            best_dist_name = "Puri"

            for idx, (cp_lon, cp_lat, d_name, _) in enumerate(COASTAL_POINTS):
                d_km = haversine_km(c_lat, c_lon, cp_lat, cp_lon)
                if d_km < min_dist_km:
                    min_dist_km = d_km
                    best_station_surge = peak_surge_by_point.get(idx, 2.5)
                    best_dist_name = d_name

            if min_dist_km > max_inland_km:
                continue

            # Model elevation based on distance inland + realistic topography:
            # Low elevation along Mahanadi / Devi river delta and coastal estuaries (Puri/Jagatsinghpur/Kendrapara)
            # Coastal sand dunes: 2.0m, inland lowlands / polders: 0.8 - 2.5m, rising gently 0.15m per km
            base_elev = 0.8 + 0.12 * min_dist_km
            # Add micro-topographic delta depressions
            if best_dist_name in ("Jagatsinghpur", "Kendrapara"):
                base_elev -= 0.3  # Mahanadi delta estuarine wetlands are ultra-low
            elif best_dist_name == "Puri" and c_lon < 85.7:
                base_elev -= 0.4  # Chilika lagoon fringe

            base_elev = max(0.4, base_elev)

            depth = compute_inland_flood_depth(
                surge_peak_m=best_station_surge,
                elevation_m=base_elev,
                distance_to_coast_km=min_dist_km,
                attenuation_per_km=alpha,
                max_inland_km=max_inland_km,
            )

            if depth > 0.1:  # flooded cell (>10 cm water)
                cell_poly = [
                    [c_lon - stride_lon, c_lat - stride_lat],
                    [c_lon + stride_lon, c_lat - stride_lat],
                    [c_lon + stride_lon, c_lat + stride_lat],
                    [c_lon - stride_lon, c_lat + stride_lat],
                    [c_lon - stride_lon, c_lat - stride_lat],
                ]

                # Classify severity
                if depth >= 1.5:
                    sev = "Catastrophic"
                elif depth >= 0.6:
                    sev = "Severe"
                elif depth >= 0.3:
                    sev = "Moderate (Impassable)"
                else:
                    sev = "Minor"

                inundation_features.append(
                    polygon_feature(
                        coordinates=[cell_poly],
                        properties={
                            "depth_m": round(depth, 2),
                            "severity": sev,
                            "elevation_m": round(base_elev, 2),
                            "dist_to_coast_km": round(min_dist_km, 1),
                            "district": best_dist_name,
                        },
                    )
                )

                if best_dist_name in district_flood_summary:
                    district_flood_summary[best_dist_name]["flooded_area_sqkm"] += 1.0  # ~1 sqkm per cell
                    if depth > district_flood_summary[best_dist_name]["max_depth_m"]:
                        district_flood_summary[best_dist_name]["max_depth_m"] = round(depth, 2)
                    if best_station_surge > district_flood_summary[best_dist_name]["peak_surge_m"]:
                        district_flood_summary[best_dist_name]["peak_surge_m"] = round(best_station_surge, 2)

    # Save surge inundation GeoJSON
    with open(surge_inundation_out, "w") as f:
        json.dump(feature_collection(inundation_features), f)
    log.info(f"Saved {len(inundation_features)} flood inundation polygons to {surge_inundation_out}")

    # Save district summary
    with open(surge_ts_out, "w") as f:
        json.dump(district_flood_summary, f, indent=2)
    log.info(f"Saved district surge summary to {surge_ts_out}: {district_flood_summary}")

    # Save metadata
    meta = {
        "scenario": scenario,
        "max_peak_surge_m": round(max_peak_surge, 2),
        "inland_attenuation_coeff": round(alpha, 4),
        "astronomical_tide_m": cfg_surge.get("tide_height_m", 1.2),
        "max_inland_penetration_km": max_inland_km,
        "total_flooded_cells": len(inundation_features),
        "physics": "Inverse Barometer + Wind Setup + Tide + Attenuated Bathtub",
        "citation": "Pugh (1987) Tides, Surges and Mean Sea-Level; IMD Cyclone Fani Report",
    }
    with open(surge_meta_out, "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Saved surge metadata to {surge_meta_out}")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 03: Storm Surge & Coastal Inundation Model")
    parser.add_argument("--scenario", default="fani_2019", help="Scenario name")
    parser.add_argument("--attenuation", type=float, default=None, help="Custom attenuation coefficient")
    parser.add_argument("--force", action="store_true", help="Force regenerate")
    args = parser.parse_args()

    ok = run(scenario=args.scenario, attenuation_coeff=args.attenuation, force=args.force)
    sys.exit(0 if ok else 1)
