"""
CycloneShield Open Data Ingestion Utility
=========================================
Downloads and caches open geospatial datasets for the CycloneShield pipeline
into `data/raw/` without requiring Google Earth Engine:

1. Copernicus GLO-30 DEM (Microsoft Planetary Computer: cop-dem-glo-30)
2. Sentinel-1 RTC VV (Pre- and Post-event SAR from Microsoft Planetary Computer: sentinel-1-rtc)
3. JRC Global Surface Water occurrence mask (Microsoft Planetary Computer: jrc-gsw)
4. WorldPop 2019 Population (Direct download from data.worldpop.org)
5. CHIRPS Daily Rainfall (Direct download from Climate Hazards Center)

HARD RULES:
- No synthetic, mock, or fallback data.
- Downloads once into `data/raw/` (cached; skips if exists unless --force is given).
- Fails clearly if any source is unavailable.
- Reports exact scenes, acquisition dates, file sizes, and CRS.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from rasterio.windows import from_bounds
import requests
import yaml

from pipeline.utils.logger import get_logger

log = get_logger(__name__)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def get_stac_catalog() -> pystac_client.Client:
    """Connect to Microsoft Planetary Computer STAC catalog with signed asset URLs."""
    try:
        return pystac_client.Client.open(
            PC_STAC_URL,
            modifier=planetary_computer.sign_inplace,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to connect to Microsoft Planetary Computer STAC API: {exc}"
        ) from exc


def download_file(url: str, dest_path: Path, chunk_size: int = 262144) -> Path:
    """Stream download a file via HTTP GET with progress logging."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".part")
    log.info(f"Downloading {dest_path.name} from {url[:80]}...")
    resp = requests.get(url, stream=True, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} downloading {url}")
    total_bytes = 0
    with open(temp_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                total_bytes += len(chunk)
    temp_path.replace(dest_path)
    log.info(f"Downloaded {dest_path.name} ({total_bytes / 1e6:.2f} MB)")
    return dest_path


# ---------------------------------------------------------------------------
# 1. Copernicus GLO-30 DEM
# ---------------------------------------------------------------------------
def fetch_copernicus_dem(
    bbox: list[float],
    out_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Download and mosaic Copernicus GLO-30 DEM for the AOI bbox from Planetary Computer.
    Downloads tiles locally to data/raw/dem_tiles/ before merging to prevent network drops.
    Bbox format: [lon_min, lat_min, lon_max, lat_max].
    """
    out_path = out_path or (RAW_DIR / "copernicus_glo30_dem.tif")
    if not force and out_path.exists() and out_path.stat().st_size > 1024:
        log.info(f"[CACHE] Copernicus GLO-30 DEM exists: {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")
        with rasterio.open(out_path) as ds:
            return {
                "dataset": "Copernicus GLO-30 DEM",
                "collection": "cop-dem-glo-30",
                "file": str(out_path),
                "size_mb": round(out_path.stat().st_size / 1e6, 2),
                "crs": str(ds.crs),
                "shape": ds.shape,
                "bounds": [round(b, 4) for b in ds.bounds],
                "cached": True,
            }

    log.info(f"Querying Planetary Computer for Copernicus GLO-30 DEM over bbox {bbox}...")
    catalog = get_stac_catalog()
    search = catalog.search(collections=["cop-dem-glo-30"], bbox=bbox)
    items = list(search.items())
    if not items:
        raise RuntimeError(f"FAIL: No Copernicus GLO-30 DEM scenes found for bbox {bbox}")

    tile_dir = RAW_DIR / "dem_tiles"
    tile_dir.mkdir(parents=True, exist_ok=True)
    local_tiles = []
    scene_ids = []

    for item in items:
        scene_ids.append(item.id)
        tile_file = tile_dir / f"{item.id}.tif"
        if not tile_file.exists() or force or tile_file.stat().st_size < 1024:
            asset = item.assets.get("data")
            if not asset:
                raise RuntimeError(f"FAIL: DEM item {item.id} has no 'data' asset")
            download_file(asset.href, tile_file)
        local_tiles.append(tile_file)

    log.info(f"Merging {len(local_tiles)} DEM tiles clipped to bbox {bbox}...")
    src_files = [rasterio.open(f) for f in local_tiles]
    try:
        mosaic, out_transform = merge(src_files, bounds=bbox)
        out_meta = src_files[0].meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_transform,
            "compress": "deflate",
            "nodata": -9999.0,
        })
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out_path, "w", **out_meta) as dest:
            dest.write(mosaic.astype(np.float32))
    finally:
        for s in src_files:
            s.close()

    size_mb = out_path.stat().st_size / 1e6
    log.info(f"Saved Copernicus GLO-30 DEM -> {out_path} ({size_mb:.2f} MB)")

    return {
        "dataset": "Copernicus GLO-30 DEM",
        "collection": "cop-dem-glo-30",
        "scenes": scene_ids,
        "file": str(out_path),
        "size_mb": round(size_mb, 2),
        "crs": str(out_meta["crs"]),
        "shape": (mosaic.shape[1], mosaic.shape[2]),
        "bounds": bbox,
        "cached": False,
    }


# ---------------------------------------------------------------------------
# 2. Sentinel-1 RTC VV (Pre & Post Cyclone Fani)
# ---------------------------------------------------------------------------
def fetch_sentinel1_rtc(
    bbox: list[float],
    out_pre_path: Path | None = None,
    out_post_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Download Sentinel-1 Radiometrically Terrain Corrected (RTC) VV SAR scenes
    pre-event (22 Apr 2019) and post-event (04 May 2019, 24h post-landfall)
    from Microsoft Planetary Computer.
    Reads AOI window directly from remote COG at 30m resolution.
    """
    out_pre_path = out_pre_path or (RAW_DIR / "s1_rtc_vv_pre.tif")
    out_post_path = out_post_path or (RAW_DIR / "s1_rtc_vv_post.tif")

    results = {}

    if (
        not force
        and out_pre_path.exists()
        and out_post_path.exists()
        and out_pre_path.stat().st_size > 1024
        and out_post_path.stat().st_size > 1024
    ):
        log.info(f"[CACHE] Sentinel-1 RTC VV files exist: {out_pre_path.name}, {out_post_path.name}")
        with rasterio.open(out_pre_path) as ds_pre, rasterio.open(out_post_path) as ds_post:
            return {
                "pre": {
                    "dataset": "Sentinel-1 RTC VV (Pre-event)",
                    "file": str(out_pre_path),
                    "size_mb": round(out_pre_path.stat().st_size / 1e6, 2),
                    "crs": str(ds_pre.crs),
                    "shape": ds_pre.shape,
                    "cached": True,
                },
                "post": {
                    "dataset": "Sentinel-1 RTC VV (Post-event)",
                    "file": str(out_post_path),
                    "size_mb": round(out_post_path.stat().st_size / 1e6, 2),
                    "crs": str(ds_post.crs),
                    "shape": ds_post.shape,
                    "cached": True,
                },
            }

    catalog = get_stac_catalog()

    # Pre-event: ~15-28 Apr 2019
    log.info("Searching Sentinel-1 RTC for pre-event window (2019-04-15 to 2019-04-28)...")
    search_pre = catalog.search(
        collections=["sentinel-1-rtc"],
        bbox=bbox,
        datetime="2019-04-15/2019-04-28",
    )
    items_pre = list(search_pre.items())
    if not items_pre:
        raise RuntimeError(f"FAIL: No Sentinel-1 RTC pre-event scenes found in 2019-04-15/2019-04-28 for {bbox}")

    target_pre_id = "S1A_IW_GRDH_1SDV_20190422T000501_20190422T000530_026895_030652_rtc"
    chosen_pre = next((it for it in items_pre if it.id == target_pre_id), items_pre[0])

    # Post-event: ~03-08 May 2019
    log.info("Searching Sentinel-1 RTC for post-event window (2019-05-03 to 2019-05-08)...")
    search_post = catalog.search(
        collections=["sentinel-1-rtc"],
        bbox=bbox,
        datetime="2019-05-03/2019-05-08",
    )
    items_post = list(search_post.items())
    if not items_post:
        raise RuntimeError(f"FAIL: No Sentinel-1 RTC post-event scenes found in 2019-05-03/2019-05-08 for {bbox}")

    target_post_id = "S1A_IW_GRDH_1SDV_20190504T000512_20190504T000537_027070_030CB5_rtc"
    chosen_post = next((it for it in items_post if it.id == target_post_id), items_post[0])

    log.info(f"Selected Pre-event scene: {chosen_pre.id} ({chosen_pre.datetime})")
    log.info(f"Selected Post-event scene: {chosen_post.id} ({chosen_post.datetime})")

    def _read_window_s1(item, out_f: Path) -> dict[str, Any]:
        vv_asset = item.assets.get("vv")
        if not vv_asset:
            raise RuntimeError(f"FAIL: S1 scene {item.id} has no 'vv' asset")

        log.info(f"Reading S1 RTC VV window for {item.id}...")
        with rasterio.open(vv_asset.href) as src:
            tb = transform_bounds("EPSG:4326", src.crs, *bbox)
            clip_b = (
                max(tb[0], src.bounds.left),
                max(tb[1], src.bounds.bottom),
                min(tb[2], src.bounds.right),
                min(tb[3], src.bounds.top),
            )
            win = from_bounds(*clip_b, transform=src.transform)

            scale_factor = src.res[0] / 30.0  # export at 30m resolution for consistency with DEM
            out_h = max(int(win.height * scale_factor), 10)
            out_w = max(int(win.width * scale_factor), 10)

            data = src.read(1, window=win, out_shape=(out_h, out_w), resampling=Resampling.bilinear)
            out_transform = rasterio.transform.from_bounds(*clip_b, out_w, out_h)

            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_h,
                "width": out_w,
                "transform": out_transform,
                "compress": "deflate",
                "nodata": src.nodata or -32768.0,
            })

            out_f.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(out_f, "w", **out_meta) as dest:
                dest.write(data, 1)

        size_mb = out_f.stat().st_size / 1e6
        log.info(f"Saved S1 RTC VV -> {out_f} ({size_mb:.2f} MB)")
        return {
            "scene_id": item.id,
            "datetime": str(item.datetime),
            "file": str(out_f),
            "size_mb": round(size_mb, 2),
            "crs": str(out_meta["crs"]),
            "shape": (out_h, out_w),
            "native_res_m": src.res[0],
            "exported_res_m": 30.0,
        }

    results["pre"] = _read_window_s1(chosen_pre, out_pre_path)
    results["post"] = _read_window_s1(chosen_post, out_post_path)
    return results


# ---------------------------------------------------------------------------
# 3. JRC Global Surface Water
# ---------------------------------------------------------------------------
def fetch_jrc_gsw(
    bbox: list[float],
    out_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Download JRC Global Surface Water occurrence layer from Planetary Computer (jrc-gsw).
    Permanent water mask used to prevent false positive flood detections.
    """
    out_path = out_path or (RAW_DIR / "jrc_gsw_occurrence.tif")
    if not force and out_path.exists() and out_path.stat().st_size > 1024:
        log.info(f"[CACHE] JRC GSW exists: {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")
        with rasterio.open(out_path) as ds:
            return {
                "dataset": "JRC Global Surface Water",
                "collection": "jrc-gsw",
                "file": str(out_path),
                "size_mb": round(out_path.stat().st_size / 1e6, 2),
                "crs": str(ds.crs),
                "shape": ds.shape,
                "cached": True,
            }

    log.info(f"Querying Planetary Computer for JRC GSW over bbox {bbox}...")
    catalog = get_stac_catalog()
    search = catalog.search(collections=["jrc-gsw"], bbox=bbox)
    items = list(search.items())
    if not items:
        raise RuntimeError(f"FAIL: No JRC GSW items found for bbox {bbox}")

    jrc_dir = RAW_DIR / "jrc_tiles"
    jrc_dir.mkdir(parents=True, exist_ok=True)
    local_tiles = []
    scene_ids = []

    for item in items:
        scene_ids.append(item.id)
        tile_file = jrc_dir / f"{item.id}_occurrence.tif"
        if not tile_file.exists() or force or tile_file.stat().st_size < 1024:
            asset = item.assets.get("occurrence")
            if not asset:
                raise RuntimeError(f"FAIL: JRC tile {item.id} missing 'occurrence' asset")
            download_file(asset.href, tile_file)
        local_tiles.append(tile_file)

    log.info(f"Merging {len(local_tiles)} JRC GSW tiles clipped to bbox {bbox}...")
    src_files = [rasterio.open(f) for f in local_tiles]
    try:
        mosaic, out_transform = merge(src_files, bounds=bbox)
        out_meta = src_files[0].meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_transform,
            "compress": "deflate",
        })
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out_path, "w", **out_meta) as dest:
            dest.write(mosaic)
    finally:
        for s in src_files:
            s.close()

    size_mb = out_path.stat().st_size / 1e6
    log.info(f"Saved JRC GSW occurrence -> {out_path} ({size_mb:.2f} MB)")

    return {
        "dataset": "JRC Global Surface Water",
        "collection": "jrc-gsw",
        "asset": "occurrence",
        "scenes": scene_ids,
        "file": str(out_path),
        "size_mb": round(size_mb, 2),
        "crs": str(out_meta["crs"]),
        "shape": (mosaic.shape[1], mosaic.shape[2]),
        "cached": False,
    }


# ---------------------------------------------------------------------------
# 4. WorldPop 2019 Population
# ---------------------------------------------------------------------------
def fetch_worldpop(
    bbox: list[float],
    out_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Direct download WorldPop 2019 unconstrained population raster for India (1km aggregated),
    and crop to the scenario AOI bbox.
    """
    out_path = out_path or (RAW_DIR / "worldpop_aoi_2019.tif")
    full_ind_path = RAW_DIR / "ind_ppp_2019_1km_Aggregated.tif"

    if not force and out_path.exists() and out_path.stat().st_size > 1024:
        log.info(f"[CACHE] WorldPop AOI raster exists: {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")
        with rasterio.open(out_path) as ds:
            return {
                "dataset": "WorldPop 2019 India (1km Aggregated)",
                "source_url": "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2019/IND/",
                "file": str(out_path),
                "size_mb": round(out_path.stat().st_size / 1e6, 2),
                "crs": str(ds.crs),
                "shape": ds.shape,
                "total_population_aoi": round(float(np.nansum(ds.read(1)[ds.read(1) > 0]))),
                "cached": True,
            }

    url = "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2019/IND/ind_ppp_2019_1km_Aggregated.tif"
    if not full_ind_path.exists() or force or full_ind_path.stat().st_size < 1024:
        download_file(url, full_ind_path)

    log.info(f"Cropping WorldPop to AOI bbox {bbox}...")
    with rasterio.open(full_ind_path) as src:
        win = from_bounds(*bbox, transform=src.transform)
        data = src.read(1, window=win)
        out_transform = rasterio.windows.transform(win, src.transform)

        out_meta = src.meta.copy()
        out_meta.update({
            "height": data.shape[0],
            "width": data.shape[1],
            "transform": out_transform,
            "compress": "deflate",
        })

        with rasterio.open(out_path, "w", **out_meta) as dest:
            dest.write(data, 1)

    pop_sum = float(np.nansum(data[data > 0]))
    log.info(f"Saved cropped WorldPop -> {out_path} (AOI population sum: {pop_sum:,.0f})")

    return {
        "dataset": "WorldPop 2019 India (1km Aggregated)",
        "source_url": url,
        "file": str(out_path),
        "size_mb": round(out_path.stat().st_size / 1e6, 2),
        "crs": str(out_meta["crs"]),
        "shape": data.shape,
        "total_population_aoi": round(pop_sum),
        "cached": False,
    }


# ---------------------------------------------------------------------------
# 5. CHIRPS Daily Rainfall
# ---------------------------------------------------------------------------
def fetch_chirps_rainfall(
    bbox: list[float],
    dates: list[str] | None = None,
    out_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Direct download CHIRPS daily precipitation (0.05° resolution) for Cyclone Fani event dates
    (2019-05-02, 2019-05-03, 2019-05-04) from UCSB Climate Hazards Center.
    Mosaics / accumulates event rainfall and crops to AOI bbox.
    """
    dates = dates or ["2019.05.02", "2019.05.03", "2019.05.04"]
    out_path = out_path or (RAW_DIR / "chirps_fani_aoi.tif")

    if not force and out_path.exists() and out_path.stat().st_size > 512:
        log.info(f"[CACHE] CHIRPS rainfall raster exists: {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")
        with rasterio.open(out_path) as ds:
            arr = ds.read(1)
            valid = arr[arr >= 0]
            return {
                "dataset": "CHIRPS Daily Precipitation (UCSB/CHG)",
                "source": "https://data.chc.ucsb.edu/products/CHIRPS-2.0/",
                "dates": dates,
                "file": str(out_path),
                "size_mb": round(out_path.stat().st_size / 1e6, 2),
                "crs": str(ds.crs),
                "shape": ds.shape,
                "max_rain_mm": round(float(np.nanmax(valid)), 1) if len(valid) > 0 else 0.0,
                "cached": True,
            }

    daily_rasters = []
    base_url = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05/2019/"

    for d in dates:
        gz_name = f"chirps-v2.0.{d}.tif.gz"
        tif_name = f"chirps-v2.0.{d}.tif"
        gz_path = RAW_DIR / gz_name
        tif_path = RAW_DIR / tif_name

        if not tif_path.exists() or force:
            url = f"{base_url}{gz_name}"
            download_file(url, gz_path)
            with gzip.open(gz_path, "rb") as f_in, open(tif_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            gz_path.unlink(missing_ok=True)
            log.info(f"Extracted {tif_path.name}")

        daily_rasters.append(tif_path)

    log.info("Accumulating multi-day rainfall and cropping to AOI...")
    accum_data: np.ndarray | None = None
    out_meta = None

    for tp in daily_rasters:
        with rasterio.open(tp) as src:
            win = from_bounds(*bbox, transform=src.transform)
            day_data = src.read(1, window=win)
            day_data = np.where(day_data < 0, 0.0, day_data)

            if accum_data is None:
                accum_data = day_data.astype(np.float32)
                out_transform = rasterio.windows.transform(win, src.transform)
                out_meta = src.meta.copy()
                out_meta.update({
                    "height": day_data.shape[0],
                    "width": day_data.shape[1],
                    "transform": out_transform,
                    "compress": "deflate",
                    "nodata": -9999.0,
                })
            else:
                accum_data += day_data.astype(np.float32)

    with rasterio.open(out_path, "w", **out_meta) as dest:
        dest.write(accum_data, 1)

    max_rain = float(np.max(accum_data))
    log.info(f"Saved accumulated CHIRPS rainfall -> {out_path} (Max accum: {max_rain:.1f} mm)")

    return {
        "dataset": "CHIRPS Daily Precipitation (UCSB/CHG)",
        "source": base_url,
        "dates": dates,
        "file": str(out_path),
        "size_mb": round(out_path.stat().st_size / 1e6, 2),
        "crs": str(out_meta["crs"]),
        "shape": accum_data.shape,
        "max_rain_mm": round(max_rain, 1),
        "cached": False,
    }


# ---------------------------------------------------------------------------
# Master Runner & Reporter
# ---------------------------------------------------------------------------
def fetch_all(
    scenario_name: str = "fani_2019",
    force: bool = False,
) -> dict[str, Any]:
    """Execute all downloads and return a summary report."""
    cfg_file = PROJECT_ROOT / "config" / "scenarios" / f"{scenario_name}.yaml"
    with open(cfg_file) as f:
        config = yaml.safe_load(f)

    bbox = config.get("aoi_bbox", [84.9, 19.6, 86.5, 20.7])
    log.info(f"=== Starting Open Data Download for Scenario: {scenario_name} (bbox: {bbox}) ===")

    report: dict[str, Any] = {
        "scenario": scenario_name,
        "aoi_bbox": bbox,
        "datasets": {},
    }

    # 1. Copernicus GLO-30 DEM
    report["datasets"]["dem"] = fetch_copernicus_dem(bbox, force=force)

    # 2. Sentinel-1 RTC VV
    report["datasets"]["sentinel1"] = fetch_sentinel1_rtc(bbox, force=force)

    # 3. JRC Global Surface Water
    report["datasets"]["jrc_gsw"] = fetch_jrc_gsw(bbox, force=force)

    # 4. WorldPop 2019 Population
    report["datasets"]["worldpop"] = fetch_worldpop(bbox, force=force)

    # 5. CHIRPS Rainfall
    report["datasets"]["rainfall"] = fetch_chirps_rainfall(bbox, force=force)

    meta_file = RAW_DIR / "open_data_meta.json"
    with open(meta_file, "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"Saved open data manifest to {meta_file}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download open data assets into data/raw/")
    parser.add_argument("--scenario", default="fani_2019", help="Scenario name")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    args = parser.parse_args()

    rep = fetch_all(scenario_name=args.scenario, force=args.force)
    print("\n--- DOWNLOAD SUMMARY REPORT ---")
    print(json.dumps(rep, indent=2))
