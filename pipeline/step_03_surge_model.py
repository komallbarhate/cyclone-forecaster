"""
Step 03 — Storm Surge & Coastal Inundation Model
=================================================
Simulates coastal storm surge and inland flood propagation on the real Copernicus GLO-30 DEM:
  1. Inverse Barometer Effect: Δη_IB = 0.01 m/hPa * (P_env - P_c)
  2. Wind Setup: Δη_wind = C_w * (U_10^2 * Fetch) / (g * H_shelf) * max(0, cos(θ_wind - θ_onshore))
  3. Astronomical Tide: Documented high tide assumption (1.2 m at landfall, semi-diurnal cycle)
  4. Connectivity-Constrained Bathtub Flood Model with Inland Attenuation:
     Floodwater propagates only from contiguous open ocean / coastal boundary seeds
     over real Copernicus GLO-30 DEM topography using 8-connectivity:
     Depth(d) = max(0, Surge_peak - Elev - α * d)
     where α is the inland attenuation coefficient (0.10 m/km).

Produces:
  - data/processed/surge_hourly.geojson      (hourly coastal surge points T-24h..T+24h)
  - data/processed/surge_inundation.geojson   (inland flood polygons with depth)
  - data/processed/surge_district_ts.json    (district-level surge time series & totals)
  - data/processed/surge_meta.json           (simulation parameters & peak metrics)
  - data/processed/surge_inundation.png      (high-resolution visualization map)
  - docs/surge_inundation.png                (documentation copy)

Usage:
    python -m pipeline.step_03_surge_model [--scenario fani_2019] [--force]
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
from scipy.ndimage import binary_dilation, distance_transform_edt, label
import yaml

from pipeline.utils.geo import (
    feature_collection,
    point_feature,
    polygon_feature,
    haversine_km,
    bearing_deg,
)
from pipeline.utils.logger import get_logger

log = get_logger(__name__)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DOCS_DIR = PROJECT_ROOT / "docs"

GRAVITY = 9.80665  # m/s²
RHO_WATER = 1025.0  # kg/m³ seawater density
RHO_AIR = 1.15     # kg/m³ air density
P_ENV_DEFAULT = 1010.0  # hPa far-field MSLP

# Representative coastal observation stations along Odisha coast
# [lon, lat, district, seaward_normal_azimuth_deg, station_name]
COASTAL_POINTS = [
    [85.45, 19.68, "Puri", 135.0, "Satapada / Chilika Mouth"],
    [85.65, 19.75, "Puri", 140.0, "Brahmagiri Coast"],
    [85.83, 19.80, "Puri", 145.0, "Puri Beach (Landfall Zone)"],
    [86.05, 19.87, "Puri", 150.0, "Konark / Chandrabhaga"],
    [86.27, 19.98, "Puri", 140.0, "Astaranga / Devi Estuary"],
    [86.44, 20.16, "Jagatsinghpur", 130.0, "Ersama Coastal Belt"],
    [86.67, 20.29, "Jagatsinghpur", 120.0, "Paradip Port"],
    [86.72, 20.48, "Kendrapara", 110.0, "Mahakalpara / Hukitola"],
    [86.78, 20.65, "Kendrapara", 100.0, "Rajanagar / Bhitarkanika"],
]

DISTRICT_CENTROIDS = {
    "Puri": (19.81, 85.83),
    "Khordha": (20.18, 85.62),
    "Jagatsinghpur": (20.27, 86.17),
    "Kendrapara": (20.50, 86.42),
    "Cuttack": (20.46, 85.88),
}


def load_scenario(scenario_name: str) -> dict[str, Any]:
    cfg_path = PROJECT_ROOT / "config" / "scenarios" / f"{scenario_name}.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def compute_inverse_barometer(
    mslp_hpa: float,
    coeff: float = 0.01,
    p_env: float = P_ENV_DEFAULT,
) -> float:
    """
    Inverse barometer surge component:
    Δη_IB = coeff * (P_env - P_c)
    Typically ~1 cm sea level rise per 1 hPa pressure deficit.
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
    Wind setup component over shallow shelf:
    Δη_wind = (coeff * U10^2 * Fetch) / (g * Depth) * max(0, cos(theta))
    where theta is the angle between the wind direction (coming from) and the seaward normal.
    """
    u10_ms = wind_kmh / 3.6
    d_theta = math.radians(abs(wind_dir_deg - coast_normal_deg))
    cos_align = max(0.0, math.cos(d_theta))

    fetch_m = fetch_km * 1000.0
    setup = (wind_setup_coeff * (u10_ms ** 2) * fetch_m) / (GRAVITY * shelf_depth_m) * cos_align
    return max(0.0, setup)


def compute_total_surge_at_coast(
    mslp_hpa: float,
    wind_kmh: float,
    wind_dir_deg: float,
    coast_normal_deg: float,
    t_relative_hours: float,
    cfg_surge: dict[str, Any],
) -> dict[str, float]:
    """Calculate total storm surge = IB + Wind Setup + Astronomical Tide."""
    ib_coeff = cfg_surge.get("inverse_barometer_coeff", 0.01)
    ws_coeff = cfg_surge.get("wind_setup_coeff", 3.0e-6)
    depth = cfg_surge.get("shelf_depth_m", 15.0)
    fetch = cfg_surge.get("fetch_km", 60.0)
    peak_tide = cfg_surge.get("tide_height_m", 1.2)

    # Semi-diurnal astronomical tide cycle (~12.42h period) peaking near landfall (t=0)
    tide_val = (peak_tide / 2.0) + (peak_tide / 2.0) * math.cos(2 * math.pi * t_relative_hours / 12.42)

    eta_ib = compute_inverse_barometer(mslp_hpa, coeff=ib_coeff)
    eta_wind = compute_wind_setup(wind_kmh, wind_dir_deg, coast_normal_deg, depth, fetch, ws_coeff)
    eta_total = eta_ib + eta_wind + tide_val

    return {
        "surge_total_m": round(eta_total, 2),
        "surge_ib_m": round(eta_ib, 2),
        "surge_wind_m": round(eta_wind, 2),
        "tide_m": round(tide_val, 2),
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
    """Run storm surge simulation on real Copernicus DEM with 8-connectivity constraints."""
    surge_hourly_out = PROCESSED_DIR / "surge_hourly.geojson"
    surge_inundation_out = PROCESSED_DIR / "surge_inundation.geojson"
    surge_ts_out = PROCESSED_DIR / "surge_district_ts.json"
    surge_meta_out = PROCESSED_DIR / "surge_meta.json"
    surge_png_out = PROCESSED_DIR / "surge_inundation.png"
    docs_png_out = DOCS_DIR / "surge_inundation.png"

    if (
        not force
        and surge_hourly_out.exists()
        and surge_inundation_out.exists()
        and surge_ts_out.exists()
        and surge_meta_out.exists()
        and surge_png_out.exists()
        and not attenuation_coeff
    ):
        log.info("Surge model outputs already exist; use --force to re-run.")
        return True

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    config = load_scenario(scenario)
    cfg_surge = config.get("surge", {})
    alpha = attenuation_coeff if attenuation_coeff is not None else cfg_surge.get("inland_attenuation_per_km", 0.10)
    max_inland_km = cfg_surge.get("max_inland_km", 30.0)
    bbox = config.get("aoi_bbox", [84.9, 19.6, 86.5, 20.7])

    dem_path = RAW_DIR / "copernicus_glo30_dem.tif"
    if not dem_path.exists():
        raise FileNotFoundError(f"Real Copernicus GLO-30 DEM not found at {dem_path}. Run open_data.py first.")

    track_path = PROCESSED_DIR / "track_hourly.geojson"
    if not track_path.exists():
        raise FileNotFoundError(f"Hourly track file not found at {track_path}. Run step_01_fetch_track.py first.")

    with open(track_path) as f:
        track_data = json.load(f)

    track_points = [
        f for f in track_data.get("features", [])
        if f.get("geometry", {}).get("type") == "Point"
    ]
    if not track_points:
        raise RuntimeError("No hourly track points found in track_hourly.geojson")

    log.info(f"Loaded {len(track_points)} track points. Simulating hourly surge along Odisha coast...")

    # Hourly simulation across timeline T-24h to T+24h
    hourly_features = []
    peak_surge_by_point = {idx: 0.0 for idx in range(len(COASTAL_POINTS))}
    hourly_station_timeseries: dict[str, list[dict[str, Any]]] = {
        cp[4]: [] for cp in COASTAL_POINTS
    }

    # Filter track points within T-24 to T+24
    sim_points = [
        p for p in track_points
        if -24.0 <= p["properties"].get("hours_to_landfall", -999) <= 24.0
    ]

    for pt_feat in sim_points:
        p = pt_feat["properties"]
        t_h = p.get("hours_to_landfall", 0.0)
        mslp = p.get("mslp_hpa", 950.0)
        vmax = p.get("vmax_kmh", 150.0)
        time_utc = p.get("time_utc", "")
        eye_lon, eye_lat = pt_feat["geometry"]["coordinates"]

        for idx, (cp_lon, cp_lat, dist_name, c_norm, cp_name) in enumerate(COASTAL_POINTS):
            dist_to_eye = haversine_km(cp_lat, cp_lon, eye_lat, eye_lon)
            # Bearing from storm center to coastal point
            brg_eye_to_pt = bearing_deg(eye_lat, eye_lon, cp_lat, cp_lon)
            # Cyclonic flow direction (counter-clockwise in Northern Hemisphere):
            # The flow vector points towards (bearing - 90°)
            wind_vec_dir = (brg_eye_to_pt - 90.0) % 360.0

            rmw = config.get("landfall", {}).get("rmw_km", 35.0)
            if dist_to_eye < rmw:
                local_wind = vmax * (dist_to_eye / max(rmw, 1.0))
            else:
                local_wind = vmax * ((rmw / dist_to_eye) ** 0.5)

            surge_res = compute_total_surge_at_coast(
                mslp_hpa=mslp,
                wind_kmh=local_wind,
                wind_dir_deg=wind_vec_dir,
                coast_normal_deg=c_norm,
                t_relative_hours=t_h,
                cfg_surge=cfg_surge,
            )

            tot_s = surge_res["surge_total_m"]
            if tot_s > peak_surge_by_point[idx]:
                peak_surge_by_point[idx] = tot_s

            pt_meta = {
                "station_id": f"coast_{idx}",
                "station_name": cp_name,
                "district": dist_name,
                "time_utc": time_utc,
                "hours_to_landfall": round(t_h, 1),
                "local_wind_kmh": round(local_wind, 1),
                **surge_res,
            }

            hourly_station_timeseries[cp_name].append(pt_meta)
            hourly_features.append(
                point_feature(
                    lat=cp_lat,
                    lon=cp_lon,
                    properties=pt_meta,
                )
            )

    # Save hourly surge points GeoJSON
    with open(surge_hourly_out, "w") as f:
        json.dump(feature_collection(hourly_features), f, indent=2)
    log.info(f"Saved {len(hourly_features)} hourly coastal surge records to {surge_hourly_out}")

    # -----------------------------------------------------------------------
    # Real DEM Inundation with Connectivity-Constrained Bathtub
    # -----------------------------------------------------------------------
    log.info("Loading real Copernicus GLO-30 DEM for connectivity-constrained bathtub simulation...")
    # Resample DEM to 500m simulation grid (244 rows x 336 cols)
    n_rows, n_cols = 244, 336
    with rasterio.open(dem_path) as ds:
        dem_grid = ds.read(1, out_shape=(n_rows, n_cols), resampling=Resampling.bilinear)
        dem_grid = np.where(dem_grid < -100, 0.0, dem_grid)
        dem_grid = np.maximum(0.0, dem_grid)

    lats_arr = np.linspace(bbox[3], bbox[1], n_rows)  # north to south
    lons_arr = np.linspace(bbox[0], bbox[2], n_cols)  # west to east
    lons_2d, lats_2d = np.meshgrid(lons_arr, lats_arr)

    cell_dlat = abs(lats_arr[1] - lats_arr[0])
    cell_dlon = abs(lons_arr[1] - lons_arr[0])
    cell_area_km2 = 0.25  # ~500m x 500m = 0.25 km²

    # Identify open ocean: contiguous water cells connected to south/east boundaries
    ocean_candidates = (dem_grid <= 0.0)
    structure_8 = np.ones((3, 3), dtype=int)
    lbl_ocean, _ = label(ocean_candidates, structure=structure_8)
    ocean_seed_lbl = lbl_ocean[-1, -1]  # south-east corner in Bay of Bengal
    ocean_mask = (lbl_ocean == ocean_seed_lbl) & ocean_candidates

    # Identify coastline cells (land cells directly adjacent to ocean mask)
    coast_line = binary_dilation(ocean_mask, structure=structure_8) & (~ocean_mask)

    # Distance to coast in km (500m grid cell)
    dist_to_coast_km = distance_transform_edt(~coast_line) * 0.5

    # Interpolate coastal peak surge across the coastal line
    cp_coords = np.array([[cp[1], cp[0]] for cp in COASTAL_POINTS])  # (lat, lon)
    station_peaks = np.array([peak_surge_by_point[i] for i in range(len(COASTAL_POINTS))])

    # Assign nearest coastal station surge to all grid points
    grid_coords = np.stack([lats_2d.ravel(), lons_2d.ravel()], axis=1)
    dists_to_stations = np.hypot(
        grid_coords[:, 0:1] - cp_coords[:, 0].reshape(1, -1),
        (grid_coords[:, 1:2] - cp_coords[:, 1].reshape(1, -1)) * np.cos(np.radians(20.0)),
    )
    nearest_station_idx = np.argmin(dists_to_stations, axis=1)
    grid_surge_peak = station_peaks[nearest_station_idx].reshape(n_rows, n_cols)

    # Attenuated surge level: eta(x, y) = surge_peak - alpha * distance
    eta_surge = grid_surge_peak - (alpha * dist_to_coast_km)

    # Candidate flooded cells: elevation < eta_surge within max_inland_km on land
    flood_candidate = (
        (dem_grid < eta_surge)
        & (dist_to_coast_km <= max_inland_km)
        & (~ocean_mask)
    )

    # CONNECTIVITY CONSTRAINT (8-connectivity):
    # Floodwater must be connected to the open ocean boundary.
    # NOTE: label() re-numbers components from scratch, so the wet-network label at
    # the sea boundary (SE corner, Bay of Bengal) is NOT the same integer as
    # ocean_seed_lbl from the ocean-only labelling. We must read lbl_wet[-1,-1].
    wet_network = ocean_mask | flood_candidate
    lbl_wet, _ = label(wet_network, structure=structure_8)
    wet_seed_lbl = int(lbl_wet[-1, -1])  # label of the open-ocean component in wet_network
    connected_flood_mask = (lbl_wet == wet_seed_lbl) & flood_candidate

    # Flood depth
    flood_depth_grid = np.where(connected_flood_mask, eta_surge - dem_grid, 0.0)
    flood_depth_grid = np.maximum(0.0, flood_depth_grid)

    # Assign each grid cell to a district based on closest district centroid
    dist_names = list(DISTRICT_CENTROIDS.keys())
    dist_centers = np.array([DISTRICT_CENTROIDS[d] for d in dist_names])
    dists_to_districts = np.hypot(
        grid_coords[:, 0:1] - dist_centers[:, 0].reshape(1, -1),
        (grid_coords[:, 1:2] - dist_centers[:, 1].reshape(1, -1)) * np.cos(np.radians(20.0)),
    )
    nearest_dist_idx = np.argmin(dists_to_districts, axis=1).reshape(n_rows, n_cols)

    # Build vector polygons for flooded cells (> 10 cm depth)
    inundation_features = []
    district_summary: dict[str, dict[str, float]] = {
        d: {"peak_surge_m": 0.0, "max_depth_m": 0.0, "flooded_area_km2": 0.0}
        for d in dist_names
    }

    stride_lat = cell_dlat / 2.0
    stride_lon = cell_dlon / 2.0

    for i in range(n_rows):
        for j in range(n_cols):
            depth = float(flood_depth_grid[i, j])
            if depth < 0.10:
                continue

            c_lat = float(lats_2d[i, j])
            c_lon = float(lons_2d[i, j])
            elev = float(dem_grid[i, j])
            d_km = float(dist_to_coast_km[i, j])
            dist_name = dist_names[int(nearest_dist_idx[i, j])]

            if depth >= 1.5:
                sev = "Catastrophic"
            elif depth >= 0.6:
                sev = "Severe"
            elif depth >= 0.3:
                sev = "Moderate (Impassable)"
            else:
                sev = "Minor"

            cell_poly = [
                [round(c_lon - stride_lon, 5), round(c_lat - stride_lat, 5)],
                [round(c_lon + stride_lon, 5), round(c_lat - stride_lat, 5)],
                [round(c_lon + stride_lon, 5), round(c_lat + stride_lat, 5)],
                [round(c_lon - stride_lon, 5), round(c_lat + stride_lat, 5)],
                [round(c_lon - stride_lon, 5), round(c_lat - stride_lat, 5)],
            ]

            inundation_features.append(
                polygon_feature(
                    coordinates=[cell_poly],
                    properties={
                        "depth_m": round(depth, 2),
                        "severity": sev,
                        "elevation_m": round(elev, 2),
                        "dist_to_coast_km": round(d_km, 1),
                        "district": dist_name,
                    },
                )
            )

            # District rollup
            district_summary[dist_name]["flooded_area_km2"] += cell_area_km2
            if depth > district_summary[dist_name]["max_depth_m"]:
                district_summary[dist_name]["max_depth_m"] = round(depth, 2)
            station_s = float(grid_surge_peak[i, j])
            if station_s > district_summary[dist_name]["peak_surge_m"]:
                district_summary[dist_name]["peak_surge_m"] = round(station_s, 2)

    for d in dist_names:
        district_summary[d]["flooded_area_km2"] = round(district_summary[d]["flooded_area_km2"], 1)

    # Save inundation GeoJSON
    with open(surge_inundation_out, "w") as f:
        json.dump(feature_collection(inundation_features), f)
    log.info(f"Saved {len(inundation_features)} flood polygons to {surge_inundation_out}")

    # Compute hourly district time series for T-24h to T+24h
    hourly_district_ts = []
    for pt_feat in sim_points:
        p = pt_feat["properties"]
        t_h = p.get("hours_to_landfall", 0.0)
        time_utc = p.get("time_utc", "")
        # Hydrodynamic time envelope peaking at landfall
        t_envelope = max(0.0, 1.0 - (abs(t_h) / 12.0) ** 2) if abs(t_h) <= 12.0 else 0.0
        row: dict[str, Any] = {
            "hours_to_landfall": round(t_h, 1),
            "time_utc": time_utc,
            "districts": {},
        }
        for d in dist_names:
            peak_a = district_summary[d]["flooded_area_km2"]
            peak_d = district_summary[d]["max_depth_m"]
            row["districts"][d] = {
                "flooded_area_km2": round(peak_a * t_envelope, 1),
                "max_depth_m": round(peak_d * t_envelope, 2),
            }
        hourly_district_ts.append(row)

    full_district_output = {
        "summary": district_summary,
        "hourly": hourly_district_ts,
    }
    with open(surge_ts_out, "w") as f:
        json.dump(full_district_output, f, indent=2)
    log.info(f"Saved district surge summary to {surge_ts_out}")

    # Save metadata with computed numbers
    overall_peak_surge = round(float(np.max(station_peaks)), 2)
    overall_max_depth = round(float(np.max(flood_depth_grid)), 2)
    total_flooded_km2 = round(float(sum(d["flooded_area_km2"] for d in district_summary.values())), 1)

    meta = {
        "scenario": scenario,
        "dem_source": "Copernicus GLO-30 DEM (Microsoft Planetary Computer cop-dem-glo-30)",
        "dem_type": "Digital Surface Model (DSM)",
        "grid_resolution_m": 500,
        "max_peak_surge_m": overall_peak_surge,
        "max_flood_depth_m": overall_max_depth,
        "total_flooded_area_km2": total_flooded_km2,
        "total_flooded_polygons": len(inundation_features),
        "inland_attenuation_coeff_m_per_km": round(alpha, 3),
        "max_inland_km": max_inland_km,
        "astronomical_tide_m": cfg_surge.get("tide_height_m", 1.2),
        "connectivity_constrained": True,
        "connectivity_type": "8-connected",
        "physics": "Inverse Barometer + Shallow Shelf Wind Setup + Semi-diurnal Tide + Connectivity-Constrained Bathtub",
        "citation": "Pugh (1987) Tides, Surges and Mean Sea-Level; Harper et al. (2010); Poulter & Halpin (2008)",
        "district_flooded_area_km2": {d: district_summary[d]["flooded_area_km2"] for d in dist_names},
    }
    with open(surge_meta_out, "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Saved surge metadata to {surge_meta_out}")

    # -----------------------------------------------------------------------
    # Generate High-Resolution Visualization PNG
    # -----------------------------------------------------------------------
    log.info("Generating surge inundation PNG figure...")
    fig, (ax_map, ax_ts) = plt.subplots(1, 2, figsize=(15, 6.5), dpi=150)

    # Panel 1: Map
    masked_depth = np.ma.masked_where(flood_depth_grid <= 0.1, flood_depth_grid)
    ax_map.set_facecolor("#111827")
    ax_map.imshow(
        dem_grid,
        extent=[bbox[0], bbox[2], bbox[1], bbox[3]],
        cmap="gray",
        vmin=0,
        vmax=60,
        alpha=0.35,
    )
    im_flood = ax_map.imshow(
        masked_depth,
        extent=[bbox[0], bbox[2], bbox[1], bbox[3]],
        cmap="Blues",
        vmin=0.1,
        vmax=4.0,
        alpha=0.85,
    )
    cbar = plt.colorbar(im_flood, ax=ax_map, fraction=0.035, pad=0.03)
    cbar.set_label("Surge Inundation Depth (m)", color="white", fontsize=10)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")

    # Plot coastal observation points
    for idx, (cp_lon, cp_lat, d_name, _, cp_name) in enumerate(COASTAL_POINTS):
        p_s = peak_surge_by_point[idx]
        ax_map.scatter(cp_lon, cp_lat, color="#f59e0b", edgecolors="black", s=60, zorder=5)
        ax_map.text(
            cp_lon + 0.02,
            cp_lat - 0.02,
            f"{cp_name.split('/')[0].strip()} ({p_s:.1f}m)",
            color="#fbbf24",
            fontsize=7,
            fontweight="bold",
            zorder=6,
        )

    # Plot track near landfall
    track_lons = [pt["geometry"]["coordinates"][0] for pt in sim_points]
    track_lats = [pt["geometry"]["coordinates"][1] for pt in sim_points]
    ax_map.plot(track_lons, track_lats, color="#ef4444", linestyle="--", linewidth=1.8, label="Track (T-24h..T+24h)")
    landfall_pt = config.get("landfall", {})
    ax_map.scatter(
        [landfall_pt.get("lon", 85.85)],
        [landfall_pt.get("lat", 19.85)],
        marker="X",
        color="#ef4444",
        edgecolors="white",
        s=120,
        zorder=7,
        label="Landfall (~02:40 UTC)",
    )

    ax_map.set_xlim(bbox[0], bbox[2])
    ax_map.set_ylim(bbox[1], bbox[3])
    ax_map.set_title(
        f"Cyclone Fani (2019) Peak Surge Inundation\nReal Copernicus GLO-30 DEM (Peak: {overall_peak_surge:.2f} m, Area: {total_flooded_km2:,.1f} km²)",
        color="white",
        fontsize=11,
        fontweight="bold",
    )
    ax_map.tick_params(colors="white")
    for spine in ax_map.spines.values():
        spine.set_color("#374151")
    ax_map.legend(loc="upper left", facecolor="#1f2937", edgecolor="#374151", labelcolor="white", fontsize=8)

    # Panel 2: Hourly Surge Timeseries at Key Stations
    fig.patch.set_facecolor("#0b0f19")
    ax_ts.set_facecolor("#111827")

    colors = {
        "Puri Beach (Landfall Zone)": "#ef4444",
        "Paradip Port": "#3b82f6",
        "Satapada / Chilika Mouth": "#10b981",
        "Astaranga / Devi Estuary": "#f59e0b",
    }
    for st_name, st_col in colors.items():
        if st_name in hourly_station_timeseries:
            records = hourly_station_timeseries[st_name]
            hours = [r["hours_to_landfall"] for r in records]
            surges = [r["surge_total_m"] for r in records]
            ax_ts.plot(hours, surges, label=st_name, color=st_col, linewidth=2.0)

    # Plot components for Puri Beach
    puri_records = hourly_station_timeseries.get("Puri Beach (Landfall Zone)", [])
    if puri_records:
        hours = [r["hours_to_landfall"] for r in puri_records]
        ax_ts.plot(hours, [r["surge_ib_m"] for r in puri_records], label="Puri: Inverse Barometer", color="#94a3b8", linestyle=":")
        ax_ts.plot(hours, [r["surge_wind_m"] for r in puri_records], label="Puri: Wind Setup", color="#fbbf24", linestyle="--")
        ax_ts.plot(hours, [r["tide_m"] for r in puri_records], label="Astronomical Tide", color="#60a5fa", linestyle="-.")

    ax_ts.set_xlabel("Hours to Landfall (T=0: 2019-05-03 02:40 UTC)", color="white", fontsize=10)
    ax_ts.set_ylabel("Water Level Above Mean Sea Level (m)", color="white", fontsize=10)
    ax_ts.set_title("Hourly Surge Component Breakdown (T-24h to T+24h)", color="white", fontsize=11, fontweight="bold")
    ax_ts.tick_params(colors="white")
    ax_ts.grid(True, color="#374151", linestyle="--", alpha=0.5)
    for spine in ax_ts.spines.values():
        spine.set_color("#374151")
    ax_ts.legend(loc="upper right", facecolor="#1f2937", edgecolor="#374151", labelcolor="white", fontsize=8)

    plt.tight_layout()
    fig.savefig(surge_png_out, dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
    shutil.copyfile(surge_png_out, docs_png_out)
    plt.close(fig)
    log.info(f"Saved visualization figure to {surge_png_out} and {docs_png_out}")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 03: Storm Surge & Coastal Inundation Model on Real DEM")
    parser.add_argument("--scenario", default="fani_2019", help="Scenario name")
    parser.add_argument("--attenuation", type=float, default=None, help="Custom attenuation coefficient")
    parser.add_argument("--force", action="store_true", help="Force regenerate")
    args = parser.parse_args()

    ok = run(scenario=args.scenario, attenuation_coeff=args.attenuation, force=args.force)
    sys.exit(0 if ok else 1)
