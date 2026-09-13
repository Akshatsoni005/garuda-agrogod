"""
Garuda AgroGod - Hardware ESP32-S3 Simulator
Ponytail: 35-line script that mocks physical ESP32 drone & ground telemetry.
Use for testing the 3D cockpit without physical USB hardware plugged in.
"""

import requests
import time
import math

SERVER_URL = "http://localhost:8000"

def run_simulation():
    print("[Simulator] Starting ESP32-S3 hardware emulation...")
    seq = 0
    base_lat = 26.912400
    base_lon = 75.787300
    battery = 98

    while True:
        seq += 1
        # Circular patrol trajectory around the agricultural field
        radius = 0.0006
        drone_lat = base_lat + radius * math.cos(seq * 0.15)
        drone_lon = base_lon + radius * math.sin(seq * 0.15)
        if seq % 20 == 0 and battery > 15:
            battery -= 1

        drone_payload = {
            "device_id": "esp32_drone_sim",
            "lat": round(drone_lat, 6),
            "lon": round(drone_lon, 6),
            "alt": 14.5 + round(math.sin(seq * 0.2) * 1.5, 1),
            "battery": battery,
            "spraying": (seq % 10 < 4), # Periodic spraying demonstration
            "seq": seq
        }

        field_payload = {
            "node_id": "esp32_ground_sim",
            "lat": base_lat - 0.0003,
            "lon": base_lon - 0.0003,
            "temp_c": round(29.2 + math.sin(seq * 0.05) * 1.2, 1),
            "humidity_pct": round(58.0 + math.cos(seq * 0.05) * 2.0, 1),
            "soil_moisture_pct": round(43.5 + math.sin(seq * 0.1) * 0.8, 1)
        }

        try:
            requests.post(f"{SERVER_URL}/api/telemetry/drone", json=drone_payload, timeout=1)
            if seq % 4 == 0:
                requests.post(f"{SERVER_URL}/api/telemetry/field", json=field_payload, timeout=1)
            print(f"[TX Packet #{seq}] Drone @ ({drone_payload['lat']}, {drone_payload['lon']}) Alt: {drone_payload['alt']}m Bat: {battery}%")
        except Exception as e:
            print(f"[Error connecting to {SERVER_URL}] {e}")

        time.sleep(0.5)

if __name__ == "__main__":
    run_simulation()
