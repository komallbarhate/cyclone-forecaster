"""Diagnostic part 2: Chilika, JRC masking, surge breakdown."""
import json, math
import numpy as np
import rasterio
from rasterio.enums import Resampling
from scipy.ndimage import label, binary_dilation, distance_transform_edt
from pathlib import Path

RAW = Path("data/raw"); PROC = Path("data/processed")
bbox = [84.9, 19.6, 86.5, 20.7]
n_rows, n_cols = 244, 336

with rasterio.open(RAW / "copernicus_glo30_dem.tif") as ds:
    dem_grid = ds.read(1, out_shape=(n_rows, n_cols), resampling=Resampling.bilinear)
dem_grid = np.where(dem_grid < -100, 0.0, dem_grid)
dem_grid = np.maximum(0.0, dem_grid)

with rasterio.open(RAW / "jrc_gsw_occurrence.tif") as ds:
    jrc = ds.read(1, out_shape=(n_rows, n_cols), resampling=Resampling.nearest)

lats_arr = np.linspace(bbox[3], bbox[1], n_rows)
lons_arr = np.linspace(bbox[0], bbox[2], n_cols)
lons_2d, lats_2d = np.meshgrid(lons_arr, lats_arr)

structure_8 = np.ones((3, 3), dtype=int)
ocean_cands = (dem_grid <= 0.0)
lbl_ocean, _ = label(ocean_cands, structure=structure_8)
ocean_mask = (lbl_ocean == int(lbl_ocean[-1, -1])) & ocean_cands

# Chilika: roughly 85.0-85.55E, 19.6-19.9N
chilika_mask = (lons_2d >= 85.0) & (lons_2d <= 85.55) & (lats_2d >= 19.6) & (lats_2d <= 19.95)
print(f"Chilika region cells: {chilika_mask.sum()}")
print(f"  DEM<=0 in Chilika: {(ocean_cands & chilika_mask).sum()}")
print(f"  In ocean_mask: {(ocean_mask & chilika_mask).sum()}")
print(f"  JRC>=50 in Chilika: {((jrc >= 50) & chilika_mask).sum()} = {((jrc >= 50) & chilika_mask).sum() * 0.25:.0f} km2")
print(f"  JRC>=80 in Chilika: {((jrc >= 80) & chilika_mask).sum()} = {((jrc >= 80) & chilika_mask).sum() * 0.25:.0f} km2")

# Compute flood without and with JRC mask
coast_line = binary_dilation(ocean_mask, structure=structure_8) & (~ocean_mask)
dist_coast = distance_transform_edt(~coast_line) * 0.5

# Station surge peaks
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

# Load surge meta for peak surge values per station
with open(PROC / "surge_meta.json") as f:
    meta = json.load(f)
print(f"\nSurge meta peak: {meta['max_peak_surge_m']}m, flooded: {meta['total_flooded_area_km2']} km2")
print("District areas:", meta["district_flooded_area_km2"])

# Per-district counts with and without JRC mask
grid_coords = np.stack([lats_2d.ravel(), lons_2d.ravel()], axis=1)
DISTRICT_CENTROIDS = {
    "Puri": (19.81, 85.83), "Khordha": (20.18, 85.62),
    "Jagatsinghpur": (20.27, 86.17), "Kendrapara": (20.50, 86.42),
    "Cuttack": (20.46, 85.88),
}
dist_names = list(DISTRICT_CENTROIDS.keys())
dist_centers = np.array([DISTRICT_CENTROIDS[d] for d in dist_names])
dists_to_districts = np.hypot(
    grid_coords[:, 0:1] - dist_centers[:, 0].reshape(1, -1),
    (grid_coords[:, 1:2] - dist_centers[:, 1].reshape(1, -1)) * np.cos(np.radians(20.0)),
)
nearest_dist_idx = np.argmin(dists_to_districts, axis=1).reshape(n_rows, n_cols)

# Use the actual surge peaks from the meta
alpha = 0.1
cp_coords = np.array([[cp[1], cp[0]] for cp in COASTAL_POINTS])
station_peaks = [4.28, 2.08, 2.25, 1.96, 1.96, 1.96, 1.96, 1.96, 1.96]  # from diagnostic
sp = np.array(station_peaks)
dists_to_stations = np.hypot(
    grid_coords[:, 0:1] - cp_coords[:, 0].reshape(1, -1),
    (grid_coords[:, 1:2] - cp_coords[:, 1].reshape(1, -1)) * np.cos(np.radians(20.0)),
)
nearest_station_idx = np.argmin(dists_to_stations, axis=1)
grid_surge_peak = sp[nearest_station_idx].reshape(n_rows, n_cols)
eta_surge = grid_surge_peak - (alpha * dist_coast)
flood_candidate = (dem_grid < eta_surge) & (dist_coast <= 30.0) & (~ocean_mask)
wet = ocean_mask | flood_candidate
lbl_wet, _ = label(wet, structure=structure_8)
wet_seed = int(lbl_wet[-1, -1])
connected = (lbl_wet == wet_seed) & flood_candidate

jrc_perm = (jrc >= 80)  # 80% occurrence = permanent water
non_perm = connected & ~jrc_perm

print("\n=== Per-district flooded area with / without JRC>=80 mask ===")
for i, d in enumerate(dist_names):
    dm = (nearest_dist_idx == i)
    with_all = (connected & dm).sum() * 0.25
    without_perm = (non_perm & dm).sum() * 0.25
    print(f"  {d:20s}: raw={with_all:.1f} km2  after_JRC_mask={without_perm:.1f} km2  masked={with_all-without_perm:.1f} km2")
total_raw = connected.sum() * 0.25
total_np = non_perm.sum() * 0.25
print(f"  {'TOTAL':20s}: raw={total_raw:.1f} km2  after_JRC_mask={total_np:.1f} km2")
