"""
Garuda AgroGod - End-to-End System & Integration Tests
Ponytail: Pure standard-library test runner.
Tests ML math, async FastAPI endpoints, and static HTML UI without external test packages.
"""

import sys
import os
import asyncio

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server.main import app, receive_drone_telemetry, receive_field_telemetry, toggle_vrt_spray, DronePacket, FieldPacket
from ml.diagnose import calculate_ndvi, evaluate_crop_health

def test_ml_diagnosis():
    print("[1/3] Testing NDVI & VRT crop health calculation...")
    ndvi = calculate_ndvi(0.7, 0.2)
    assert ndvi == 0.556, f"NDVI calculation unexpected: {ndvi}"
    
    # Healthy case
    healthy_res = evaluate_crop_health(ndvi, "healthy", field_area_ha=2.0)
    assert healthy_res["recommended_action"] == "BYPASS_HEALTHY"
    assert healthy_res["vrt_spray_volume_liters"] == 0.0

    # Diseased case
    diseased_res = evaluate_crop_health(0.25, "yellow_rust", field_area_ha=2.0)
    assert diseased_res["recommended_action"] == "DISPATCH_VRT_SPRAY"
    assert diseased_res["chemical_saved_pct"] == 70.0
    print("  ✓ ML diagnosis passed.")

async def test_fastapi_endpoints():
    print("[2/3] Testing FastAPI async endpoints directly...")
    
    # Drone telemetry
    drone_pkt = DronePacket(
        device_id="test_esp32_s3",
        lat=26.912450,
        lon=75.787350,
        alt=15.0,
        battery=95,
        spraying=False,
        seq=101
    )
    res_drone = await receive_drone_telemetry(drone_pkt)
    assert res_drone["status"] == "ok"
    assert res_drone["synced"] is True

    # Field sensor telemetry
    field_pkt = FieldPacket(
        node_id="test_ground_node",
        lat=26.912000,
        lon=75.787000,
        temp_c=30.1,
        humidity_pct=55.4,
        soil_moisture_pct=41.2
    )
    res_field = await receive_field_telemetry(field_pkt)
    assert res_field["status"] == "ok"
    assert res_field["synced"] is True

    # VRT Spray Toggle
    res_spray = await toggle_vrt_spray()
    assert res_spray["status"] == "ok"
    assert "spraying" in res_spray
    print("  ✓ Telemetry and VRT endpoints passed.")

def test_client_assets():
    print("[3/3] Checking client frontend assets...")
    index_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "client", "index.html"))
    assert os.path.exists(index_path), "client/index.html is missing!"
    with open(index_path, "r") as f:
        content = f.read()
    assert "GARUDA // AGRO-GOD" in content
    assert "map" in content
    assert "toggleNDVI" in content
    assert "FLIR" in content
    print("  ✓ Client UI verification passed.")

if __name__ == "__main__":
    test_ml_diagnosis()
    asyncio.run(test_fastapi_endpoints())
    test_client_assets()
    print("\n==============================================")
    print("  [SUCCESS] ALL AGROGOD TESTS PASSED!        ")
    print("==============================================")
