#!/usr/bin/env python3
"""
KhetSense AI — Farmer Registration Service
Handles registration of new farms in Supabase PostGIS from WhatsApp location pins and chat inputs.
"""

import os
import psycopg2
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import re

# Ensure environment variables are loaded
load_dotenv()

# Relative import or direct import
try:
    from .geo_utils import point_to_square_polygon
except ImportError:
    from geo_utils import point_to_square_polygon

try:
    from common.utils import normalize_phone
except ImportError:
    try:
        from khetsense.common.utils import normalize_phone
    except ImportError:
        import re
        def normalize_phone(phone):
            if not phone:
                return ""
            d = re.sub(r"\D", "", str(phone).strip())
            return ("91" + d) if len(d) == 10 and d[0] in "6789" else d


def register_farmer_from_pin(
    farmer_name: str,
    mobile_number: str,
    lat: float,
    lon: float,
    crop_name: str,
    village: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    preferred_language: Optional[str] = "en",
    farm_area_acres: Optional[float] = None,
    side_meters: float = 100.0,
    db_url: Optional[str] = None,
    boundary_source: str = "estimated_from_pin",
    area_source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Registers a new farm into the PostGIS `farms` table using a WhatsApp GPS pin.

    Workflow:
    1. Converts the (lat, lon) pin into a 100m x 100m (or custom area) square polygon (SRID 4326).
    2. Stores the original raw pin in the `pin` column as a Point geometry.
    3. Records provenance in `boundary_source` ('estimated_from_pin') and `area_source` ('farmer_stated' or 'default').
    4. Inserts the record into the Supabase PostgreSQL `farms` table.
    5. Returns the registered farm details including newly assigned `farm_id`.

    Args:
        farmer_name: Name of the farmer
        mobile_number: Farmer's WhatsApp mobile number (e.g., '919876543210')
        lat: Latitude from WhatsApp location attachment
        lon: Longitude from WhatsApp location attachment
        crop_name: Name of the primary crop (e.g., 'Cotton', 'Soybean')
        village: Village name (optional, defaults to None)
        district: District name (optional, defaults to None)
        state: State name (optional, defaults to None)
        preferred_language: 'en', 'mr', or 'hi' (default: 'en')
        farm_area_acres: Declared farm acreage (if provided by farmer)
        side_meters: Buffer box side in meters (default: 100.0 m ≈ 2.47 acres)
        db_url: PostgreSQL connection URL (defaults to os.getenv('DATABASE_URL'))
        boundary_source: Provenance of the boundary (default: 'estimated_from_pin')
        area_source: Provenance of the area ('farmer_stated' or 'default')

    Returns:
        Dictionary containing registration details, farm_id, and polygon metrics.
    """
    if not db_url:
        db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL is not set in environment or arguments.")

    # Normalize phone to Meta standard digits
    mobile_number = normalize_phone(mobile_number)

    # 1. Determine area provenance
    if area_source is None:
        area_source = "farmer_stated" if (farm_area_acres is not None and farm_area_acres > 0) else "default"

    # 2. Convert point to square polygon
    poly_data = point_to_square_polygon(
        lat=lat,
        lon=lon,
        side_meters=side_meters,
        farm_area_acres=farm_area_acres
    )

    final_area_acres = poly_data["area_acres"]
    wkt_polygon = poly_data["wkt"]
    pin_wkt = poly_data.get("pin_wkt", f"POINT({lon} {lat})")

    # 3. Insert into PostGIS `farms` table
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            insert_query = """
                INSERT INTO farms (
                    farmer_name,
                    mobile_number,
                    village,
                    district,
                    state,
                    preferred_language,
                    crop_name,
                    farm_area,
                    farm_area_unit,
                    polygon,
                    pin,
                    boundary_source,
                    area_source
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    ST_GeomFromText(%s, 4326),
                    ST_GeomFromText(%s, 4326),
                    %s,
                    %s
                )
                RETURNING 
                    id, 
                    farmer_name, 
                    mobile_number, 
                    crop_name, 
                    farm_area, 
                    farm_area_unit,
                    ST_AsGeoJSON(polygon),
                    ST_IsValid(polygon),
                    ST_X(ST_Centroid(polygon)) AS centroid_lon,
                    ST_Y(ST_Centroid(polygon)) AS centroid_lat,
                    boundary_source,
                    area_source,
                    created_at;
            """
            cur.execute(
                insert_query,
                (
                    farmer_name,
                    mobile_number,
                    village,
                    district,
                    state,
                    preferred_language,
                    crop_name,
                    final_area_acres,
                    "acres",
                    wkt_polygon,
                    pin_wkt,
                    boundary_source,
                    area_source,
                )
            )
            row = cur.fetchone()
            conn.commit()

            (
                farm_id, f_name, f_mobile, f_crop, f_area, f_unit,
                geojson_str, is_valid, c_lon, c_lat,
                b_source, a_source, created_at
            ) = row

            return {
                "success": True,
                "farm_id": farm_id,
                "farmer_name": f_name,
                "mobile_number": f_mobile,
                "crop_name": f_crop,
                "farm_area": f_area,
                "farm_area_unit": f_unit,
                "centroid_lat": c_lat,
                "centroid_lon": c_lon,
                "pin_lat": lat,
                "pin_lon": lon,
                "is_valid": is_valid,
                "wkt": wkt_polygon,
                "pin_wkt": pin_wkt,
                "boundary_source": b_source,
                "area_source": a_source,
                "created_at": str(created_at),
                "message": (
                    f"Farm successfully registered for {f_name} (ID: {farm_id}). "
                    f"Generated {side_meters:.0f}m x {side_meters:.0f}m polygon ({f_area:.2f} {f_unit}, source: {a_source}) "
                    f"centered at Lat {c_lat:.5f}, Lon {c_lon:.5f}."
                )
            }
    finally:
        conn.close()
