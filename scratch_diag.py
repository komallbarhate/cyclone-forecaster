"""Diagnostic script for surge model issues 2-7."""
import numpy as np
import rasterio
import json
import math
from rasterio.enums import Resampling
from scipy.ndimage import label, distance_transform_edt
from pathlib import Path

RAW = Path("data/raw")
PROC = Path("data/processed")
bbox = [84.9, 19.6, 86.5, 20.7]
n_rows, n_cols = 244, 336

with rasterio.open(RAW / "copernicus_glo30_dem.tif") as ds:
    dem_grid = ds.read(1, out_shape=(n_rows, n_cols), resampling=Resampling.bilinear)
dem_grid = np.where(dem_grid < -100, 0.0, dem_grid)
dem_grid = np.maximum(0.0, dem_grid)

# ---- Issue 2: component breakdown at 4.28m peak ----
with open(PROC / "surge_hourly.geojson") as f:
    hourly = json.load(f)

feats = hourly["features"]
top = sorted(feats, key=lambda x: -x["properties"]["surge_total_m"])[:10]
print("=== Top 10 surge points (Issue 2) ===")
for ft in top:
    p = ft["properties"]
    print(
        f"  {p['station_name']:40s} t={p['hours_to_landfall']:+6.1f}h "
        f"total={p['surge_total_m']:.2f} IB={p['surge_ib_m']:.2f} "
        f"wind={p['surge_wind_m']:.2f} tide={p['tide_m']:.2f} "
        f"local_wind={p['local_wind_kmh']:.1f} km/h"
    )

# ---- Issue 3: wind setup time evolution at Satapada ----
print("\n=== Satapada wind setup time evolution (Issue 3) ===")
satapada = [ft for ft in feats if ft["properties"]["station_name"] == "Satapada / Chilika Mouth"]
satapada.sort(key=lambda x: x["properties"]["hours_to_landfall"])
for ft in satapada:
    p = ft["properties"]
    if -12 <= p["hours_to_landfall"] <= 4:
        print(
            f"  t={p['hours_to_landfall']:+6.1f}h wind_kmh={p['local_wind_kmh']:6.1f} "
            f"IB={p['surge_ib_m']:.2f} windsetup={p['surge_wind_m']:.2f} "
            f"tide={p['tide_m']:.2f} total={p['surge_total_m']:.2f}"
        )

# ---- Issue 4: right-track stations (Paradip, Ersama, Mahakalpara) ----
print("\n=== Right-track stations at peak (Issue 4) ===")
right_track = ["Paradip Port", "Ersama Coastal Belt", "Mahakalpara / Hukitola", "Rajanagar / Bhitarkanika", "Puri Beach (Landfall Zone)", "Konark / Chandrabhaga", "Astaranga / Devi Estuary"]
for name in right_track:
    pts = [ft for ft in feats if ft["properties"]["station_name"] == name]
    if pts:
        peak = max(pts, key=lambda x: x["properties"]["surge_total_m"])
        p = peak["properties"]
        print(
            f"  {p['station_name']:40s} t={p['hours_to_landfall']:+6.1f}h "
            f"wind={p['local_wind_kmh']:.1f} coast_normal={None} "
            f"IB={p['surge_ib_m']:.2f} windsetup={p['surge_wind_m']:.2f} "
            f"tide={p['tide_m']:.2f} total={p['surge_total_m']:.2f}"
        )

# ---- Wind setup manual calc for Paradip at t=0 ----
print("\n=== Manual wind setup check for Paradip at t~0 (Issue 4) ===")
# Paradip: lon=86.67, lat=20.29, coast_normal=120
# At landfall, track is at lon=85.85, lat=19.85 (from config)
# bearing from eye to Paradip
import sys
sys.path.insert(0, str(Path(".").resolve()))
from pipeline.utils.geo import haversine_km, bearing_deg
from pipeline.step_03_surge_model import compute_wind_setup

eye_lat, eye_lon = 19.85, 85.85  # approx at t=0
cp_lat, cp_lon = 20.29, 86.67   # Paradip
dist = haversine_km(cp_lat, cp_lon, eye_lat, eye_lon)
brg = bearing_deg(eye_lat, eye_lon, cp_lat, cp_lon)
wind_vec_dir = (brg - 90.0) % 360.0
rmw = 35.0
vmax = 175.0
local_wind = vmax * ((rmw / dist) ** 0.5) if dist > rmw else vmax * (dist / rmw)

print(f"  dist={dist:.1f}km, bearing eye->Paradip={brg:.1f}deg")
print(f"  wind_vec_dir={wind_vec_dir:.1f}deg, coast_normal=120deg")
print(f"  local_wind={local_wind:.1f} km/h")
d_theta = math.radians(abs(wind_vec_dir - 120.0))
cos_align = max(0.0, math.cos(d_theta))
print(f"  d_theta={math.degrees(d_theta):.1f}deg, cos_align={cos_align:.4f}")
setup = compute_wind_setup(local_wind, wind_vec_dir, 120.0)
print(f"  computed wind setup = {setup:.3f}m")

# ---- Issue 7: attenuation diagonal wedge ----
print("\n=== Attenuation diagonal (Issue 7): coast line structure ===")
structure_8 = np.ones((3, 3), dtype=int)
ocean_cands = (dem_grid <= 0.0)
lbl_ocean, _ = label(ocean_cands, structure=structure_8)
ocean_mask = (lbl_ocean == int(lbl_ocean[-1, -1])) & ocean_cands

from scipy.ndimage import binary_dilation
coast_line = binary_dilation(ocean_mask, structure=structure_8) & (~ocean_mask)
dist_coast = distance_transform_edt(~coast_line) * 0.5  # km

lats_arr = np.linspace(bbox[3], bbox[1], n_rows)
lons_arr = np.linspace(bbox[0], bbox[2], n_cols)
lons_2d, lats_2d = np.meshgrid(lons_arr, lats_arr)

# Show dist_coast pattern along bottom rows (should be smooth, not diagonal wedge)
for i in [n_rows-1, n_rows-10, n_rows-20]:
    row_d = dist_coast[i, :]
    print(f"  Row {i} (lat={lats_arr[i]:.2f}): dist_coast min={row_d.min():.1f} max={row_d.max():.1f} mean={row_d.mean():.1f}")
