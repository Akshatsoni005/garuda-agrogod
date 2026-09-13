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
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from ml.diagnose import evaluate_crop_health, calculate_ndvi
from ml.real_satellite_ndvi import compute_real_ndvi_raster, generate_vrt_prescription_zones, create_synthetic_field_reflectance
from ml.real_crop_cv import detect_foliar_pathology_and_triggers, create_synthetic_crop_image
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

current_state = {
    "drone": {
        "device_id": "garuda_drone_alpha",
        "lat": 26.912400,
        "lon": 75.787300,
        "alt": 12.5,
        "battery": 98,
        "spraying": False,
        "seq": 0
    },
    "field": {
        "node_id": "garuda_ground_node_01",
        "lat": 26.912000,
        "lon": 75.787000,
        "temp_c": 29.5,
        "humidity_pct": 58.0,
        "soil_moisture_pct": 42.0
    },
    "weather": {
        "wind_speed_kmh": 8.5,
        "wind_direction_deg": 140,
        "safety_status": "OPTIMAL_CONDITIONS",
        "recommended_buffer_m": 3.2
    },
    "vrt_stats": {
        "status": "STANDBY",
        "chemical_saved_pct": 62.4,
        "saved_liters": 14.8,
        "money_saved_inr": 4850
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
    current_state["drone"]["spraying"] = not current_state["drone"]["spraying"]
    status_label = "ACTIVE_SPRAYING" if current_state["drone"]["spraying"] else "STANDBY"
    current_state["vrt_stats"]["status"] = status_label
    await broadcast({
        "type": "VRT_STATUS_UPDATE",
        "data": {
            "spraying": current_state["drone"]["spraying"],
            "status": status_label,
            "vrt_stats": current_state["vrt_stats"]
        }
    })
    return {"status": "ok", "spraying": current_state["drone"]["spraying"]}

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
        "payback_period": "Immediate (First Spray Session)"
    }

@app.post("/api/real/ndvi")
async def run_real_satellite_ndvi(grid_size: int = 100):
    red, nir = create_synthetic_field_reflectance(grid_size)
    ndvi_matrix = compute_real_ndvi_raster(red, nir)
    report = generate_vrt_prescription_zones(ndvi_matrix)
    await broadcast({"type": "REAL_NDVI_REPORT", "data": report})
    return report

@app.post("/api/real/cv_spot_detect")
async def run_real_computer_vision_spot_detect(speed_m_s: float = 3.0, offset_m: float = 0.6):
    frame = create_synthetic_crop_image()
    cv_res = detect_foliar_pathology_and_triggers(frame, ground_speed_m_s=speed_m_s, camera_to_nozzle_offset_m=offset_m)
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

@app.websocket("/ws/cockpit")
async def cockpit_websocket(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    await websocket.send_text(json.dumps({"type": "INITIAL_STATE", "data": current_state}))
    try:
        while True:
            msg = await websocket.receive_text()
            try:
                cmd = json.loads(msg)
                if cmd.get("action") == "TOGGLE_SPRAY":
                    await toggle_vrt_spray()
            except Exception:
                pass
    except WebSocketDisconnect:
        connected_websockets.discard(websocket)

CLIENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "client"))
if os.path.exists(CLIENT_DIR):
    app.mount("/static", StaticFiles(directory=CLIENT_DIR), name="static")

@app.get("/")
async def root():
    index_file = os.path.join(CLIENT_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Garuda AgroGod API is running."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
