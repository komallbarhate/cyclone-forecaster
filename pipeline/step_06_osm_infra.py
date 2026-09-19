"""
Step 06 — OSM Critical Infrastructure Extraction (real data, no padding)
=========================================================================
Queries the public Overpass API for critical infrastructure within the AOI:
  - Power substations / transformers  (power=substation|transformer)
  - Hospitals and clinics             (amenity=hospital|clinic|health_post|doctors)
  - Emergency shelters and schools    (amenity=school|community_centre|shelter)
  - Arterial roads: trunk, primary, secondary only (Amendment 7)

Data source: OpenStreetMap contributors via Overpass API
  https://overpass-api.de / https://lz4.overpass-api.de / https://z.overpass-api.de
  License: ODbL 1.0  https://www.openstreetmap.org/copyright

HARD RULE: This step will FAIL if Overpass returns zero elements, unless the
  --allow-synthetic flag is passed. No padding, no fallback catalog.

Produces:
  - data/raw/osm_raw.json          (raw Overpass JSON response, cached)
  - data/processed/infra.geojson  (points: substations, hospitals, shelters)
  - data/processed/roads.geojson  (linestrings: arterial road segments)
  - data/processed/infra_meta.json (counts, road_km, source, OSM timestamp)

Usage:
    python -m pipeline.step_06_osm_infra [--scenario fani_2019] [--force]
    python -m pipeline.step_06_osm_infra --allow-synthetic   # only for offline testing
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import yaml

from pipeline.utils.geo import feature_collection, point_feature, linestring_feature
from pipeline.utils.logger import get_logger

log = get_logger(__name__)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]

# Overpass query timeout (seconds) — must match [timeout:NN] in query string
OVERPASS_TIMEOUT = 60
REQUEST_TIMEOUT = 90  # HTTP socket timeout


def load_scenario(scenario_name: str) -> dict[str, Any]:
    cfg_path = PROJECT_ROOT / "config" / "scenarios" / f"{scenario_name}.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def build_overpass_query(bbox: list[float]) -> str:
    """
    Overpass QL query for power, medical, shelter, and arterial road features.
    bbox: [lon_min, lat_min, lon_max, lat_max] — Overpass order: (S,W,N,E).
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    south, west, north, east = lat_min, lon_min, lat_max, lon_max
    return f"""[out:json][timeout:{OVERPASS_TIMEOUT}];
(
  node["power"~"^(substation|transformer)$"]({south},{west},{north},{east});
  way["power"~"^(substation|transformer)$"]({south},{west},{north},{east});
  node["amenity"~"^(hospital|clinic|health_post|doctors)$"]({south},{west},{north},{east});
  way["amenity"~"^(hospital|clinic|health_post|doctors)$"]({south},{west},{north},{east});
  node["amenity"~"^(school|community_centre|shelter)$"]({south},{west},{north},{east});
  way["amenity"~"^(school|community_centre|shelter)$"]({south},{west},{north},{east});
  way["highway"~"^(trunk|primary|secondary)$"]({south},{west},{north},{east});
);
out body center qt;
"""


def fetch_from_overpass(query: str) -> dict[str, Any] | None:
    """Try each Overpass mirror in order; return JSON or None on failure."""
    for url in OVERPASS_URLS:
        try:
            log.info(f"  Querying Overpass: {url}")
            resp = requests.post(
                url,
                data={"data": query},
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "CycloneShield-hackathon/1.0 (educational)"},
            )
            if resp.status_code == 200:
                data = resp.json()
                n = len(data.get("elements", []))
                if n > 0:
                    log.info(f"  {url}: {n} elements received")
                    return data
                else:
                    log.warning(f"  {url}: response OK but 0 elements returned")
            else:
                log.warning(f"  {url}: HTTP {resp.status_code}")
        except Exception as exc:
            log.warning(f"  {url}: {exc}")
        time.sleep(1)
    return None


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(max(a, 0)))


def linestring_length_km(coords: list[list[float]]) -> float:
    """Total length of a [lon, lat] coordinate list in km."""
    total = 0.0
    for i in range(len(coords) - 1):
        total += haversine_km(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
    return total


def run(
    scenario: str = "fani_2019",
    force: bool = False,
    allow_synthetic: bool = False,
) -> bool:
    """Run Step 06 OSM infrastructure extraction."""
    infra_out = PROCESSED_DIR / "infra.geojson"
    roads_out = PROCESSED_DIR / "roads.geojson"
    meta_out = PROCESSED_DIR / "infra_meta.json"
    raw_cache = RAW_DIR / "osm_raw.json"

    if not force and infra_out.exists() and roads_out.exists() and meta_out.exists():
        log.info("Infrastructure outputs exist; use --force to regenerate.")
        return True

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    config = load_scenario(scenario)
    bbox = config.get("aoi_bbox", [84.9, 19.6, 86.5, 20.7])
    log.info(f"AOI bbox: {bbox}")

    # --- Fetch from Overpass (or use cached raw response) ---
    osm_data: dict[str, Any] | None = None

    if raw_cache.exists():
        log.info(f"Loading cached OSM raw response from {raw_cache}")
        with open(raw_cache) as f:
            osm_data = json.load(f)
        n = len(osm_data.get("elements", []))
        log.info(f"  Cached: {n} elements")
        if n == 0:
            osm_data = None  # treat as invalid cache

    if osm_data is None:
        log.info("Fetching from Overpass API...")
        query = build_overpass_query(bbox)
        osm_data = fetch_from_overpass(query)
        if osm_data is not None:
            with open(raw_cache, "w") as f:
                json.dump(osm_data, f)
            log.info(f"Saved raw OSM response to {raw_cache}")

    elements = osm_data.get("elements", []) if osm_data else []
    log.info(f"Total OSM elements to process: {len(elements)}")

    if len(elements) == 0:
        if allow_synthetic:
            log.warning(
                "[SYNTHETIC] --allow-synthetic is set: Overpass returned 0 elements. "
                "Writing empty GeoJSONs labelled SYNTHETIC. Do NOT use for real analysis."
            )
            _write_empty(infra_out, roads_out, meta_out, bbox, synthetic=True)
            return True
        else:
            raise RuntimeError(
                "FAIL: Overpass API returned 0 elements for the AOI bbox. "
                "Check your internet connection, try again later (rate limiting), "
                "or pass --allow-synthetic for offline testing (results will be labelled SYNTHETIC)."
            )

    # --- Parse elements ---
    infra_features: list[dict] = []
    road_features: list[dict] = []

    # Tag maps
    POWER_TAGS = {"substation", "transformer"}
    HOSPITAL_TAGS = {"hospital", "clinic", "health_post", "doctors"}
    SHELTER_TAGS = {"school", "community_centre", "shelter"}
    ROAD_TAGS = {"trunk", "primary", "secondary"}

    for el in elements:
        tags = el.get("tags", {})
        etype = el.get("type")

        # --- Road ways ---
        hw = tags.get("highway", "")
        if etype == "way" and hw in ROAD_TAGS:
            # Overpass `out body center qt` returns geometry for ways only if
            # we add `>;` — we used `out body center qt` which gives center but
            # not node geometry for ways. Use the center lon/lat as a point if
            # no geometry, otherwise skip (road geometry needs `>;out geom;`).
            # We rebuild the query to include geometry:
            pass  # handled below in road-geometry requery

    DISTRICT_CENTROIDS = {
        "Puri": (19.81, 85.83),
        "Khordha": (20.18, 85.62),
        "Jagatsinghpur": (20.27, 86.17),
        "Kendrapara": (20.50, 86.42),
        "Cuttack": (20.46, 85.88),
    }

    def assign_district(lat: float, lon: float, tags: dict[str, Any]) -> str:
        for key in ("district", "addr:district", "is_in:district", "is_in:state_district"):
            val = tags.get(key)
            if val in DISTRICT_CENTROIDS:
                return val
        return min(
            DISTRICT_CENTROIDS.keys(),
            key=lambda d: haversine_km(lon, lat, DISTRICT_CENTROIDS[d][1], DISTRICT_CENTROIDS[d][0]),
        )

    for el in elements:
        tags = el.get("tags", {})
        etype = el.get("type")

        # --- Power infrastructure (nodes and way centres) ---
        pwr = tags.get("power", "")
        if pwr in POWER_TAGS:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if lat is not None and lon is not None:
                category = "substation" if pwr == "substation" else "transformer"
                infra_features.append(point_feature(
                    lon=lon, lat=lat,
                    properties={
                        "osm_id": f"{etype}_{el['id']}",
                        "name": tags.get("name", f"OSM {pwr.title()} {el['id']}"),
                        "type": "substation",
                        "category": category,
                        "power": pwr,
                        "voltage": tags.get("voltage", ""),
                        "operator": tags.get("operator", ""),
                        "district": assign_district(lat, lon, tags),
                        "source": "OpenStreetMap",
                    },
                ))

        # --- Medical facilities (nodes and way centres) ---
        amenity = tags.get("amenity", "")
        if amenity in HOSPITAL_TAGS:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if lat is not None and lon is not None:
                category = "hospital" if amenity == "hospital" else ("clinic" if amenity == "clinic" else amenity)
                infra_features.append(point_feature(
                    lon=lon, lat=lat,
                    properties={
                        "osm_id": f"{etype}_{el['id']}",
                        "name": tags.get("name", f"OSM {amenity.title()} {el['id']}"),
                        "type": "hospital",
                        "category": category,
                        "amenity": amenity,
                        "beds": tags.get("capacity", tags.get("beds", "")),
                        "operator": tags.get("operator", ""),
                        "district": assign_district(lat, lon, tags),
                        "source": "OpenStreetMap",
                    },
                ))

        # --- Shelters / schools ---
        if amenity in SHELTER_TAGS:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if lat is not None and lon is not None:
                category = "shelter" if amenity == "shelter" else ("community_centre" if amenity == "community_centre" else "school")
                infra_features.append(point_feature(
                    lon=lon, lat=lat,
                    properties={
                        "osm_id": f"{etype}_{el['id']}",
                        "name": tags.get("name", f"OSM {amenity.title()} {el['id']}"),
                        "type": "shelter",
                        "category": category,
                        "amenity": amenity,
                        "capacity": tags.get("capacity", ""),
                        "operator": tags.get("operator", ""),
                        "district": assign_district(lat, lon, tags),
                        "source": "OpenStreetMap",
                    },
                ))

    # For roads we need geometry — check cache or re-fetch with `out geom;`
    roads_raw_cache = RAW_DIR / "osm_roads_raw.json"
    road_data: dict[str, Any] | None = None
    total_road_km = 0.0

    if roads_raw_cache.exists():
        log.info(f"Loading cached road raw response from {roads_raw_cache}")
        with open(roads_raw_cache) as f:
            road_data = json.load(f)
    elif roads_out.exists():
        log.info(f"Re-using verified road network from {roads_out}")
        with open(roads_out) as f:
            roads_existing = json.load(f)
            road_features = roads_existing.get("features", [])
            total_road_km = sum(f.get("properties", {}).get("length_km", 0.0) for f in road_features)
    else:
        log.info("Fetching road geometry (Overpass out geom)...")
        road_data = _fetch_roads_with_geometry(bbox)
        if road_data:
            with open(roads_raw_cache, "w") as f:
                json.dump(road_data, f)

    if road_data:
        for el in road_data.get("elements", []):
            tags = el.get("tags", {})
            hw = tags.get("highway", "")
            if hw not in ROAD_TAGS:
                continue
            geom = el.get("geometry", [])
            if len(geom) < 2:
                continue
            coords = [[pt["lon"], pt["lat"]] for pt in geom]
            seg_km = linestring_length_km(coords)
            total_road_km += seg_km
            road_features.append(linestring_feature(
                coords,
                properties={
                    "osm_id": f"way_{el['id']}",
                    "name": tags.get("name", tags.get("ref", f"OSM way {el['id']}")),
                    "highway": hw,
                    "ref": tags.get("ref", ""),
                    "lanes": tags.get("lanes", ""),
                    "length_km": round(seg_km, 3),
                    "source": "OpenStreetMap",
                },
            ))

    # --- Summary & Counts ---
    n_substations = sum(1 for f in infra_features if f["properties"].get("category") == "substation")
    n_transformers = sum(1 for f in infra_features if f["properties"].get("category") == "transformer")
    n_hospitals = sum(1 for f in infra_features if f["properties"].get("category") == "hospital")
    n_clinics = sum(1 for f in infra_features if f["properties"].get("category") in {"clinic", "health_post", "doctors"})
    n_shelters = sum(1 for f in infra_features if f["properties"].get("category") == "shelter")
    n_schools = sum(1 for f in infra_features if f["properties"].get("category") in {"school", "community_centre"})
    n_roads = len(road_features)

    log.info(
        f"Parsed: {n_substations} substations, {n_transformers} transformers, "
        f"{n_hospitals} hospitals, {n_clinics} clinics/health posts, "
        f"{n_shelters} shelters, {n_schools} schools/centres, {n_roads} road segments "
        f"({total_road_km:.1f} km total)"
    )

    # --- Write outputs ---
    infra_fc = feature_collection(infra_features)
    with open(infra_out, "w") as f:
        json.dump(infra_fc, f)
    log.info(f"Saved {len(infra_features)} infra points -> {infra_out}")

    roads_fc = feature_collection(road_features)
    with open(roads_out, "w") as f:
        json.dump(roads_fc, f)
    log.info(f"Saved {n_roads} road segments -> {roads_out}")

    osm_ts = osm_data.get("osm3s", {}).get("timestamp_osm_base", "unknown")
    meta = {
        "source": "OpenStreetMap contributors via Overpass API",
        "license": "ODbL 1.0 — https://www.openstreetmap.org/copyright",
        "overpass_timestamp_osm_base": osm_ts,
        "query_bbox_lonlat": bbox,
        "infra_tags_queried": {
            "power": ["substation", "transformer"],
            "amenity_hospital": ["hospital", "clinic", "health_post", "doctors"],
            "amenity_shelter": ["school", "community_centre", "shelter"],
            "highway": ["trunk", "primary", "secondary"],
        },
        "counts": {
            "substations": n_substations,
            "transformers": n_transformers,
            "hospitals": n_hospitals,
            "clinics_health_posts": n_clinics,
            "shelters": n_shelters,
            "schools_community_centres": n_schools,
            "substations_and_transformers": n_substations + n_transformers,
            "hospitals_and_clinics": n_hospitals + n_clinics,
            "shelters_and_schools": n_shelters + n_schools,
            "road_segments": n_roads,
            "total_road_km": round(total_road_km, 2),
            "total_infra_points": len(infra_features),
        },
        "substations": n_substations,
        "transformers": n_transformers,
        "hospitals": n_hospitals,
        "clinics": n_clinics,
        "shelters": n_shelters + n_schools,
        "arterial_roads": n_roads,
        "synthetic": False,
        "scenario": scenario,
    }
    with open(meta_out, "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Saved infra metadata -> {meta_out}")

    return True


def _fetch_roads_with_geometry(bbox: list[float]) -> dict[str, Any] | None:
    """Separate Overpass query for road ways with full node geometry."""
    lon_min, lat_min, lon_max, lat_max = bbox
    query = f"""[out:json][timeout:{OVERPASS_TIMEOUT}];
(
  way["highway"~"^(trunk|primary|secondary)$"]({lat_min},{lon_min},{lat_max},{lon_max});
);
out geom qt;
"""
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(
                url,
                data={"data": query},
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "CycloneShield-hackathon/1.0 (educational)"},
            )
            if resp.status_code == 200:
                data = resp.json()
                n = len(data.get("elements", []))
                if n > 0:
                    log.info(f"  Road geometry: {n} ways from {url}")
                    return data
        except Exception as exc:
            log.warning(f"  Road geometry fetch failed at {url}: {exc}")
        time.sleep(1)
    return None


def _write_empty(
    infra_out: Path,
    roads_out: Path,
    meta_out: Path,
    bbox: list[float],
    synthetic: bool = True,
) -> None:
    """Write empty GeoJSONs labelled SYNTHETIC for offline testing."""
    label = "SYNTHETIC — no real data; --allow-synthetic was passed"
    for path in (infra_out, roads_out):
        with open(path, "w") as f:
            json.dump({"type": "FeatureCollection", "features": [], "_synthetic": label}, f)
    meta = {
        "source": label,
        "query_bbox_lonlat": bbox,
        "counts": {
            "substations": 0, "hospitals_clinics": 0, "shelters_schools": 0,
            "road_segments": 0, "total_road_km": 0.0, "total_infra_points": 0,
        },
        "synthetic": True,
    }
    with open(meta_out, "w") as f:
        json.dump(meta, f, indent=2)


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Step 06: OSM Infrastructure Extract")
    parser.add_argument("--scenario", default="fani_2019")
    parser.add_argument("--force", action="store_true", help="Delete cache and re-fetch")
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="If Overpass returns 0 elements, write empty SYNTHETIC outputs instead of failing",
    )
    args = parser.parse_args()

    ok = run(
        scenario=args.scenario,
        force=args.force,
        allow_synthetic=args.allow_synthetic,
    )
    sys.exit(0 if ok else 1)
