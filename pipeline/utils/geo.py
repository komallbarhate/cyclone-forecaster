"""
Geospatial utilities for the CycloneShield pipeline.

Provides reusable functions for coordinate transforms, GeoJSON
construction, grid generation, and spatial operations that are
used across multiple pipeline steps.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import unary_union


# ---- Constants ----------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0
KM_PER_DEG_LAT = 111.32  # approximate, varies slightly by latitude


# ---- Distance & Bearing -------------------------------------------------------


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute great-circle distance in kilometres between two lat/lon points.

    Parameters
    ----------
    lat1, lon1 : float
        First point (degrees).
    lat2, lon2 : float
        Second point (degrees).

    Returns
    -------
    float
        Distance in kilometres.
    """
    r = EARTH_RADIUS_KM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute forward azimuth (degrees, 0=N, 90=E) from point 1 to point 2.

    Parameters
    ----------
    lat1, lon1 : float
        Origin point (degrees).
    lat2, lon2 : float
        Destination point (degrees).

    Returns
    -------
    float
        Bearing in degrees [0, 360).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination_point(lat: float, lon: float, bearing_deg_val: float, dist_km: float) -> tuple[float, float]:
    """
    Return the lat/lon of a point ``dist_km`` away from (lat, lon) along ``bearing_deg_val``.

    Parameters
    ----------
    lat, lon : float
        Starting point (degrees).
    bearing_deg_val : float
        Azimuth in degrees.
    dist_km : float
        Distance in kilometres.

    Returns
    -------
    tuple[float, float]
        (latitude, longitude) of destination point.
    """
    r = EARTH_RADIUS_KM
    d = dist_km / r
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    theta = math.radians(bearing_deg_val)
    phi2 = math.asin(
        math.sin(phi1) * math.cos(d) + math.cos(phi1) * math.sin(d) * math.cos(theta)
    )
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(d) * math.cos(phi1),
        math.cos(d) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lam2)


# ---- Grid generation ----------------------------------------------------------


def make_grid(
    bbox: list[float],
    resolution_m: float = 500,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Create a regular lat/lon grid over the given bounding box.

    Parameters
    ----------
    bbox : list[float]
        [lon_min, lat_min, lon_max, lat_max] in degrees.
    resolution_m : float
        Grid spacing in metres.

    Returns
    -------
    lats, lons : np.ndarray
        2-D arrays of cell centre latitudes and longitudes.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    # Approx degrees per cell
    dlat = resolution_m / (KM_PER_DEG_LAT * 1000)
    centre_lat = (lat_min + lat_max) / 2
    dlon = resolution_m / (KM_PER_DEG_LAT * 1000 * math.cos(math.radians(centre_lat)))

    lat_coords = np.arange(lat_min + dlat / 2, lat_max, dlat)
    lon_coords = np.arange(lon_min + dlon / 2, lon_max, dlon)
    return np.meshgrid(lat_coords, lon_coords, indexing="ij")


# ---- GeoJSON helpers ----------------------------------------------------------


def point_feature(lat: float, lon: float, properties: dict[str, Any] | None = None) -> dict:
    """Return a GeoJSON Point Feature."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties or {},
    }


def feature_collection(features: list[dict]) -> dict:
    """Return a GeoJSON FeatureCollection."""
    return {"type": "FeatureCollection", "features": features}


def bbox_polygon(bbox: list[float]) -> Polygon:
    """Return a shapely Polygon for the given bbox [lon_min, lat_min, lon_max, lat_max]."""
    lon_min, lat_min, lon_max, lat_max = bbox
    return Polygon([
        (lon_min, lat_min), (lon_max, lat_min),
        (lon_max, lat_max), (lon_min, lat_max),
        (lon_min, lat_min),
    ])


def circle_polygon(lat: float, lon: float, radius_km: float, n_pts: int = 36) -> Polygon:
    """
    Return a shapely Polygon approximating a circle around (lat, lon).

    Parameters
    ----------
    lat, lon : float
        Centre of circle.
    radius_km : float
        Radius in kilometres.
    n_pts : int
        Number of polygon vertices (higher = smoother).

    Returns
    -------
    shapely.geometry.Polygon
    """
    coords = []
    for i in range(n_pts):
        bearing = 360 * i / n_pts
        pt_lat, pt_lon = destination_point(lat, lon, bearing, radius_km)
        coords.append((pt_lon, pt_lat))
    coords.append(coords[0])
    return Polygon(coords)


def merge_polygons(polygons: list[Polygon]) -> Polygon | None:
    """Return the union of a list of shapely Polygons, or None if empty."""
    if not polygons:
        return None
    return unary_union(polygons)
