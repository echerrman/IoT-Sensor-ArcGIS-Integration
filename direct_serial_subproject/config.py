"""Configuration for the direct serial sensor subproject."""

import os
from dotenv import load_dotenv

load_dotenv()

# Local runtime file for latest readings by sensor_id.
JSON_FILE = "latest_temperature.json"

# ArcGIS OAuth token endpoint and app credentials.
ARCGIS_REST_API_URL = "https://www.arcgis.com/sharing/rest/oauth2/token"
OAUTH_CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET", "")
OAUTH_GRANT_TYPE = "client_credentials"

# Target feature layer (set in .env, keep secrets and tenant URLs out of git).
FEATURE_LAYER_URL = os.getenv("FEATURE_LAYER_URL", "")
TEMPERATURE_FIELD = "temperature_F"
SENSOR_ID_FIELD = "sensor_id"
LAST_RECORDED_FIELD = "last_updated"

# Poll/update cadence in seconds.
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", "3"))

# Sensor map: each known sensor_id with COM settings and ArcGIS ObjectID mapping.
SENSORS = {
    "sensor_1": {
        "com_port": "COM7",
        "baud_rate": 9600,
        "timeout": 2,
        "arcgis_object_id": 1,
    },
}

# Logging level: DEBUG, INFO, WARNING, ERROR.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
