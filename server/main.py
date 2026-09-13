"""
Garuda AgroGod - Central Tactical Bridge & Telemetry Server
Ponytail: Single-file backend serving REST endpoints, WebSockets, and static client.
Zero complex microservices. Runs locally on port 8000.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Set
import asyncio
import json
import os
import sys

# Add parent directory for module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from ml.diagnose import evaluate_crop_health, calculate_ndvi

app = FastAPI(title="Garuda AgroGod Command Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connected_websockets: Set[WebSocket] = set()

# State memory
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
    "vrt_stats": {
        "status": "STANDBY",
        "chemical_saved_pct": 62.4,
        "saved_liters": 14.8,
        "money_saved_inr": 4850
    }
}

async def broadcast(message: dict):
    """Broadcast JSON message to all active cockpit UI clients."""
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

class DiagnosisRequest(BaseModel):
    nir: float = 0.62
    red: float = 0.22
    symptom: str = "yellow_rust"
    field_area_ha: float = 2.5

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

@app.post("/api/crop/diagnose")
async def run_crop_diagnosis(req: DiagnosisRequest):
    ndvi = calculate_ndvi(req.nir, req.red)
    res = evaluate_crop_health(ndvi, req.symptom, req.field_area_ha)
    await broadcast({"type": "CROP_DIAGNOSIS_RESULT", "data": res})
    return res

@app.websocket("/ws/cockpit")
async def cockpit_websocket(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    # Send initial state snapshot on connection
    await websocket.send_text(json.dumps({"type": "INITIAL_STATE", "data": current_state}))
    try:
        while True:
            msg = await websocket.receive_text()
            # Handle client commands if any
            try:
                cmd = json.loads(msg)
                if cmd.get("action") == "TOGGLE_SPRAY":
                    await toggle_vrt_spray()
            except Exception:
                pass
    except WebSocketDisconnect:
        connected_websockets.discard(websocket)

# Serve client assets
CLIENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "client"))
if os.path.exists(CLIENT_DIR):
    app.mount("/static", StaticFiles(directory=CLIENT_DIR), name="static")

@app.get("/")
async def root():
    index_file = os.path.join(CLIENT_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Garuda AgroGod API is running. Client folder not found."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
