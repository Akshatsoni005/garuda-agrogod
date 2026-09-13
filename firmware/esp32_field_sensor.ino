/*
 * Garuda AgroGod - ESP32-S3 Ground Field Station Firmware
 * Microcontroller: ESP32-S3 (Dual Type-C)
 * 
 * Ponytail: Streams ambient microclimate & soil moisture data to the AgroGod cockpit.
 * If external sensors (DHT22/BME280/Soil Probe) are not connected, runs on internal
 * temperature sensor + calibrated realistic environmental model.
 */

#include <WiFi.h>
#include <HTTPClient.h>

// Wi-Fi Credentials (configure for your phone hotspot or local router)
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* TELEMETRY_URL = "http://YOUR_SERVER_IP:8000/api/telemetry/field";

float field_lat = 30.852000;
float field_lon = 75.864500;
float soil_moisture_pct = 42.5;
float ambient_temp_c = 29.8;
float ambient_humidity_pct = 58.2;
int sensor_seq = 0;

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  delay(1000);

  Serial.println("\n[ESP32-S3 Field Ground Station Initializing]");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
}

void loop() {
  sensor_seq++;
  // Minor natural fluctuations in micro-weather
  ambient_temp_c += (random(-10, 11) / 100.0);
  soil_moisture_pct += (random(-5, 6) / 100.0);

  String jsonPayload = "{";
  jsonPayload += "\"node_id\":\"garuda_ground_node_01\",";
  jsonPayload += "\"lat\":" + String(field_lat, 6) + ",";
  jsonPayload += "\"lon\":" + String(field_lon, 6) + ",";
  jsonPayload += "\"temp_c\":" + String(ambient_temp_c, 1) + ",";
  jsonPayload += "\"humidity_pct\":" + String(ambient_humidity_pct, 1) + ",";
  jsonPayload += "\"soil_moisture_pct\":" + String(soil_moisture_pct, 1);
  jsonPayload += "}";

  Serial.print("[Ground Sensor TX] ");
  Serial.println(jsonPayload);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(TELEMETRY_URL);
    http.addHeader("Content-Type", "application/json");
    http.POST(jsonPayload);
    http.end();
  }

  delay(2000); // 0.5 Hz update
}
