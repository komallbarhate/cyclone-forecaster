"""
Step 01 — Fetch IBTrACS Track
================================
Downloads the North Indian Ocean IBTrACS CSV, filters for Cyclone Fani
(SID 2019153N11090), and produces:
  - data/raw/ibtracs_ni.csv              (full NI basin CSV)
  - data/processed/track_raw.geojson     (raw 3-hourly observations)
  - data/processed/track_hourly.geojson  (1-hourly interpolated track)
  - data/processed/track_meta.json       (storm metadata)

Usage:
    python pipeline/01_fetch_track.py [--scenario fani_2019] [--force]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml
from scipy.interpolate import CubicSpline
from shapely.geometry import LineString

from pipeline.utils.cache import load_json_cache, save_json_cache
from pipeline.utils.geo import feature_collection, point_feature
from pipeline.utils.logger import get_logger

log = get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# IBTrACS column name mappings
# Reference: https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r00/documentation/
IBTRACS_COLS = {
    "SID": "SID",
    "SEASON": "SEASON",
    "NUMBER": "NUMBER",
    "BASIN": "BASIN",
    "NAME": "NAME",
    "ISO_TIME": "ISO_TIME",
    "NATURE": "NATURE",
    "LAT": "LAT",
    "LON": "LON",
    "WMO_WIND": "WMO_WIND",       # 10-min sustained wind (kt); from WMO agency
    "WMO_PRES": "WMO_PRES",       # MSLP (hPa)
    "TRACK_TYPE": "TRACK_TYPE",
    "USA_WIND": "USA_WIND",        # 1-min sustained wind (kt); from USA (JTWC)
    "USA_PRES": "USA_PRES",
    "USA_RMW": "USA_RMW",          # radius of maximum winds (nm)
    "IMD_WIND": "IMD_WIND",        # IMD 3-min wind
    "IMD_PRES": "IMD_PRES",
}

# Willoughby & Rahn (2004) RMW estimation coefficients
# RMW(nm) = exp(3.015 - 6.291e-5 * (ΔP)^2 + 0.0169 * phi)
# where ΔP = Penv - Pc, phi = abs(latitude)
# This formula is used when USA_RMW is missing.
PENV_HPA = 1010.0  # environmental pressure (hPa)


def load_scenario(scenario: str) -> dict:
    """Load scenario YAML configuration."""
    config_path = PROJECT_ROOT / "config" / "scenarios" / f"{scenario}.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def download_ibtracs(url: str, dest: Path, force: bool = False) -> Path:
    """
    Download IBTrACS CSV from NOAA if not cached.

    Parameters
    ----------
    url : str
        IBTrACS download URL.
    dest : Path
        Destination file path.
    force : bool
        Re-download even if file exists.

    Returns
    -------
    Path
        Path to the downloaded file.
    """
    if dest.exists() and not force:
        log.info(f"IBTrACS CSV already cached at {dest}")
        return dest

    log.info(f"Downloading IBTrACS from {url}")
    log.info("This may take 1-2 minutes (~30MB)...")
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    log.info(f"Downloaded IBTrACS to {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def parse_ibtracs_storm(csv_path: Path, storm_sid: str) -> pd.DataFrame:
    """
    Parse IBTrACS CSV and return rows for a single storm.

    IBTrACS CSVs have two header rows: the first is the column names,
    the second is units. We skip the units row.

    Parameters
    ----------
    csv_path : Path
        Path to the IBTrACS CSV file.
    storm_sid : str
        Storm SID to extract (e.g. "2019153N11090").

    Returns
    -------
    pd.DataFrame
        Filtered dataframe for the requested storm.
    """
    log.info(f"Parsing IBTrACS CSV for storm {storm_sid}...")
    # Read with two header rows; second row is units
    df = pd.read_csv(csv_path, skiprows=[1], na_values=[" ", ""], low_memory=False)
    df.columns = df.columns.str.strip()

    # Filter for storm
    storm_df = df[df["SID"].str.strip() == storm_sid].copy()
    if storm_df.empty:
        raise ValueError(
            f"Storm SID '{storm_sid}' not found in {csv_path}. "
            "Check the IBTrACS file and storm ID."
        )

    log.info(f"Found {len(storm_df)} observations for {storm_sid}")
    return storm_df


def clean_track_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and standardize the raw track dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Raw storm dataframe from IBTrACS.

    Returns
    -------
    pd.DataFrame
        Cleaned dataframe with standardized column names and types.
    """
    df = df.copy()

    # Parse ISO_TIME to datetime
    df["time_utc"] = pd.to_datetime(df["ISO_TIME"].str.strip(), utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc"]).sort_values("time_utc").reset_index(drop=True)

    # Lat / Lon
    df["lat"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["lon"] = pd.to_numeric(df["LON"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    # Wind speed: prefer WMO_WIND (10-min), fall back to USA_WIND (1-min × 0.88), then IMD_WIND (3-min × 0.93)
    def get_wind_kt(row: pd.Series) -> float:
        wmo = pd.to_numeric(row.get("WMO_WIND", np.nan), errors="coerce")
        usa = pd.to_numeric(row.get("USA_WIND", np.nan), errors="coerce")
        imd = pd.to_numeric(row.get("IMD_WIND", np.nan), errors="coerce")
        if pd.notna(wmo) and wmo > 0:
            return float(wmo)
        if pd.notna(usa) and usa > 0:
            return float(usa * 0.88)  # 1-min → 10-min (standard conversion)
        if pd.notna(imd) and imd > 0:
            return float(imd * 0.93)  # 3-min → 10-min
        return np.nan

    df["vmax_kt"] = df.apply(get_wind_kt, axis=1)
    df["vmax_kmh"] = df["vmax_kt"] * 1.852

    # MSLP
    def get_pres_hpa(row: pd.Series) -> float:
        wmo = pd.to_numeric(row.get("WMO_PRES", np.nan), errors="coerce")
        usa = pd.to_numeric(row.get("USA_PRES", np.nan), errors="coerce")
        imd = pd.to_numeric(row.get("IMD_PRES", np.nan), errors="coerce")
        for v in [wmo, usa, imd]:
            if pd.notna(v) and 850 < v < 1020:
                return float(v)
        return np.nan

    df["mslp_hpa"] = df.apply(get_pres_hpa, axis=1)

    # RMW (radius of maximum winds) — from USA_RMW (nm), convert to km
    df["rmw_nm"] = pd.to_numeric(df.get("USA_RMW", np.nan), errors="coerce")
    df["rmw_km"] = np.where(
        df["rmw_nm"] > 0,
        df["rmw_nm"] * 1.852,
        np.nan,
    )

    # Fill missing RMW using Willoughby & Rahn (2004) empirical formula
    df["rmw_km"] = df.apply(
        lambda r: estimate_rmw_km(r["lat"], r["mslp_hpa"]) if np.isnan(r["rmw_km"]) else r["rmw_km"],
        axis=1,
    )

    # Storm name
    df["name"] = df["NAME"].str.strip() if "NAME" in df.columns else "UNKNOWN"

    # Keep only useful columns
    cols = ["time_utc", "lat", "lon", "vmax_kt", "vmax_kmh", "mslp_hpa", "rmw_km", "name"]
    return df[[c for c in cols if c in df.columns]].reset_index(drop=True)


def estimate_rmw_km(lat: float, mslp_hpa: float) -> float:
    """
    Estimate radius of maximum winds using Willoughby & Rahn (2004).

    Parameters
    ----------
    lat : float
        Latitude of storm centre.
    mslp_hpa : float
        Central pressure in hPa.

    Returns
    -------
    float
        Estimated RMW in kilometres.

    Notes
    -----
    Willoughby, H.E., and M.E. Rahn (2004). Parametric representation of the
    primary hurricane vortex. Part I. *Mon. Wea. Rev.*, 132, 3033–3048.

    This is an ASSUMPTION when direct RMW measurements are unavailable.
    """
    if np.isnan(mslp_hpa) or np.isnan(lat):
        return 35.0  # fallback: 35 km (scenario YAML value for Fani)
    dp = max(PENV_HPA - mslp_hpa, 0)
    phi = abs(lat)
    rmw_nm = np.exp(3.015 - 6.291e-5 * dp**2 + 0.0169 * phi)
    return float(rmw_nm * 1.852)


def interpolate_track(df: pd.DataFrame, step_hours: int = 1) -> pd.DataFrame:
    """
    Interpolate a 3-hourly track to hourly resolution using cubic splines.

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned track dataframe with time_utc, lat, lon, vmax_kt, mslp_hpa, rmw_km.
    step_hours : int
        Target time step in hours.

    Returns
    -------
    pd.DataFrame
        Interpolated dataframe at 1-hourly (or step_hours) resolution.
    """
    log.info(f"Interpolating track from {len(df)} obs to {step_hours}-hourly resolution...")

    # Convert times to numeric (hours since first obs)
    t0 = df["time_utc"].iloc[0]
    t_hours = np.array([(t - t0).total_seconds() / 3600 for t in df["time_utc"]])

    # Target hourly timestamps
    t_new = np.arange(t_hours[0], t_hours[-1] + step_hours, step_hours)

    # Cubic splines for each variable
    cs_lat = CubicSpline(t_hours, df["lat"].values)
    cs_lon = CubicSpline(t_hours, df["lon"].values)
    cs_vmax = CubicSpline(t_hours, df["vmax_kt"].fillna(df["vmax_kt"].mean()).values)
    cs_mslp = CubicSpline(t_hours, df["mslp_hpa"].fillna(df["mslp_hpa"].mean()).values)
    cs_rmw = CubicSpline(t_hours, df["rmw_km"].fillna(df["rmw_km"].mean()).values)

    new_times = [t0 + pd.Timedelta(hours=h) for h in t_new]

    df_hourly = pd.DataFrame({
        "time_utc": new_times,
        "lat": cs_lat(t_new).clip(-90, 90),
        "lon": cs_lon(t_new),
        "vmax_kt": cs_vmax(t_new).clip(0, 200),
        "vmax_kmh": cs_vmax(t_new).clip(0, 200) * 1.852,
        "mslp_hpa": cs_mslp(t_new).clip(850, 1020),
        "rmw_km": cs_rmw(t_new).clip(10, 200),
        "hours_since_start": t_new,
    })

    log.info(f"Interpolated to {len(df_hourly)} hourly steps")
    return df_hourly


def compute_translation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add translation speed (km/h) and direction (degrees) columns.

    Parameters
    ----------
    df : pd.DataFrame
        Hourly interpolated track dataframe.

    Returns
    -------
    pd.DataFrame
        Track with added columns: trans_speed_kmh, trans_direction_deg.
    """
    from pipeline.utils.geo import haversine_km, bearing_deg

    speeds, bearings = [np.nan], [np.nan]
    for i in range(1, len(df)):
        d_km = haversine_km(df["lat"].iloc[i - 1], df["lon"].iloc[i - 1],
                            df["lat"].iloc[i], df["lon"].iloc[i])
        b = bearing_deg(df["lat"].iloc[i - 1], df["lon"].iloc[i - 1],
                        df["lat"].iloc[i], df["lon"].iloc[i])
        speeds.append(d_km)  # km in 1 hour = km/h
        bearings.append(b)

    df = df.copy()
    df["trans_speed_kmh"] = speeds
    df["trans_direction_deg"] = bearings
    # Fill the first NaN by forward-filling
    df["trans_speed_kmh"] = df["trans_speed_kmh"].bfill()
    df["trans_direction_deg"] = df["trans_direction_deg"].bfill()
    return df


def track_to_geojson(df: pd.DataFrame) -> dict:
    """
    Convert track dataframe to GeoJSON FeatureCollection (Point per observation).

    Parameters
    ----------
    df : pd.DataFrame
        Track dataframe.

    Returns
    -------
    dict
        GeoJSON FeatureCollection.
    """
    features = []
    for _, row in df.iterrows():
        props = {
            "time_utc": row["time_utc"].isoformat() if hasattr(row["time_utc"], "isoformat") else str(row["time_utc"]),
            "vmax_kt": round(float(row["vmax_kt"]), 1),
            "vmax_kmh": round(float(row["vmax_kmh"]), 1),
            "mslp_hpa": round(float(row["mslp_hpa"]), 1),
            "rmw_km": round(float(row["rmw_km"]), 1),
            "trans_speed_kmh": round(float(row.get("trans_speed_kmh", 0)), 1),
            "trans_direction_deg": round(float(row.get("trans_direction_deg", 0)), 1),
        }
        # Add hours_relative_to_landfall if landfall time available
        if "hours_to_landfall" in row:
            props["hours_to_landfall"] = round(float(row["hours_to_landfall"]), 1)
        features.append(point_feature(float(row["lat"]), float(row["lon"]), props))

    return feature_collection(features)


def compute_landfall_hours(df: pd.DataFrame, landfall_time: str) -> pd.DataFrame:
    """
    Add hours_to_landfall column (negative = before, positive = after).

    Parameters
    ----------
    df : pd.DataFrame
        Interpolated track dataframe.
    landfall_time : str
        ISO 8601 UTC landfall time string.

    Returns
    -------
    pd.DataFrame
        Track with hours_to_landfall column.
    """
    lf_time = pd.Timestamp(landfall_time, tz="UTC")
    df = df.copy()
    df["hours_to_landfall"] = [
        (t - lf_time).total_seconds() / 3600 for t in df["time_utc"]
    ]
    return df


def run(scenario: str = "fani_2019", force: bool = False) -> bool:
    """
    Run the track fetch step.

    Parameters
    ----------
    scenario : str
        Scenario name.
    force : bool
        Re-run even if outputs exist.

    Returns
    -------
    bool
        True on success.
    """
    config = load_scenario(scenario)
    ibtracs_cfg = config["ibtracs"]
    storm_sid = ibtracs_cfg["storm_sid"]
    landfall_time = config["landfall"]["time_utc"]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    csv_dest = RAW_DIR / "ibtracs_ni.csv"
    hourly_out = PROCESSED_DIR / "track_hourly.geojson"
    raw_out = PROCESSED_DIR / "track_raw.geojson"
    meta_out = PROCESSED_DIR / "track_meta.json"

    if hourly_out.exists() and not force:
        log.info(f"Track already processed at {hourly_out}; use --force to re-run")
        return True

    # 1. Download IBTrACS
    try:
        download_ibtracs(ibtracs_cfg["url"], csv_dest, force=force)
    except Exception as e:
        log.error(f"IBTrACS download failed: {e}")
        log.error("Check your internet connection and the URL in fani_2019.yaml")
        return False

    # 2. Parse storm
    raw_df = parse_ibtracs_storm(csv_dest, storm_sid)

    # 3. Clean
    clean_df = clean_track_df(raw_df)

    # 4. Save raw GeoJSON
    raw_geojson = track_to_geojson(clean_df)
    with open(raw_out, "w") as f:
        json.dump(raw_geojson, f, indent=2)
    log.info(f"Saved raw track: {raw_out} ({len(clean_df)} observations)")

    # 5. Interpolate to hourly
    hourly_df = interpolate_track(clean_df, step_hours=1)
    hourly_df = compute_translation(hourly_df)
    hourly_df = compute_landfall_hours(hourly_df, landfall_time)

    # 6. Save hourly GeoJSON
    hourly_geojson = track_to_geojson(hourly_df)
    with open(hourly_out, "w") as f:
        json.dump(hourly_geojson, f, indent=2)
    log.info(f"Saved hourly track: {hourly_out} ({len(hourly_df)} steps)")

    # 7. Save metadata
    meta = {
        "storm_sid": storm_sid,
        "storm_name": clean_df["name"].iloc[0] if "name" in clean_df.columns else "FANI",
        "basin": config["basin"],
        "raw_obs_count": len(clean_df),
        "hourly_steps": len(hourly_df),
        "start_time_utc": str(hourly_df["time_utc"].iloc[0]),
        "end_time_utc": str(hourly_df["time_utc"].iloc[-1]),
        "landfall_time_utc": landfall_time,
        "peak_vmax_kmh": round(float(clean_df["vmax_kmh"].max()), 1),
        "min_mslp_hpa": round(float(clean_df["mslp_hpa"].min()), 1),
        "data_source": "NOAA IBTrACS v04r00",
        "citation": "Knapp et al. (2010) BAMS https://doi.org/10.1175/2009BAMS2755.1",
    }
    with open(meta_out, "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Saved track metadata: {meta_out}")
    log.info(f"  Peak wind: {meta['peak_vmax_kmh']} km/h | Min MSLP: {meta['min_mslp_hpa']} hPa")

    return True


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Step 01: Fetch IBTrACS Track")
    parser.add_argument("--scenario", default="fani_2019", help="Scenario name")
    parser.add_argument("--force", action="store_true", help="Re-run even if outputs exist")
    args = parser.parse_args()

    ok = run(scenario=args.scenario, force=args.force)
    import sys
    sys.exit(0 if ok else 1)
