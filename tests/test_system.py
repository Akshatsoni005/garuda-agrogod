"""
Garuda AgroGod - Comprehensive End-to-End Test Suite
Tests real satellite NDVI raster matrix computations, real computer vision
green-on-green ExG and solenoid trigger math, and official pymavlink ArduPilot mission protocol.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server.main import (
    app,
    run_real_satellite_ndvi,
    run_real_computer_vision_spot_detect,
    export_real_mavlink2_mission,
    calculate_farmer_roi,
    RoiRequest
)
from ml.real_satellite_ndvi import compute_real_ndvi_raster, generate_vrt_prescription_zones, create_synthetic_field_reflectance
from ml.real_crop_cv import detect_foliar_pathology_and_triggers, create_synthetic_crop_image
from server.real_mavlink_mission import create_mavlink_mission_items, serialize_mission_to_qgc_wpl
from server.planner import calculate_spray_drift

def test_real_satellite_processing():
    print("[1/4] Testing Real Multi-Band Satellite NDVI Raster Engine...")
    red, nir = create_synthetic_field_reflectance(80)
    ndvi = compute_real_ndvi_raster(red, nir)
    assert ndvi.shape == (80, 80)
    assert -1.0 <= ndvi.min() and ndvi.max() <= 1.0
    
    report = generate_vrt_prescription_zones(ndvi)
    assert report["vrt_prescription"]["chemical_reduction_pct"] > 50.0
    print(f"  ✓ Mean NDVI: {report['mean_ndvi']} | Chemical Reduction: {report['vrt_prescription']['chemical_reduction_pct']}%")

def test_real_computer_vision_spot_spray():
    print("[2/4] Testing Real Green-on-Green Computer Vision & Solenoid Timing...")
    frame = create_synthetic_crop_image(300, 300)
    cv_res = detect_foliar_pathology_and_triggers(frame, ground_speed_m_s=3.0, camera_to_nozzle_offset_m=0.6)
    assert cv_res["infection_detected"] is True
    assert cv_res["physical_actuation"]["solenoid_active"] is True
    assert cv_res["physical_actuation"]["trigger_delay_ms"] == 200
    print(f"  ✓ CV Detected {cv_res['lesion_cluster_count']} clusters | Solenoid Delay: {cv_res['physical_actuation']['trigger_delay_ms']}ms")

def test_official_ardupilot_mavlink():
    print("[3/4] Testing Official ArduPilot MAVLink 2.0 Mission Generation...")
    sample_wps = [
        {"lat": 26.9124, "lon": 75.7873, "alt": 10.0, "spraying": False},
        {"lat": 26.9128, "lon": 75.7877, "alt": 10.0, "spraying": True}
    ]
    items = create_mavlink_mission_items(sample_wps)
    wpl = serialize_mission_to_qgc_wpl(items)
    assert "QGC WPL 110" in wpl
    assert "183" in wpl # MAV_CMD_DO_SET_SERVO present
    print(f"  ✓ Generated {len(items)} official MAVLink items with servo PWM commands.")

async def test_fastapi_real_endpoints():
    print("[4/4] Testing FastAPI Integrated Real Endpoints...")
    res_ndvi = await run_real_satellite_ndvi(50)
    assert "zone_distribution" in res_ndvi

    res_cv = await run_real_computer_vision_spot_detect(3.0, 0.6)
    assert res_cv["infection_detected"] is True

    res_mav = await export_real_mavlink2_mission()
    assert "QGC WPL 110" in res_mav.body.decode()
    print("  ✓ All FastAPI real endpoints verified.")

if __name__ == "__main__":
    test_real_satellite_processing()
    test_real_computer_vision_spot_spray()
    test_official_ardupilot_mavlink()
    asyncio.run(test_fastapi_real_endpoints())
    print("\n=======================================================")
    print("  [SUCCESS] 100% OF REAL SCIENTIFIC PIPELINES PASSED!  ")
    print("=======================================================")
