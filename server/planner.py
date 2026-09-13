"""
Garuda AgroGod - Precision VRT Flight Path Planner & MAVLink Mission Generator
Ponytail: Pure Python stdlib math for Boustrophedon (lawnmower) flight paths and MAVLink QGC WPL 110 export.
Zero heavy GIS/GDAL dependencies. Runs anywhere.
"""

import math
from typing import List, Tuple, Dict, Any

# Point in polygon check using ray casting algorithm (stdlib only)
def point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    num = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, num + 1):
        p2x, p2y = polygon[i % num]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def calculate_spray_drift(wind_speed_kmh: float, flight_alt_m: float = 3.0, droplet_size_microns: int = 250) -> Dict[str, Any]:
    """Estimates physical downwind spray drift buffer zone in meters.
    Higher wind speed and higher altitude increase drift risk.
    """
    wind_m_s = wind_speed_kmh / 3.6
    # Empirical ag-drift approximation for medium nozzles (250um)
    drift_distance_m = round((wind_m_s * flight_alt_m * 0.45) * (300.0 / max(droplet_size_microns, 100)), 2)
    
    if wind_speed_kmh > 20:
        safety_status = "CRITICAL_DRIFT_HAZARD"
        can_spray = False
    elif wind_speed_kmh > 12:
        safety_status = "CAUTION_BUFFER_REQUIRED"
        can_spray = True
    else:
        safety_status = "OPTIMAL_CONDITIONS"
        can_spray = True

    return {
        "wind_speed_kmh": wind_speed_kmh,
        "flight_alt_m": flight_alt_m,
        "recommended_buffer_m": drift_distance_m,
        "safety_status": safety_status,
        "can_spray": can_spray
    }

def generate_vrt_flight_mission(
    polygon_coords: List[Tuple[float, float]],
    swath_width_m: float = 4.0,
    cruise_alt_m: float = 12.0,
    stress_zones: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generates an autonomous Boustrophedon (lawnmower) survey grid over a field polygon.
    Marks waypoints with VRT spray commands (SPRAY_ON / SPRAY_OFF) based on NDVI stress zones.
    """
    if len(polygon_coords) < 3:
        raise ValueError("Polygon must have at least 3 vertices")

    lats = [p[0] for p in polygon_coords]
    lons = [p[1] for p in polygon_coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # Approximate 1 degree latitude ~ 111,000 meters
    lat_step = (swath_width_m / 111000.0)
    # Approximate 1 degree longitude at mean latitude
    mean_lat_rad = math.radians((min_lat + max_lat) / 2.0)
    lon_step = (swath_width_m / (111000.0 * math.cos(mean_lat_rad)))

    waypoints = []
    current_lat = min_lat
    direction = 1 # 1 = West to East, -1 = East to West
    seq = 1

    stress_zones = stress_zones or []

    while current_lat <= max_lat:
        lon_range = []
        # Sample points along this sweep line
        num_samples = 25
        for s in range(num_samples + 1):
            curr_lon = min_lon + s * (max_lon - min_lon) / num_samples
            if point_in_polygon(current_lat, curr_lon, polygon_coords):
                lon_range.append(curr_lon)

        if lon_range:
            start_lon = min(lon_range) if direction == 1 else max(lon_range)
            end_lon = max(lon_range) if direction == 1 else min(lon_range)

            # Check if start or end point intersects a stress hotspot
            def is_stressed(lat, lon):
                for z in stress_zones:
                    # Euclidean distance approximation
                    dist = math.hypot((lat - z["lat"]) * 111000, (lon - z["lon"]) * 111000 * math.cos(mean_lat_rad))
                    if dist <= z.get("radius_m", 25.0):
                        return True
                return False

            spray_start = is_stressed(current_lat, start_lon)
            spray_end = is_stressed(current_lat, end_lon)

            waypoints.append({
                "seq": seq,
                "lat": round(current_lat, 6),
                "lon": round(start_lon, 6),
                "alt": cruise_alt_m,
                "spraying": spray_start,
                "action": "VRT_SPRAY_ON" if spray_start else "TRANSIT"
            })
            seq += 1

            waypoints.append({
                "seq": seq,
                "lat": round(current_lat, 6),
                "lon": round(end_lon, 6),
                "alt": cruise_alt_m,
                "spraying": spray_end,
                "action": "VRT_SPRAY_ON" if spray_end else "TRANSIT"
            })
            seq += 1

            direction *= -1

        current_lat += lat_step

    # Compute mission stats
    total_dist_m = 0.0
    spray_dist_m = 0.0
    for i in range(len(waypoints) - 1):
        p1, p2 = waypoints[i], waypoints[i+1]
        d = math.hypot((p2["lat"] - p1["lat"]) * 111000, (p2["lon"] - p1["lon"]) * 111000 * math.cos(mean_lat_rad))
        total_dist_m += d
        if p1["spraying"] or p2["spraying"]:
            spray_dist_m += d

    spray_reduction_pct = round((1.0 - (spray_dist_m / max(total_dist_m, 1.0))) * 100, 1)

    return {
        "waypoint_count": len(waypoints),
        "total_distance_m": round(total_dist_m, 1),
        "spray_distance_m": round(spray_dist_m, 1),
        "chemical_saved_pct": spray_reduction_pct,
        "flight_time_est_min": round(total_dist_m / (5.0 * 60.0), 1), # assuming 5 m/s drone cruise
        "waypoints": waypoints
    }

def export_mavlink_wpl110(waypoints: List[Dict[str, Any]]) -> str:
    """Generates standard QGroundControl / Mission Planner MAVLink WPL 110 format string.
    Strict sequential integer indexing (0, 1, 2, ...) compatible with all GCS parsers.
    """
    lines = ["QGC WPL 110"]
    seq = 0
    for wp in waypoints:
        current_wp = 1 if seq == 0 else 0
        cmd = 16  # MAV_CMD_NAV_WAYPOINT
        line = f"{seq}\t{current_wp}\t3\t{cmd}\t0.000000\t2.000000\t0.000000\t0.000000\t{wp['lat']:.7f}\t{wp['lon']:.7f}\t{wp.get('alt', 12.0):.2f}\t1"
        lines.append(line)
        seq += 1
        
        if wp.get("spraying", False):
            # MAV_CMD_DO_SET_SERVO = 183 on Channel 9
            lines.append(f"{seq}\t0\t3\t183\t9.000000\t2000.000000\t0.000000\t0.000000\t0.000000\t0.000000\t0.000000\t1")
            seq += 1

    return "\n".join(lines)

if __name__ == "__main__":
    # Self-test
    sample_field = [
        (26.9135, 75.7858),
        (26.9135, 75.7888),
        (26.9113, 75.7888),
        (26.9113, 75.7858)
    ]
    sample_stress = [{"lat": 26.9128, "lon": 75.7878, "radius_m": 30.0}]
    mission = generate_vrt_flight_mission(sample_field, swath_width_m=8.0, stress_zones=sample_stress)
    assert mission["waypoint_count"] > 0
    assert mission["chemical_saved_pct"] > 50.0
    mavlink_text = export_mavlink_wpl110(mission["waypoints"][:5])
    assert "QGC WPL 110" in mavlink_text
    print(f"[OK] Planner passed: {mission['waypoint_count']} waypoints, {mission['chemical_saved_pct']}% chemical saved.")
