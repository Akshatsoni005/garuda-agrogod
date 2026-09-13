"""
Garuda AgroGod - Central Tactical Bridge & Telemetry Server
Ponytail: Single-file backend serving REST endpoints, WebSockets, MAVLink mission export, and static client.
Zero complex microservices. Runs locally on port 8000.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from typing import Optional, Set, List, Tuple, Dict, Any
import asyncio
import json
import os
import sys

# Add parent directory for module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from ml.real_satellite_ndvi import compute_real_ndvi_raster, generate_vrt_prescription_zones, create_synthetic_field_reflectance
from ml.real_crop_cv import detect_foliar_pathology_and_triggers, create_synthetic_crop_image
from ml.central_complex import BiologicalNavigationSystem, run_gps_denied_flight_benchmark
from server.planner import generate_vrt_flight_mission, export_mavlink_wpl110, calculate_spray_drift
from server.real_mavlink_mission import create_mavlink_mission_items, serialize_mission_to_qgc_wpl

app = FastAPI(title="Garuda AgroGod Command Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connected_websockets: Set[WebSocket] = set()

# In-memory flight mission cache
latest_mission_cache: Dict[str, Any] = {}

FARM_PRESETS = {
    "punjab_wheat": {
        "id": "punjab_wheat",
        "name": "Punjab Wheat Belt (Ludhiana)",
        "state": "Punjab, India",
        "center": [30.852500, 75.865000],
        "zoom": 17,
        "crop": "Triticum aestivum (HD-3086 Wheat)",
        "growth_stage": "Feekes 10.1 (Flowering & Early Heading)",
        "soil_type": "Alluvial Loam (Indo-Gangetic Basin)",
        "lai": 3.48,
        "chlorophyll_spad": 48.6,
        "soil_moisture_pct": 24.8,
        "canopy_temp_c": 22.4,
        "air_temp_c": 24.8,
        "temp_depression_c": -2.4,
        "fapar": 0.85,
        "target_disease": "Puccinia striiformis (Yellow Rust)",
        "chemical_name": "Azoxystrobin 18.2% + Difenoconazole 11.4% SC",
        "blanket_rate_ml_acre": 200,
        "total_acres": 5.0,
        "infested_acres": 0.625,
        "chemical_saved_pct": 87.5,
        "money_saved_inr": 3850,
        "water_saved_liters": 900,
        "reflectance": {
            "b02_blue": 0.024,
            "b03_green": 0.052,
            "b04_red": 0.038,
            "b08_nir": 0.512,
            "b11_swir": 0.145,
            "ndvi": 0.862,
            "ndwi": -0.472
        },
        "polygon": [
            [30.8545, 75.8620],
            [30.8545, 75.8685],
            [30.8505, 75.8685],
            [30.8505, 75.8620]
        ],
        "stress_hotspot": {
            "lat": 30.8530,
            "lon": 75.8665,
            "radius_m": 38.0,
            "ndvi": 0.267,
            "cause": "Yellow Rust Pustule Outbreak (Sector 04)"
        }
    },
    "haryana_paddy": {
        "id": "haryana_paddy",
        "name": "Haryana Basmati Basin (Karnal)",
        "state": "Haryana, India",
        "center": [29.692000, 76.985000],
        "zoom": 17,
        "crop": "Oryza sativa (Pusa Basmati 1121)",
        "growth_stage": "Tillering / Active Panicle Initiation",
        "soil_type": "Clay Loam (Puddled Paddy Soil)",
        "lai": 3.85,
        "chlorophyll_spad": 45.2,
        "soil_moisture_pct": 36.5,
        "canopy_temp_c": 26.2,
        "air_temp_c": 29.0,
        "temp_depression_c": -2.8,
        "fapar": 0.88,
        "target_disease": "Xanthomonas oryzae (Bacterial Leaf Blight)",
        "chemical_name": "Copper Oxychloride 50% WP + Streptomycin",
        "blanket_rate_ml_acre": 250,
        "total_acres": 6.2,
        "infested_acres": 0.95,
        "chemical_saved_pct": 84.7,
        "money_saved_inr": 4200,
        "water_saved_liters": 1150,
        "reflectance": {
            "b02_blue": 0.028,
            "b03_green": 0.065,
            "b04_red": 0.042,
            "b08_nir": 0.540,
            "b11_swir": 0.180,
            "ndvi": 0.856,
            "ndwi": -0.500
        },
        "polygon": [
            [29.6940, 76.9820],
            [29.6940, 76.9880],
            [29.6900, 76.9880],
            [29.6900, 76.9820]
        ],
        "stress_hotspot": {
            "lat": 29.6925,
            "lon": 76.9860,
            "radius_m": 42.0,
            "ndvi": 0.310,
            "cause": "Bacterial Leaf Blight Wilting"
        }
    },
    "rajasthan_canal": {
        "id": "rajasthan_canal",
        "name": "Indira Gandhi Canal Oasis (Sri Ganganagar)",
        "state": "Rajasthan, India",
        "center": [29.920000, 73.880000],
        "zoom": 16,
        "crop": "Brassica juncea (Mustard / Pusa Bold)",
        "growth_stage": "Flowering & Siliqua Development",
        "soil_type": "Sandy Loam (Canal Irrigated)",
        "lai": 2.95,
        "chlorophyll_spad": 42.1,
        "soil_moisture_pct": 19.4,
        "canopy_temp_c": 21.8,
        "air_temp_c": 25.5,
        "temp_depression_c": -3.7,
        "fapar": 0.79,
        "target_disease": "Albugo candida (White Rust of Mustard)",
        "chemical_name": "Mancozeb 75% WP + Metalaxyl 8%",
        "blanket_rate_ml_acre": 300,
        "total_acres": 8.0,
        "infested_acres": 1.10,
        "chemical_saved_pct": 86.2,
        "money_saved_inr": 5100,
        "water_saved_liters": 1400,
        "reflectance": {
            "b02_blue": 0.035,
            "b03_green": 0.070,
            "b04_red": 0.050,
            "b08_nir": 0.480,
            "b11_swir": 0.210,
            "ndvi": 0.811,
            "ndwi": -0.391
        },
        "polygon": [
            [29.9230, 73.8760],
            [29.9230, 73.8840],
            [29.9170, 73.8840],
            [29.9170, 73.8760]
        ],
        "stress_hotspot": {
            "lat": 29.9205,
            "lon": 73.8815,
            "radius_m": 45.0,
            "ndvi": 0.260,
            "cause": "White Rust Pustule Blistering"
        }
    },
    "maharashtra_sugarcane": {
        "id": "maharashtra_sugarcane",
        "name": "Baramati Sugarcane Belt (Pune Basin)",
        "state": "Maharashtra, India",
        "center": [18.151000, 74.577000],
        "zoom": 17,
        "crop": "Saccharum officinarum (Co 86032)",
        "growth_stage": "Grand Growth / Internode Elongation",
        "soil_type": "Black Cotton Soil (Vertisol)",
        "lai": 4.60,
        "chlorophyll_spad": 52.4,
        "soil_moisture_pct": 31.0,
        "canopy_temp_c": 25.0,
        "air_temp_c": 28.5,
        "temp_depression_c": -3.5,
        "fapar": 0.92,
        "target_disease": "Colletotrichum falcatum (Red Rot)",
        "chemical_name": "Carbendazim 50% WP (Spot Drench/Spray)",
        "blanket_rate_ml_acre": 350,
        "total_acres": 4.5,
        "infested_acres": 0.50,
        "chemical_saved_pct": 88.9,
        "money_saved_inr": 3600,
        "water_saved_liters": 850,
        "reflectance": {
            "b02_blue": 0.020,
            "b03_green": 0.048,
            "b04_red": 0.030,
            "b08_nir": 0.590,
            "b11_swir": 0.130,
            "ndvi": 0.903,
            "ndwi": -0.520
        },
        "polygon": [
            [18.1530, 74.5740],
            [18.1530, 74.5800],
            [18.1490, 74.5800],
            [18.1490, 74.5740]
        ],
        "stress_hotspot": {
            "lat": 18.1515,
            "lon": 74.5780,
            "radius_m": 35.0,
            "ndvi": 0.320,
            "cause": "Red Rot Interveinal Chlorosis"
        }
    }
}

# ─── Data Source Taxonomy ─────────────────────────────────────────────────────
# Every API response should include data_source from this set:
# LIVE   - Real hardware reading (ESP32, sensor, GPS)
# SIMULATED - Software-generated synthetic value
# CALCULATED - Mathematically derived from real inputs (NDVI from real B04/B08)
# MODELLED - Physics/agronomic model output, not yet field-validated
# ESTIMATED - Statistical inference, sub-pixel extrapolation
DATA_SOURCE = {
    "drone_telemetry": "SIMULATED",      # ESP32 simulates orbit; not airborne
    "field_sensor": "SIMULATED",         # ESP32 uses random() drift; no real probe
    "ndvi_endpoint": "CALCULATED_SYNTHETIC",  # Real NumPy math on synthetic reflectance
    "cv_detection": "CALCULATED_SYNTHETIC",   # Real OpenCV on synthetic crop image
    "bio_nav_benchmark": "SIMULATED",    # Simulation benchmark, not real IMU
    "drift_model": "MODELLED",           # Empirical formula, not field-validated
    "roi_model": "MODELLED",             # Economic model, not field-trial data
    "farm_presets": "LITERATURE_BASED",  # Based on published Sentinel-2 reflectance ranges
    "spad_index": "ESTIMATED",           # Derived from hotspot proximity model, not instrument
    "chemical_savings": "MODELLED",      # VRT volume model, efficacy unvalidated
}

current_state = {
    "drone": {
        "device_id": "garuda_drone_alpha",
        "lat": 30.852500,
        "lon": 75.865000,
        "alt": 15.0,
        "battery": 98,
        "spraying": False,
        "seq": 0
    },
    "field": {
        "node_id": "garuda_ground_node_01",
        "lat": 30.852000,
        "lon": 75.864500,
        "temp_c": 24.8,
        "humidity_pct": 62.0,
        "soil_moisture_pct": 24.8
    },
    "weather": {
        "wind_speed_kmh": 6.8,
        "wind_direction_deg": 135,
        "safety_status": "MODELLED_LOW_RISK",
        "recommended_buffer_m": 2.8
    },
    "vrt_stats": {
        "status": "STANDBY",
        "chemical_saved_pct": 87.5,
        "saved_liters": 18.2,
        "money_saved_inr": 3850
    }
}

async def broadcast(message: dict):
    payload = json.dumps(message)
    for ws in list(connected_websockets):
        try:
            await ws.send_text(payload)
        except Exception:
            connected_websockets.discard(ws)

class DronePacket(BaseModel):
    device_id: Optional[str] = "garuda_drone"
    lat: float
    lon: float
    alt: float
    battery: int
    spraying: bool
    seq: Optional[int] = 0

class FieldPacket(BaseModel):
    node_id: Optional[str] = "garuda_field_node"
    lat: float
    lon: float
    temp_c: float
    humidity_pct: float
    soil_moisture_pct: float

class MissionRequest(BaseModel):
    polygon: List[List[float]] # [[lat, lon], ...]
    swath_width_m: float = 6.0
    cruise_alt_m: float = 12.0
    stress_zones: Optional[List[Dict[str, Any]]] = None

class RoiRequest(BaseModel):
    farm_area_acres: float = 5.0
    crop_type: str = "Wheat"
    spray_passes_per_season: int = 3

class BioNavStepRequest(BaseModel):
    dt: float = 0.05
    gyro_z_rad_s: float = 0.0
    forward_speed_m_s: float = 2.5
    lateral_speed_m_s: float = 0.0
    visual_cue_heading: Optional[float] = None

class BioNavSimulateRequest(BaseModel):
    duration_s: float = 60.0
    wind_gust_strength: float = 0.6
    mag_drift_deg_per_min: float = 45.0
    gyro_bias_rad_s: float = 0.02

@app.post("/api/telemetry/drone")
async def receive_drone_telemetry(data: DronePacket):
    current_state["drone"] = data.model_dump()
    await broadcast({"type": "DRONE_TELEMETRY", "data": current_state["drone"]})
    return {"status": "ok", "synced": True}

@app.post("/api/telemetry/field")
async def receive_field_telemetry(data: FieldPacket):
    current_state["field"] = data.model_dump()
    await broadcast({"type": "FIELD_TELEMETRY", "data": current_state["field"]})
    return {"status": "ok", "synced": True}

@app.post("/api/vrt/toggle_spray")
async def toggle_vrt_spray():
    """Toggles simulated spray state in cockpit digital twin.
    SAFETY GUARD: Physical actuator commanding over unauthenticated internet is locked.
    This toggle modifies digital twin state only.
    """
    current_state["drone"]["spraying"] = not current_state["drone"]["spraying"]
    status_label = "ACTIVE_SPRAYING (SIM)" if current_state["drone"]["spraying"] else "STANDBY"
    current_state["vrt_stats"]["status"] = status_label
    await broadcast({
        "type": "VRT_STATUS_UPDATE",
        "data": {
            "spraying": current_state["drone"]["spraying"],
            "status": status_label,
            "vrt_stats": current_state["vrt_stats"],
            "mode": "SIMULATION_TWIN_ONLY"
        }
    })
    return {
        "status": "ok",
        "spraying": current_state["drone"]["spraying"],
        "control_mode": "SIMULATION_TWIN_ONLY",
        "safety_guard": "PHYSICAL_ACTUATION_LOCKED",
        "data_source": "SIMULATED"
    }

@app.post("/api/mission/generate")
async def api_generate_mission(req: MissionRequest):
    global latest_mission_cache
    polygon_tuples = [(p[0], p[1]) for p in req.polygon]
    mission = generate_vrt_flight_mission(
        polygon_coords=polygon_tuples,
        swath_width_m=req.swath_width_m,
        cruise_alt_m=req.cruise_alt_m,
        stress_zones=req.stress_zones
    )
    latest_mission_cache = mission
    await broadcast({"type": "MISSION_GENERATED", "data": mission})
    return mission

@app.get("/api/mission/export/mavlink")
async def export_mavlink():
    global latest_mission_cache
    if not latest_mission_cache or "waypoints" not in latest_mission_cache:
        # Default fallback sample mission
        sample_field = [(26.9135, 75.7858), (26.9135, 75.7888), (26.9113, 75.7888), (26.9113, 75.7858)]
        latest_mission_cache = generate_vrt_flight_mission(sample_field)

    mavlink_content = export_mavlink_wpl110(latest_mission_cache["waypoints"])
    return PlainTextResponse(
        mavlink_content,
        headers={"Content-Disposition": "attachment; filename=garuda_vrt_mission.waypoints"}
    )

@app.get("/api/weather/drift")
async def get_drift_status(wind_kmh: float = 8.5):
    drift = calculate_spray_drift(wind_kmh)
    current_state["weather"]["wind_speed_kmh"] = wind_kmh
    current_state["weather"]["safety_status"] = drift["safety_status"]
    current_state["weather"]["recommended_buffer_m"] = drift["recommended_buffer_m"]
    return drift

@app.post("/api/farmer/roi")
async def calculate_farmer_roi(req: RoiRequest):
    # Standard agricultural metrics for Indian smallholders
    chemical_cost_per_acre_inr = 1800 # Pesticides/fungicides per acre
    water_liters_per_acre_manual = 200 # Heavy knapsack water wastage
    water_liters_per_acre_drone = 20   # Ultra-low-volume ULV spray
    labor_cost_per_acre_inr = 600     # Manual spraying labor
    drone_faas_cost_per_acre_inr = 450 # Garuda FaaS booking charge

    total_acres = req.farm_area_acres * req.spray_passes_per_season
    traditional_cost = (chemical_cost_per_acre_inr + labor_cost_per_acre_inr) * total_acres
    
    # Garuda precision VRT: 62% pesticide reduction
    garuda_chemical_cost = (chemical_cost_per_acre_inr * 0.38) * total_acres
    garuda_service_cost = drone_faas_cost_per_acre_inr * total_acres
    garuda_total_cost = garuda_chemical_cost + garuda_service_cost
    
    net_savings_inr = round(traditional_cost - garuda_total_cost, 0)
    water_saved_liters = round((water_liters_per_acre_manual - water_liters_per_acre_drone) * total_acres, 0)
    chemical_saved_pct = 62.0

    return {
        "farm_area_acres": req.farm_area_acres,
        "traditional_total_cost_inr": traditional_cost,
        "garuda_vrt_cost_inr": garuda_total_cost,
        "net_money_saved_inr": net_savings_inr,
        "water_saved_liters": water_saved_liters,
        "chemical_saved_pct": chemical_saved_pct,
        "chemical_saved_pct_note": "Conservative fleet-average (62%). Per-field VRT savings range 80-90% depending on infestation area.",
        "payback_period": "Immediate (First Spray Session)",
        "data_source": "MODELLED",
        "model_note": "Economic model based on published ICAR input costs (2023-24). Chemical efficacy at reduced rates unvalidated by field trial."
    }

@app.post("/api/real/ndvi")
async def run_real_satellite_ndvi(grid_size: int = 100):
    red, nir = create_synthetic_field_reflectance(grid_size)
    ndvi_matrix = compute_real_ndvi_raster(red, nir)
    report = generate_vrt_prescription_zones(ndvi_matrix)
    report["data_source"] = "CALCULATED_SYNTHETIC"
    report["data_note"] = "Real NumPy NDVI algorithm applied to synthetic reflectance arrays. Not real Sentinel-2 ingestion."
    await broadcast({"type": "REAL_NDVI_REPORT", "data": report})
    return report

@app.post("/api/real/cv_spot_detect")
async def run_real_computer_vision_spot_detect(speed_m_s: float = 3.0, offset_m: float = 0.6):
    frame = create_synthetic_crop_image()
    cv_res = detect_foliar_pathology_and_triggers(frame, ground_speed_m_s=speed_m_s, camera_to_nozzle_offset_m=offset_m)
    cv_res["data_source"] = "CALCULATED_SYNTHETIC"
    cv_res["data_note"] = "Real OpenCV pipeline applied to synthetic crop frame. Yellow-lesion candidate detector, not disease classifier."
    await broadcast({"type": "REAL_CV_DETECTION", "data": cv_res})
    return cv_res

@app.get("/api/real/export_mavlink2")
async def export_real_mavlink2_mission():
    global latest_mission_cache
    if not latest_mission_cache or "waypoints" not in latest_mission_cache:
        sample_field = [(26.9135, 75.7858), (26.9135, 75.7888), (26.9113, 75.7888), (26.9113, 75.7858)]
        sample_stress = [{"lat": 26.9128, "lon": 75.7878, "radius_m": 30.0}]
        latest_mission_cache = generate_vrt_flight_mission(sample_field, stress_zones=sample_stress)

    items = create_mavlink_mission_items(latest_mission_cache["waypoints"])
    wpl_content = serialize_mission_to_qgc_wpl(items)
    return PlainTextResponse(
        wpl_content,
        headers={"Content-Disposition": "attachment; filename=garuda_ardupilot_vrt.waypoints"}
    )

class SamplePointRequest(BaseModel):
    farm_id: Optional[str] = "punjab_wheat"
    lat: float
    lon: float

class SwitchFarmRequest(BaseModel):
    farm_id: str

@app.get("/api/gee/presets")
async def get_gee_presets():
    return FARM_PRESETS

@app.post("/api/gee/switch_farm")
async def switch_gee_farm(req: SwitchFarmRequest):
    farm = FARM_PRESETS.get(req.farm_id, FARM_PRESETS["punjab_wheat"])
    current_state["drone"]["lat"] = farm["center"][0]
    current_state["drone"]["lon"] = farm["center"][1]
    current_state["field"]["lat"] = farm["center"][0] - 0.0005
    current_state["field"]["lon"] = farm["center"][1] - 0.0005
    current_state["field"]["temp_c"] = farm["air_temp_c"]
    current_state["field"]["soil_moisture_pct"] = farm["soil_moisture_pct"]
    current_state["vrt_stats"]["chemical_saved_pct"] = farm["chemical_saved_pct"]
    current_state["vrt_stats"]["money_saved_inr"] = farm["money_saved_inr"]
    await broadcast({"type": "FARM_SWITCHED", "data": farm})
    return {"status": "ok", "active_farm": farm}

@app.post("/api/gee/sample_point")
async def sample_gee_point(req: SamplePointRequest):
    farm = FARM_PRESETS.get(req.farm_id, FARM_PRESETS["punjab_wheat"])
    hotspot = farm["stress_hotspot"]
    # Compute rough distance in meters to stress hotspot
    d_lat = (req.lat - hotspot["lat"]) * 111000.0
    d_lon = (req.lon - hotspot["lon"]) * 95000.0
    dist_m = (d_lat**2 + d_lon**2)**0.5
    radius = hotspot["radius_m"]

    if dist_m <= radius:
        # Inside infection core
        b04_red = 0.165
        b08_nir = 0.285
        ndvi = round((b08_nir - b04_red) / (b08_nir + b04_red), 3)  # = 0.267, exact match with band physics
        spad = round(21.4 + (dist_m / radius) * 8.0, 1)
        lai = round(1.2 + (dist_m / radius) * 0.8, 2)
        vrt_pwm_pct = 100
        health_status = f"PATHOLOGY_DETECTED: {hotspot['cause']}"
        nozzle_status = "ACTIVE_DISCHARGE_100_PCT"
    elif dist_m <= radius * 1.8:
        # Buffer / Drift mitigation perimeter
        ndvi = round(0.55 + ((dist_m - radius) / radius) * 0.2, 3)
        b04_red = 0.082
        b08_nir = 0.410
        spad = 38.2
        lai = 2.65
        vrt_pwm_pct = 40
        health_status = "DRIFT_BUFFER_MARGIN"
        nozzle_status = "PROPORTIONAL_PULSE_40_PCT"
    else:
        # Clean healthy vegetative crop
        ndvi = farm["reflectance"]["ndvi"]
        b04_red = farm["reflectance"]["b04_red"]
        b08_nir = farm["reflectance"]["b08_nir"]
        spad = farm["chlorophyll_spad"]
        lai = farm["lai"]
        vrt_pwm_pct = 0
        health_status = "HEALTHY_VIGOROUS_CANOPY"
        nozzle_status = "VALVE_SHUT_STANDBY"

    ndwi = round((farm["reflectance"]["b03_green"] - b08_nir) / (farm["reflectance"]["b03_green"] + b08_nir), 3)

    return {
        "query_coords": [req.lat, req.lon],
        "farm_id": farm["id"],
        "farm_name": farm["name"],
        "crop": farm["crop"],
        "growth_stage": farm["growth_stage"],
        "data_source": "MODELLED",
        "data_note": "Spectral values modelled from farm literature baseline + proximity-based stress gradient. Not real Sentinel-2 pixel query.",
        "spectral_bands": {
            "b02_blue_490nm": farm["reflectance"]["b02_blue"],
            "b03_green_560nm": farm["reflectance"]["b03_green"],
            "b04_red_665nm": b04_red,
            "b08_nir_842nm": b08_nir,
            "b11_swir_1610nm": farm["reflectance"]["b11_swir"]
        },
        "indices": {
            "ndvi": ndvi,
            "ndwi": ndwi,
            "chlorophyll_index_estimated": spad,
            "leaf_area_index": lai,
            "fapar": farm["fapar"]
        },
        "pathology": {
            "status": health_status,
            "canopy_temp_c": farm["canopy_temp_c"] if vrt_pwm_pct == 0 else farm["canopy_temp_c"] + 2.8,
            "temp_depression_c": farm["temp_depression_c"] if vrt_pwm_pct == 0 else "+0.4",
            "target_disease": farm["target_disease"],
            "prescribed_chemical": farm["chemical_name"]
        },
        "vrt_actuation": {
            "nozzle_pwm_pct": vrt_pwm_pct,
            "nozzle_state": nozzle_status,
            "target_dose_ml_acre": farm["blanket_rate_ml_acre"] if vrt_pwm_pct == 100 else (farm["blanket_rate_ml_acre"] * 0.4 if vrt_pwm_pct == 40 else 0),
            "solenoid_advance_lead_ms": 200
        }
    }

# --- Biological Central Complex (CX) Navigation Endpoints ---
active_bio_nav = BiologicalNavigationSystem()

@app.post("/api/bio-nav/step")
async def step_bio_navigation(req: BioNavStepRequest):
    telemetry = active_bio_nav.step(
        dt=req.dt,
        gyro_z_rad_s=req.gyro_z_rad_s,
        forward_speed_m_s=req.forward_speed_m_s,
        lateral_speed_m_s=req.lateral_speed_m_s,
        visual_cue_heading=req.visual_cue_heading
    )
    await broadcast({"type": "BIO_NAV_TELEMETRY", "data": telemetry})
    return telemetry

@app.get("/api/bio-nav/state")
async def get_bio_navigation_state():
    telemetry = active_bio_nav.step(dt=0.0, gyro_z_rad_s=0.0, forward_speed_m_s=0.0)
    return telemetry

@app.post("/api/bio-nav/simulate")
async def simulate_gps_denied_flight(req: BioNavSimulateRequest):
    res = run_gps_denied_flight_benchmark(
        flight_duration_s=req.duration_s,
        wind_gust_strength=req.wind_gust_strength,
        mag_drift_deg_per_min=req.mag_drift_deg_per_min,
        gyro_bias_rad_s=req.gyro_bias_rad_s
    )
    # P0 FIX: Normalize schema so frontend can access both formats
    # Frontend expects: d.metrics.drift_error_reduction_pct, d.metrics.naive_dr_drift_m, etc.
    summary = res.get("benchmark_summary", {})
    res["metrics"] = {
        "naive_dr_drift_m": summary.get("final_dead_reckoning_drift_m", 0.0),
        "biological_cx_drift_m": summary.get("final_biological_drift_m", 0.0),
        "drift_error_reduction_pct": summary.get("drift_reduction_pct", 0.0),
        "homing_target_reached": summary.get("homing_success", False)
    }
    await broadcast({"type": "BIO_NAV_SIMULATION_RESULT", "data": res})
    return res

@app.get("/api/bio-nav/mavlink_odometry")
async def get_mavlink_odometry(alt_m: float = 12.0):
    return active_bio_nav.generate_mavlink_odometry_packet(alt_m=alt_m)

@app.websocket("/ws/cockpit")
async def cockpit_websocket(websocket: WebSocket):
    # NOTE: WebSocket controls simulation state. Hardware integration requires device auth.
    await websocket.accept()
    connected_websockets.add(websocket)
    await websocket.send_text(json.dumps({"type": "INITIAL_STATE", "data": current_state}))
    try:
        while True:
            msg = await websocket.receive_text()
            try:
                cmd = json.loads(msg)
                if cmd.get("action") == "TOGGLE_SPRAY":
                    # Safety: this toggles simulation state only, not real hardware
                    await toggle_vrt_spray()
            except Exception:
                pass
    except WebSocketDisconnect:
        connected_websockets.discard(websocket)

CLIENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "client"))
if os.path.exists(CLIENT_DIR):
    app.mount("/static", StaticFiles(directory=CLIENT_DIR), name="static")

@app.get("/gods_eye.html")
async def get_gods_eye():
    file_path = os.path.join(CLIENT_DIR, "gods_eye.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "gods_eye.html not found"}

@app.get("/")
async def root():
    index_file = os.path.join(CLIENT_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Garuda AgroGod API is running."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
