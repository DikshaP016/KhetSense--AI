#!/usr/bin/env python3
"""
KhetSense AI — Geodesic & Spatial Utility Functions
Converts farmer-shared GPS location pins into standardized PostGIS polygons (SRID 4326).
"""

import math
import json
from typing import Dict, Any, Optional, List


def point_to_square_polygon(
    lat: float,
    lon: float,
    side_meters: float = 100.0,
    farm_area_acres: Optional[float] = None
) -> Dict[str, Any]:
    """
    Converts a single (lat, lon) GPS point into a square polygon boundary centered on that point.

    Agricultural Rationale for Defaults:
    - Default side_meters = 100.0 m produces a 100m x 100m square (10,000 m^2 = 1.0 hectare ≈ 2.47 acres).
    - According to the Agriculture Census of India, the average smallholder landholding is ~1.08 ha (~2.5 acres).
    - If farm_area_acres is explicitly known/provided, side_meters is dynamically calculated as:
      side_meters = sqrt(farm_area_acres * 4046.8564)

    Geodesic Formulas:
    - 1 degree of latitude ≈ 111,320 meters
    - 1 degree of longitude ≈ 111,320 * cos(latitude) meters
    - Generates a closed ring of 5 coordinates in EPSG:4326 [longitude, latitude] order (RFC 7946).

    Args:
        lat: Latitude of the center pin (decimal degrees)
        lon: Longitude of the center pin (decimal degrees)
        side_meters: Length of each side of the square in meters (default: 100.0 m)
        farm_area_acres: Optional explicit farm area in acres to calculate custom square size

    Returns:
        dict containing:
            - 'wkt': Well-Known Text representation for ST_GeomFromText(wkt, 4326)
            - 'geojson': GeoJSON geometry dictionary
            - 'coordinates': List of [lon, lat] pairs
            - 'ee_coords': Format ready for ee.Geometry.Polygon([ee_coords])
            - 'centroid': [lon, lat]
            - 'area_sq_m': Area in square meters
            - 'area_acres': Area in acres
            - 'side_meters': Square dimension used
    """
    # If explicit acreage is provided, scale square dimensions proportionally
    if farm_area_acres is not None and farm_area_acres > 0:
        area_sq_m = farm_area_acres * 4046.8564
        side_meters = math.sqrt(area_sq_m)
    else:
        area_sq_m = side_meters * side_meters
        farm_area_acres = area_sq_m / 4046.8564

    half_side = side_meters / 2.0

    # Geodesic delta in degrees on WGS 84 ellipsoid
    # Meridional radius of curvature (M) for true latitude degree length
    # Semi-major axis a = 6,378,137.0 m, first eccentricity squared e^2 ≈ 0.00669437999014
    rad_lat = math.radians(lat)
    sin_lat = math.sin(rad_lat)
    e2 = 0.00669437999014
    M = 6378137.0 * (1 - e2) / ((1 - e2 * (sin_lat ** 2)) ** 1.5)
    meters_per_deg_lat = (math.pi / 180.0) * M

    # Prime vertical radius of curvature (N) for true parallel/longitude degree length
    N = 6378137.0 / math.sqrt(1 - e2 * (sin_lat ** 2))
    meters_per_deg_lon = (math.pi / 180.0) * N * math.cos(rad_lat)

    d_lat = half_side / meters_per_deg_lat
    d_lon = half_side / meters_per_deg_lon

    min_lat = round(lat - d_lat, 6)
    max_lat = round(lat + d_lat, 6)
    min_lon = round(lon - d_lon, 6)
    max_lon = round(lon + d_lon, 6)

    # Counter-clockwise closed ring: SW -> SE -> NE -> NW -> SW
    # PostGIS and GeoJSON expect [lon, lat] pairs (X = longitude, Y = latitude)
    ring_coords = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]

    wkt = (
        f"POLYGON(({min_lon} {min_lat}, "
        f"{max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, "
        f"{min_lon} {max_lat}, "
        f"{min_lon} {min_lat}))"
    )

    geojson_dict = {
        "type": "Polygon",
        "coordinates": [ring_coords]
    }

    pin_wkt = f"POINT({lon} {lat})"
    pin_geojson = {
        "type": "Point",
        "coordinates": [lon, lat]
    }

    return {
        "wkt": wkt,
        "geojson": geojson_dict,
        "coordinates": ring_coords,
        "ee_coords": ring_coords,
        "pin_wkt": pin_wkt,
        "pin_geojson": pin_geojson,
        "pin_lat": lat,
        "pin_lon": lon,
        "centroid_lat": lat,
        "centroid_lon": lon,
        "min_lat": min_lat,
        "max_lat": max_lat,
        "min_lon": min_lon,
        "max_lon": max_lon,
        "area_sq_m": round(area_sq_m, 2),
        "area_acres": round(farm_area_acres, 2),
        "side_meters": round(side_meters, 2),
    }
