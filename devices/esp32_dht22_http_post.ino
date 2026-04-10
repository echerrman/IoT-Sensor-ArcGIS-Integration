/*
  Minimal DHT22 -> HTTP(S) POST sketch for ESP8266/ESP32.
  Fill in WiFi/server/device placeholders before uploading.
*/

#if defined(ESP8266)
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecureBearSSL.h>
#elif defined(ESP32)
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#else
#error "This sketch supports only ESP8266 or ESP32"
#endif

#include <DHT.h>
#include <time.h>

// ---------------- Configuration ----------------
// Required user input (EDIT THESE BEFORE UPLOAD)
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* SENSOR_ID = "sensor_1";
const char* LOCATION_NAME = "LOCATION_NAME";
const float SENSOR_LAT = 34.680649f;  // Replace with your sensor's latitude
const float SENSOR_LON = -82.849503f; // Replace with your sensor's longitude

// Wiring pin configuration (EDIT IF YOUR WIRING IS DIFFERENT)
#define DHTPIN 4
#define DHTTYPE DHT22

// Preconfigured endpoint and request settings
const char* INGEST_HOST = "webgis.coe.clemson.edu";
const uint16_t INGEST_PORT = 443;
const bool USE_HTTPS = true;
const char* ENDPOINT_PATH = "/arcgisadmin/rest/services/Temp_Sensors/temperature_sensors_webtool/GPServer/ServerIngest/execute";
const bool USE_ARCGIS_GP_EXECUTE = true;   // send x-www-form-urlencoded to GP execute endpoint
const bool INCLUDE_SETUP_FIELDS = false;    // Include location_name/lat/lon on every payload.
                                            // New sensors are created; existing sensors keep geometry unchanged.

// Upload cadence
const unsigned long LOOP_INTERVAL_MS = 60000; // 60 seconds between sensor uploads.
// ----------------------------------------------------
DHT dht(DHTPIN, DHTTYPE);

String urlEncode(const String& input) {
  String output;
  char hex[4];
  for (size_t i = 0; i < input.length(); i++) {
    unsigned char c = static_cast<unsigned char>(input.charAt(i));
    bool safe = (c >= 'a' && c <= 'z') ||
                (c >= 'A' && c <= 'Z') ||
                (c >= '0' && c <= '9') ||
                c == '-' || c == '_' || c == '.' || c == '~';
    if (safe) {
      output += static_cast<char>(c);
    } else {
      snprintf(hex, sizeof(hex), "%%%02X", c);
      output += hex;
    }
  }
  return output;
}

// Generate ISO 8601 UTC timestamp from NTP-synchronized system time.
// Returns formatted string like "2026-03-02T14:30:00Z".
String isoTimestampUTC() {
  time_t now = time(nullptr);
  if (now < 100000) return "1970-01-01T00:00:00Z";
  struct tm* tm_utc = gmtime(&now);
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", tm_utc);
  return String(buf);
}

// Post one sensor reading to the configured endpoint.
// Returns true for 2xx responses and false otherwise.
bool postReading(float tempF, float humidity, const String& ts) {
  String url = String(USE_HTTPS ? "https://" : "http://") + INGEST_HOST + ":" + INGEST_PORT + ENDPOINT_PATH;
  String payloadJson = "{\"sensor_id\":\"" + String(SENSOR_ID) +
                       "\",\"temperature_F\":" + String(tempF, 2) +
                       "\",\"humidity\":" + String(humidity, 2) +
                       ",\"timestamp\":\"" + ts + "\"";

  if (INCLUDE_SETUP_FIELDS) {
    payloadJson += ",\"location_name\":\"" + String(LOCATION_NAME) + "\"";
    payloadJson += ",\"lat\":" + String(SENSOR_LAT, 6);
    payloadJson += ",\"lon\":" + String(SENSOR_LON, 6);
  }
  payloadJson += "}";

  String body = payloadJson;
  if (USE_ARCGIS_GP_EXECUTE) {
    body = "f=json&payload_json=" + urlEncode(payloadJson);
  }

  int httpCode = -1;

#if defined(ESP8266)
    HTTPClient http;
    if (USE_HTTPS) {
      BearSSL::WiFiClientSecure client;
      client.setInsecure();  // Demo only
      if (http.begin(client, url)) {
        if (USE_ARCGIS_GP_EXECUTE) {
          http.addHeader("Content-Type", "application/x-www-form-urlencoded");
        } else {
          http.addHeader("Content-Type", "application/json");
        }
        httpCode = http.POST(body);
        http.end();
      }
    } else {
      WiFiClient client;
      if (http.begin(client, url)) {
        if (USE_ARCGIS_GP_EXECUTE) {
          http.addHeader("Content-Type", "application/x-www-form-urlencoded");
        } else {
          http.addHeader("Content-Type", "application/json");
        }
        httpCode = http.POST(body);
        http.end();
      }
    }
#else
    HTTPClient http;
    if (USE_HTTPS) {
      WiFiClientSecure client;
      client.setInsecure();  // Demo only
      if (http.begin(client, url)) {
        if (USE_ARCGIS_GP_EXECUTE) {
          http.addHeader("Content-Type", "application/x-www-form-urlencoded");
        } else {
          http.addHeader("Content-Type", "application/json");
        }
        httpCode = http.POST(body);
        http.end();
      }
    } else {
      WiFiClient client;
      if (http.begin(client, url)) {
        if (USE_ARCGIS_GP_EXECUTE) {
          http.addHeader("Content-Type", "application/x-www-form-urlencoded");
        } else {
          http.addHeader("Content-Type", "application/json");
        }
        httpCode = http.POST(body);
        http.end();
      }
    }
#endif

  if (httpCode >= 200 && httpCode < 300) {
    Serial.printf("POST ok: %d\n", httpCode);
    return true;
  }

  Serial.printf("POST failed (code=%d)\n", httpCode);
  return false;
}

// Establish WiFi connection to the network specified in configuration.
// Blocks until connection is established.
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" connected");
}

// Initialize serial communications, DHT22 sensor, WiFi, and NTP time sync.
// Runs once at Arduino startup.
void setup() {
  Serial.begin(115200);
  delay(100);
  dht.begin();
  connectWiFi();
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}

// Main execution loop: read DHT22 sensor, convert to Fahrenheit, and POST to server.
// Repeats every LOOP_INTERVAL_MS milliseconds (default 60 seconds).
void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  float humidity = dht.readHumidity();
  float tempC = dht.readTemperature();

  if (isnan(humidity) || isnan(tempC)) {
    Serial.println("DHT22 read failed");
    delay(LOOP_INTERVAL_MS);
    return;
  }

  float tempF = (tempC * 9.0f / 5.0f) + 32.0f;
  String ts = isoTimestampUTC();
  postReading(tempF, humidity, ts);

  delay(LOOP_INTERVAL_MS);
}
