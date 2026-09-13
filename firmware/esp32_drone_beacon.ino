/*
 * Garuda AgroGod - ESP32-S3 Drone Telemetry Beacon Firmware
 * Microcontroller: ESP32-S3 (Dual Type-C)
 * Framework: Arduino / ESP-IDF
 *
 * STATUS: TELEMETRY SIMULATOR
 * This firmware simulates autonomous patrol orbit over a crop grid.
 * It does NOT read real GPS, real battery ADC, or a real flight controller.
 * Coordinates and battery are software-generated for demonstration/prototyping.
 *
 * HARDWARE INTEGRATION PATH:
 *   Replace drone_lat/lon simulation loop with:
 *     - TinyGPS++ reading NMEA from GPS module (UART2)
 *   Replace battery_pct simulation with:
 *     - ADC read on battery voltage divider pin
 *   Replace vrt_spraying_active with:
 *     - GPIO read from Pixhawk MAVLink SERVO output
 *
 * Ponytail: Lightweight JSON telemetry broadcaster over standard HTTP/REST.
 * Connects to local Wi-Fi and pushes 6-DOF coordinates + VRT spray status to AgroGod Server.
 */

#include <WiFi.h>
#include <HTTPClient.h>

// Wi-Fi Credentials (configure for your phone hotspot or local router)
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

// Server Endpoint (IP of laptop running AgroGod backend)
const char* TELEMETRY_URL = "http://YOUR_SERVER_IP:8000/api/telemetry/drone";

// Starting coordinates (Punjab Wheat Belt, India)
float drone_lat = 30.852500;
float drone_lon = 75.865000;
float drone_alt = 12.5; // meters
int battery_pct = 99;
bool vrt_spraying_active = false;
int packet_seq = 0;

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  delay(1000);

  Serial.println("\n===========================================");
  Serial.println("  GARUDA AGROGOD - ESP32-S3 DRONE BEACON  ");
  Serial.println("===========================================");
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("[WiFi] Connecting to: ");
  Serial.println(WIFI_SSID);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected successfully!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Running in Autonomous Beacon Mode (Serial Simulation)");
  }
}

void loop() {
  packet_seq++;
  
  // Simulate autonomous patrol orbit across crop grid
  drone_lat += 0.00004 * cos(packet_seq * 0.1);
  drone_lon += 0.00004 * sin(packet_seq * 0.1);
  if (packet_seq % 50 == 0 && battery_pct > 10) {
    battery_pct -= 1;
  }

  // Construct compact JSON payload
  String jsonPayload = "{";
  jsonPayload += "\"device_id\":\"garuda_drone_alpha\",";
  jsonPayload += "\"seq\":" + String(packet_seq) + ",";
  jsonPayload += "\"lat\":" + String(drone_lat, 6) + ",";
  jsonPayload += "\"lon\":" + String(drone_lon, 6) + ",";
  jsonPayload += "\"alt\":" + String(drone_alt, 1) + ",";
  jsonPayload += "\"battery\":" + String(battery_pct) + ",";
  jsonPayload += "\"spraying\":" + String(vrt_spraying_active ? "true" : "false");
  jsonPayload += "}";

  Serial.print("[TX Telemetry] ");
  Serial.println(jsonPayload);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(TELEMETRY_URL);
    http.addHeader("Content-Type", "application/json");
    
    int httpResponseCode = http.POST(jsonPayload);
    if (httpResponseCode > 0) {
      digitalWrite(LED_BUILTIN, HIGH);
    } else {
      digitalWrite(LED_BUILTIN, LOW);
    }
    http.end();
  }

  delay(500); // 2 Hz telemetry stream
}
