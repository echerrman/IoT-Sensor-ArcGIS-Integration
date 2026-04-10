# IoT-Sensor-ArcGIS-Integration

Real-time IoT sensor integration for temperature and humidity data from Arduino devices through an ArcGIS Enterprise web tool into ArcGIS Online feature layers.

```
Arduino IoT Sensor (DHT22) -> ArcGIS Enterprise Web Tool -> ArcGIS Online Feature Layer
```

## Prerequisites

- Python 3.8+
- Arduino IDE 2.x
- ESP32 or Arduino Uno R4 WiFi + DHT22 sensor
- ArcGIS Online account with feature layer
- ArcGIS Enterprise Server access (for publishing)

## Quick Start

### 1) Configure the script tool

Edit [enterprise_webtool.py](enterprise_webtool.py) and set:

```python
FEATURE_LAYER_URL = "https://services1.arcgis.com/.../FeatureServer/0"
OAUTH_CLIENT_ID = "your-oauth-client-id"
OAUTH_CLIENT_SECRET = "your-oauth-client-secret"
```

### 2) Publish as ArcGIS web tool

1. Open ArcGIS Pro
2. Create a new Script Tool → point to [enterprise_webtool.py](enterprise_webtool.py)
3. Define two parameters (in order):
   - **Input** (String): `payload_json`
   - **Output** (String): `response_json`
4. Test locally in the Geoprocessing pane with a sample JSON payload
5. Right-click tool → **Share as Web Tool** (Synchronous execution)
6. Copy the published execute endpoint URL

### 3) Hardware setup

**Wire the DHT22 sensor to your board:**

| DHT22 Pin | Board Pin (ESP32) | Board Pin (Uno R4) | Notes |
|-----------|------------------|--------------------|-------|
| VCC (+)   | 3.3V or 5V       | 5V                 | Power (check DHT22 datasheet) |
| GND (-)   | GND              | GND                | Ground |
| Data      | GPIO 4           | Digital 2          | Single-wire data (add 4.7kΩ pull-up resistor) |

### 4) Arduino IDE: Install required libraries

1. Open **Arduino IDE 2.x**
2. Go to **Sketch** → **Include Library** → **Manage Libraries**
3. Search for and install:
   - **DHT sensor library** by Adafruit (v1.4.x or later)
   - **Adafruit Unified Sensor** (dependency for DHT library)
   - **ArduinoJson** by Benoit Blanchon (v6.x or later) — for JSON serialization
4. For ESP32 only: **ESP32 board support** may already be installed (check Boards Manager if needed)
5. For Uno R4: **Arduino Uno R4 Renesas** board support (install via Boards Manager if needed)

### 5) Configure and upload the sketch

1. Choose the sketch for your board:
   - **ESP32/ESP8266**: [devices/esp32_dht22_http_post.ino](devices/esp32_dht22_http_post.ino)
   - **Arduino Uno R4 WiFi**: [devices/uno_r4_dht22_http_post.ino](devices/uno_r4_dht22_http_post.ino)

2. Open the sketch in Arduino IDE

3. **Edit these constants** at the top of the file:

   ```cpp
   // WiFi configuration
   const char* WIFI_SSID = "your-network-name";
   const char* WIFI_PASS = "your-wifi-password";
   
   // ArcGIS server endpoint (get this from step 2 above)
   const char* INGEST_HOST = "webgis.yourserver.com";
   const char* ENDPOINT_PATH = "/arcgis/rest/services/YourFolder/YourTool/GPServer/enterprise_webtool/execute";
   
   // Sensor identifier (must match a sensor_id in your ArcGIS layer)
   const char* SENSOR_ID = "sensor_1";
   
   // DHT22 data pin (adjust to match your wiring)
   #define DHTPIN 4        // ESP32
   // #define DHTPIN 2     // Uno R4 WiFi
   
   // Post interval (milliseconds)
   const unsigned long LOOP_INTERVAL_MS = 60000;  // 60 seconds
   ```

4. **Select your board:**
   - **File** → **Preferences** → note the sketchbook location
   - **Tools** → **Board** → select your board (e.g., "ESP32 Dev Module" or "Arduino Uno R4 WiFi")
   - **Tools** → **Port** → select the COM port your device is plugged into

5. **Upload the sketch:**
   - Click the **Upload** button (right arrow icon) or **Sketch** → **Upload**
   - Wait for "Upload successful" message in the status bar

6. **Open the Serial Monitor** (**Tools** → **Serial Monitor**, baud rate 115200):
   - You should see WiFi connection attempts and periodic POST requests
   - Look for messages like: `POST to /...execute sent, response: 202` (success)

### 6) Device operation

Once uploaded, the sketch will:
1. Connect to your WiFi network (watch Serial Monitor for connection log)
2. Every 60 seconds (configurable): read temperature & humidity from DHT22
3. POST JSON payload to the published tool endpoint
4. Receive response from ArcGIS
5. Return to sleep until the next 60-second interval
6. Repeat indefinitely

**Expected workflow:**
- Sensor reads: ~22.5°C → converts to Fahrenheit → 72.5°F
- Payload sent to web tool with `device_id`, `temperature_F`, `humidity`
- Tool receives, queries ArcGIS for `sensor_1` feature
- If found: updates attributes → feature layer reflects new reading ~1 second later
- If not found: returns 400 error asking for `location_name + lat + lon` (for first-time setup)

### 7) Payload format reference

During normal operation, the device sends payloads like this:

**Existing sensor update:**
```json
{
  "device_id": "sensor_1",
  "temperature_F": 72.5,
  "humidity": 20.0
}
```
(timestamp auto-generated if omitted; geometry never changes)

**New sensor creation** (first time only):
```json
{
  "device_id": "sensor_2",
  "temperature_F": 71.2,
  "humidity": 33.0,
  "location_name": "Cooper_Library_2",
  "lat": 34.680649,
  "lon": -82.849503
}
```
(required: `location_name`, `lat`, `lon` for new sensors when feature doesn't exist; these fields are ignored for existing sensors)

### 8) Local Testing (without device)

Test the script directly without running any Arduino:

```powershell
python enterprise_webtool.py '{"device_id":"sensor_1","temperature_F":72.4,"humidity":44.1}'
```

Expected output: `{"status": "accepted", "device_id": "sensor_1", "status_code": 202}`

### 9) Troubleshooting

**Arduino doesn't connect to WiFi:**
- Check WIFI_SSID and WIFI_PASS are correct
- Watch Serial Monitor at 115200 baud — look for connection messages
- Ensure device is in range of WiFi network
- Try rebooting the device (unplug/replug USB or press reset button)

**POST returns 400 (Bad Request):**
- Check `ENDPOINT_PATH` matches the exact published tool endpoint (copy from ArcGIS Server Manager)
- Verify `INGEST_HOST` is reachable from the device (ping from device, check firewall)
- Ensure `DEVICE_ID` matches a sensor_id that exists in your ArcGIS feature layer (or provide `location_name + lat + lon` for new sensors)

**Feature layer not updating:**
- Check `FEATURE_LAYER_URL` in [enterprise_webtool.py](enterprise_webtool.py) is correct
- Verify `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` have write permissions to the feature layer
- Monitor ArcGIS feature service activity logs for errors

**Readings are duplicate or too old:**
- Increase `POST_INTERVAL_MS` if you're getting rate-limited (429 errors)
- Decrease `POST_INTERVAL_MS` if you want more frequent updates (but keep ≥30 seconds to avoid service throttling)
- Check device clock is roughly synchronized (NTP sync happens at boot; check Serial Monitor for timestamp)

## Reference: Behavior & Semantics

### Upsert Logic

- **New sensor**: If a POST arrives with a `device_id` that doesn't exist in the ArcGIS layer, the tool requires `location_name`, `lat`, `lon` in the payload. It will create a new feature at that location.
- **Existing sensor**: If a POST arrives with a `device_id` that already exists, the tool updates only `temperature_F`, `humidity`, and `last_updated`. The geometry and `location_name` are **never modified** on updates.

### Field Aliases

The tool accepts multiple field names for compatibility with different client types:
- `device_id` ↔ `sensor_id`
- `temperature_F` ↔ `temperatureF`
- `humidity` ↔ `humidity_pct`

### Timestamps

If `timestamp` is omitted from the payload, the tool auto-generates the current UTC time in format: `YYYY-MM-DDTHH:MM:SSZ`

## Reference: Getting the Published Endpoint URL

After you publish the tool in ArcGIS Pro, you need to find its public endpoint URL to put in the Arduino sketch.

1. Open **ArcGIS Server Manager** in a web browser (usually: `https://webgis.yourserver.com/arcgisadmin`)
2. Log in with your Enterprise Server admin account
3. Navigate to **Services** → find your published tool
4. Click the tool name → view **Rest Endpoint**
5. You'll see a URL like:
   ```
   https://webgis.yourserver.com/arcgis/rest/services/YourFolder/YourToolName/GPServer/enterprise_webtool
   ```
6. Append `/execute` to get the POST endpoint:
   ```
   https://webgis.yourserver.com/arcgis/rest/services/YourFolder/YourToolName/GPServer/enterprise_webtool/execute
   ```
7. Copy this full URL into the Arduino sketch's `ENDPOINT_PATH` constant
8. Also copy the host part (`webgis.yourserver.com`) into `INGEST_HOST`
