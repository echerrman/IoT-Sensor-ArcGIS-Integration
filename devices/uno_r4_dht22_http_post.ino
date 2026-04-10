/*
  DHT22 -> HTTP(S) POST sketch for Arduino Uno R4 WiFi.

  Required libraries:
  - WiFiS3 (built into Uno R4 core)
  - ArduinoHttpClient
  - DHT sensor library by Adafruit

  Sends JSON payload to ArcGIS GP execute endpoint.
*/

#include <WiFiS3.h>
#include <ArduinoHttpClient.h>
#include <DHT.h>
#include <time.h>

// ---------------- Configuration ----------------
// Required user input (EDIT THESE BEFORE UPLOAD)
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* SENSOR_ID = "sensor_10";
const char* LOCATION_NAME = "LOCATION_NAME";
const float SENSOR_LAT = 34.680649f;  // Replace with your sensor's latitude
const float SENSOR_LON = -82.849503f; // Replace with your sensor's longitude

// Wiring pin configuration (EDIT IF YOUR WIRING IS DIFFERENT)
#define DHTPIN 2
#define DHTTYPE DHT22

// Preconfigured endpoint and request settings
const char* INGEST_HOST = "webgis.coe.clemson.edu";
const uint16_t INGEST_PORT = 443;
const bool USE_HTTPS = true;                  // HTTPS using WiFiSSLClient
const char* ENDPOINT_PATH = "/arcgisadmin/rest/services/Temp_Sensors/temperature_sensors_webtool/GPServer/ServerIngest/execute";
const bool USE_ARCGIS_GP_EXECUTE = true;     // send x-www-form-urlencoded to GP execute endpoint
const bool INCLUDE_SETUP_FIELDS = true;       // Include location_name/lat/lon on every payload.
                                              // New sensors are created; existing sensors keep geometry unchanged.

// Upload cadence
const unsigned long LOOP_INTERVAL_MS = 60000; // 60 seconds between sensor uploads.
// ----------------------------------------------------
DHT dht(DHTPIN, DHTTYPE);

WiFiClient wifiClient;
WiFiSSLClient wifiSslClient;

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

// Establish WiFi connection to the network specified in configuration.
// Returns true if connection successful, false if timeout (20 seconds).
bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;

  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');

    if (millis() - start > 20000) {
      Serial.println(" timeout");
      return false;
    }
  }

  Serial.println(" connected");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
  return true;
}

String isoTimestampUTC() {
  unsigned long epoch = WiFi.getTime();
  if (epoch > 100000) {
    time_t now = static_cast<time_t>(epoch);
    struct tm* tm_utc = gmtime(&now);
    char buf[25];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", tm_utc);
    return String(buf);
  }

  unsigned long seconds = millis() / 1000UL;
  char fallback[30];
  snprintf(fallback, sizeof(fallback), "uptime-%lus", seconds);
  return String(fallback);
}

// Build JSON payload with sensor_id, temperature (Fahrenheit), and humidity.
// Returns formatted JSON string ready for POST request.
String buildPayload(float tempF, float humidity, const String& ts) {
  String payload = String("{\"sensor_id\":\"") + SENSOR_ID +
                   "\",\"temperature_F\":" + String(tempF, 2) +
                   ",\"humidity\":" + String(humidity, 2) +
                   ",\"timestamp\":\"" + ts + "\"";

  if (INCLUDE_SETUP_FIELDS) {
    payload += ",\"location_name\":\"" + String(LOCATION_NAME) + "\"";
    payload += ",\"lat\":" + String(SENSOR_LAT, 6);
    payload += ",\"lon\":" + String(SENSOR_LON, 6);
  }

  payload += "}";
  return payload;
}

// Send HTTP or HTTPS POST request to the configured ArcGIS endpoint.
// Returns true if server responds with 2xx status code, false otherwise.
bool sendPostRequest(const String& payload) {
  String body = payload;
  String contentType = "application/json";

  if (USE_ARCGIS_GP_EXECUTE) {
    body = "f=json&payload_json=" + urlEncode(payload);
    contentType = "application/x-www-form-urlencoded";
  }

  if (USE_HTTPS) {
    HttpClient client(wifiSslClient, INGEST_HOST, INGEST_PORT);
    client.connectionKeepAlive();

    client.beginRequest();
    client.post(ENDPOINT_PATH);
    client.sendHeader("Content-Type", contentType);
    client.sendHeader("Content-Length", body.length());
    client.beginBody();
    client.print(body);
    client.endRequest();

    int statusCode = client.responseStatusCode();
    String body = client.responseBody();

    Serial.print("HTTP status: ");
    Serial.println(statusCode);
    if (statusCode < 200 || statusCode >= 300) {
      Serial.print("Response body: ");
      Serial.println(body);
      return false;
    }
    return true;
  }

  HttpClient client(wifiClient, INGEST_HOST, INGEST_PORT);
  client.connectionKeepAlive();

  client.beginRequest();
  client.post(ENDPOINT_PATH);
  client.sendHeader("Content-Type", contentType);
  client.sendHeader("Content-Length", body.length());
  client.beginBody();
  client.print(body);
  client.endRequest();

  int statusCode = client.responseStatusCode();
  String body = client.responseBody();

  Serial.print("HTTP status: ");
  Serial.println(statusCode);
  if (statusCode < 200 || statusCode >= 300) {
    Serial.print("Response body: ");
    Serial.println(body);
    return false;
  }
  return true;
}

// Post one sensor reading.
// Returns true on 2xx response, false otherwise.
bool postReading(float tempF, float humidity, const String& ts) {
  String payload = buildPayload(tempF, humidity, ts);
  if (!connectWiFi()) return false;

  if (sendPostRequest(payload)) {
    Serial.println("POST ok");
    return true;
  }

  Serial.println("POST failed");
  return false;
}

// Initialize serial communications, WiFi module, and DHT22 sensor.
// Runs once at Arduino startup.
void setup() {
  Serial.begin(115200);
  delay(200);

  if (WiFi.status() == WL_NO_MODULE) {
    Serial.println("WiFi module not detected.");
    while (true) {
      delay(1000);
    }
  }

  dht.begin();
  connectWiFi();
}

// Main execution loop: read DHT22 sensor, convert to Fahrenheit, and POST to server.
// Repeats every LOOP_INTERVAL_MS milliseconds (default 60 seconds).
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

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
