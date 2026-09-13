"""
Garuda AgroGod - End-to-End System & Integration Tests
Ponytail: Pure standard-library test runner.
Tests ML math, async FastAPI endpoints, MAVLink generator, and static HTML UI.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server.main import (
    app,
    receive_drone_telemetry,
    receive_field_telemetry,
    toggle_vrt_spray,
    api_generate_mission,
    export_mavlink,
    get_drift_status,
    calculate_farmer_roi,
    DronePacket,
    FieldPacket,
    MissionRequest,
    RoiRequest
)
from ml.diagnose import calculate_ndvi, evaluate_crop_health
from server.planner import generate_vrt_flight_mission, calculate_spray_drift, export_mavlink_wpl110

def test_ml_and_physics():
    print("[1/4] Testing NDVI math & spray drift physics...")
    ndvi = calculate_ndvi(0.7, 0.2)
    assert ndvi == 0.556
    
    drift = calculate_spray_drift(wind_speed_kmh=10.0, flight_alt_m=3.0)
    assert drift["can_spray"] is True
    assert drift["recommended_buffer_m"] > 0
    print("  ✓ ML and physics drift calculations passed.")

async def test_planner_and_mavlink():
    print("[2/4] Testing Boustrophedon survey planner & MAVLink export...")
    field_poly = [[26.9135, 75.7858], [26.9135, 75.7888], [26.9113, 75.7888], [26.9113, 75.7858]]
    mission_req = MissionRequest(polygon=field_poly, swath_width_m=8.0)
    mission_res = await api_generate_mission(mission_req)
    assert mission_res["waypoint_count"] > 0
    assert "chemical_saved_pct" in mission_res

    mav_res = await export_mavlink()
    assert "QGC WPL 110" in mav_res.body.decode()
    print("  ✓ Autonomous mission generator and MAVLink export passed.")

async def test_fastapi_endpoints():
    print("[3/4] Testing telemetry and ROI endpoints...")
    drone_pkt = DronePacket(device_id="esp32_s3", lat=26.9124, lon=75.7873, alt=12.0, battery=98, spraying=False)
    res_drone = await receive_drone_telemetry(drone_pkt)
    assert res_drone["synced"] is True

    roi_req = RoiRequest(farm_area_acres=5.0, crop_type="Wheat", spray_passes_per_season=3)
    roi_res = await calculate_farmer_roi(roi_req)
    assert roi_res["net_money_saved_inr"] > 10000
    assert roi_res["chemical_saved_pct"] == 62.0
    print("  ✓ Telemetry and ROI endpoints passed.")

def test_client_assets():
    print("[4/4] Checking client frontend assets...")
    index_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "client", "index.html"))
    assert os.path.exists(index_path)
    with open(index_path, "r") as f:
        content = f.read()
    assert "OPENVRT" in content
    assert "planVrtMission" in content
    assert "exportMavlink" in content
    print("  ✓ Client UI verification passed.")

if __name__ == "__main__":
    test_ml_and_physics()
    asyncio.run(test_planner_and_mavlink())
    asyncio.run(test_fastapi_endpoints())
    test_client_assets()
    print("\n==============================================")
    print("  [SUCCESS] ALL FULL-FLEDGED TESTS PASSED!   ")
    print("==============================================")
