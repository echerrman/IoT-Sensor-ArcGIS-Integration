# Direct Serial Sensor Subproject

This subproject preserves the original direct-connected receiver workflow:

- Remote field units publish readings as `sensor_id:temperature_F`
- A local USB-connected receiver forwards serial lines to this Python app
- Python stores latest values in `latest_temperature.json`
- Python batch-updates an ArcGIS FeatureServer layer by ObjectID

## What this is for

Use this when you want a local machine (laptop or desktop) to act as the ingest bridge for directly connected serial receiver hardware.

If you need internet-first ingest from distributed WiFi sensors, use the root-level published web tool flow instead.

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Create local `.env`

Copy `.env.example` to `.env` in this folder and set values:

```
OAUTH_CLIENT_ID=your_oauth_client_id
OAUTH_CLIENT_SECRET=your_oauth_client_secret
FEATURE_LAYER_URL=https://servicesX.arcgis.com/.../FeatureServer/0
UPDATE_INTERVAL=3
LOG_LEVEL=INFO
```

Do not commit `.env`.

### 3) Configure known sensors

Edit `config.py` `SENSORS` mapping:

```python
SENSORS = {
    "sensor_1": {
        "com_port": "COM7",
        "baud_rate": 9600,
        "timeout": 2,
        "arcgis_object_id": 1,
    },
}
```

Each `sensor_id` must match what the field unit transmits, and `arcgis_object_id` must match the target feature in the ArcGIS layer.

### 4) Run

```bash
python main.py
```

Press `Ctrl+C` to stop.

## ArcGIS Layer Requirements

Feature layer should include these fields:

- `sensor_id` (text)
- `temperature_F` (number)
- `last_updated` (date or text)

One feature per sensor is expected, mapped by `arcgis_object_id` in `config.py`.

## Files

- `main.py`: orchestrator loop and startup/shutdown
- `sensor.py`: serial reader + local JSON datastore
- `arcgis_client.py`: OAuth token + FeatureServer applyEdits updates
- `config.py`: local configuration and sensor mapping
- `arduino_code/`: legacy field/receiver sketches for this direct setup

## Security Notes

- Secrets are loaded from `.env` only
- `.env` and `latest_temperature.json` are gitignored in this subproject
- No OAuth secrets are hardcoded in Python files

## Add a New Sensor

1. Program field unit to send `sensor_X:<temp_f>`
2. Add `sensor_X` entry to `SENSORS` in `config.py`
3. Create/update corresponding ArcGIS feature and ObjectID mapping
4. Restart `main.py`

## Troubleshooting

- Serial issues: verify COM port and baud rate
- No readings: confirm serial line format `sensor_id:temperature_F`
- ArcGIS errors: verify `.env` credentials and `FEATURE_LAYER_URL`
- Skipped sensors: verify incoming `sensor_id` exists in `SENSORS`
