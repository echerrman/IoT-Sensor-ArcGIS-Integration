#!/usr/bin/env python3
"""Minimal standalone ArcGIS Pro script tool for sensor updates.

This file intentionally contains all runtime logic in one place.
It upserts AGOL features by sensor_id:
- Existing sensor: update attributes only (geometry unchanged).
- New sensor: require lat/lon and create feature at that location.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    import arcpy  # type: ignore
except Exception:  # pragma: no cover
    arcpy = None


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# -----------------------------------------------------------------------------
# Minimal configuration.
# Keep secrets out of git by editing these values only in your publish copy.
# -----------------------------------------------------------------------------
ARCGIS_REST_API_URL = "https://www.arcgis.com/sharing/rest/oauth2/token"
FEATURE_LAYER_URL="https://services1.arcgis.com/x5wCko8UnSi4h0CB/arcgis/rest/services/Temperature_Readings_Layer/FeatureServer/0"
OAUTH_CLIENT_ID = "CLIENT_ID"
OAUTH_CLIENT_SECRET = "CLIENT_SECRET"

SENSOR_ID_FIELD = "sensor_id"
TEMPERATURE_FIELD = "temperature_F"
HUMIDITY_FIELD = "humidity"
TIMESTAMP_FIELD = "last_updated"
LOCATION_NAME_FIELD = "location_name"

_TOKEN_CACHE: Dict[str, Any] = {"token": None, "expires_at": 0.0}


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normalize_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(raw_payload)

    # Accept either device_id or sensor_id from clients.
    if "device_id" not in payload and "sensor_id" in payload:
        payload["device_id"] = payload.get("sensor_id")

    if "temperature_F" not in payload and "temperatureF" in payload:
        payload["temperature_F"] = payload.get("temperatureF")
    if "humidity" not in payload and "humidity_pct" in payload:
        payload["humidity"] = payload.get("humidity_pct")

    if not payload.get("timestamp"):
        payload["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return payload


def validate_payload(payload: Dict[str, Any]) -> Optional[str]:
    required_fields = ("device_id", "temperature_F", "humidity")
    missing = [name for name in required_fields if name not in payload]
    if missing:
        return "Missing required fields: {}".format(", ".join(missing))

    if not is_number(payload.get("temperature_F")):
        return "temperature_F must be a number"
    if not is_number(payload.get("humidity")):
        return "humidity must be a number"

    humidity = float(payload["humidity"])
    if humidity < 0.0 or humidity > 100.0:
        return "humidity must be in range 0 to 100"

    return None


def validate_new_sensor_geometry(payload: Dict[str, Any]) -> Optional[str]:
    if "lat" not in payload or "lon" not in payload:
        return "New sensor_id requires numeric lat and lon in payload"

    if not is_number(payload.get("lat")) or not is_number(payload.get("lon")):
        return "lat and lon must be numbers"

    lat = float(payload["lat"])
    lon = float(payload["lon"])
    if lat < -90.0 or lat > 90.0:
        return "lat must be in range -90 to 90"
    if lon < -180.0 or lon > 180.0:
        return "lon must be in range -180 to 180"

    return None


def validate_new_sensor_metadata(payload: Dict[str, Any]) -> Optional[str]:
    location_name = str(payload.get("location_name", "")).strip()
    if not location_name:
        return "New sensor_id requires non-empty location_name in payload"
    return None


def ensure_configured() -> None:
    missing = []
    if not FEATURE_LAYER_URL.strip():
        missing.append("FEATURE_LAYER_URL")
    if not OAUTH_CLIENT_ID.strip():
        missing.append("OAUTH_CLIENT_ID")
    if not OAUTH_CLIENT_SECRET.strip():
        missing.append("OAUTH_CLIENT_SECRET")

    if missing:
        raise RuntimeError("Missing required config in enterprise_webtool.py: {}".format(", ".join(missing)))


def fetch_arcgis_token() -> Tuple[str, float]:
    payload = {
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "grant_type": "client_credentials",
        "f": "json",
    }

    response = requests.post(ARCGIS_REST_API_URL, data=payload, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise RuntimeError("ArcGIS auth error: {}".format(data["error"]))

    token = data.get("access_token")
    if not token:
        raise RuntimeError("ArcGIS auth response missing access_token")

    now = time.time()
    expires_in = data.get("expires_in")
    expires_at = now + float(expires_in) if expires_in else now + 1700.0

    expires_epoch_ms = data.get("expires")
    if isinstance(expires_epoch_ms, (int, float)) and expires_epoch_ms > 0:
        expires_at = float(expires_epoch_ms) / 1000.0

    return token, expires_at


def get_arcgis_token() -> str:
    now = time.time()
    cached_token = _TOKEN_CACHE.get("token")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0.0)

    if cached_token and now < (expires_at - 60.0):
        return str(cached_token)

    token, new_expires_at = fetch_arcgis_token()
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires_at"] = new_expires_at
    return token


def query_existing_objectid(sensor_id: str) -> Optional[int]:
    query_url = "{}/query".format(FEATURE_LAYER_URL.rstrip("/"))
    params = {
        "f": "json",
        "where": "{}='{}'".format(SENSOR_ID_FIELD, sensor_id.replace("'", "''")),
        "outFields": "OBJECTID,{}".format(SENSOR_ID_FIELD),
        "returnGeometry": "false",
        "token": get_arcgis_token(),
    }

    response = requests.get(query_url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise RuntimeError("ArcGIS query error: {}".format(data["error"]))

    features = data.get("features") or []
    if not features:
        return None

    attributes = features[0].get("attributes", {})
    return attributes.get("OBJECTID")


def apply_upsert(payload: Dict[str, Any]) -> None:
    object_id = query_existing_objectid(payload["device_id"])
    adds = []
    updates = []

    attributes = {
        SENSOR_ID_FIELD: payload["device_id"],
        TEMPERATURE_FIELD: payload["temperature_F"],
        HUMIDITY_FIELD: payload["humidity"],
        TIMESTAMP_FIELD: payload.get("timestamp"),
    }

    if "location_name" in payload and str(payload.get("location_name", "")).strip():
        attributes[LOCATION_NAME_FIELD] = str(payload["location_name"]).strip()

    if object_id is None:
        geometry_error = validate_new_sensor_geometry(payload)
        if geometry_error:
            raise RuntimeError(geometry_error)

        metadata_error = validate_new_sensor_metadata(payload)
        if metadata_error:
            raise RuntimeError(metadata_error)

        adds.append(
            {
                "attributes": attributes,
                "geometry": {
                    "x": float(payload["lon"]),
                    "y": float(payload["lat"]),
                    "spatialReference": {"wkid": 4326},
                },
            }
        )
    else:
        # Do not include geometry on updates so existing points never move.
        attributes["OBJECTID"] = object_id
        updates.append({"attributes": attributes})

    apply_url = "{}/applyEdits".format(FEATURE_LAYER_URL.rstrip("/"))
    request_body = {
        "f": "json",
        "adds": json.dumps(adds),
        "updates": json.dumps(updates),
        "token": get_arcgis_token(),
    }

    response = requests.post(apply_url, data=request_body, timeout=15)
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise RuntimeError("ArcGIS update error: {}".format(data["error"]))


def process_ingest(payload_json: str) -> Tuple[Dict[str, Any], int]:
    ensure_configured()

    try:
        raw_payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError as exc:
        return {"error": "Invalid JSON payload: {}".format(exc)}, 400

    payload = normalize_payload(raw_payload)
    validation_error = validate_payload(payload)
    if validation_error:
        return {"error": validation_error}, 400

    sensor_id = payload["device_id"]

    try:
        apply_upsert(payload)
    except Exception as exc:
        logging.exception("ArcGIS update failed")
        return {"error": "ArcGIS update failed: {}".format(exc)}, 500

    return {"status": "accepted", "device_id": sensor_id}, 202


def run_as_script_tool() -> int:
    if arcpy is None:
        print("arcpy is not available. Run inside ArcGIS Pro or use CLI mode.")
        return 1

    payload_json = arcpy.GetParameterAsText(0) or ""

    response, status_code = process_ingest(payload_json)
    response["status_code"] = status_code
    out_json = json.dumps(response)

    if status_code >= 400:
        arcpy.AddError(out_json)
    else:
        arcpy.AddMessage(out_json)

    try:
        arcpy.SetParameterAsText(1, out_json)
    except Exception:
        pass

    return 0 if status_code < 400 else 1


def run_as_cli(argv: List[str]) -> int:
    payload_json = argv[1] if len(argv) > 1 else "{}"
    response, status_code = process_ingest(payload_json)
    response["status_code"] = status_code
    print(json.dumps(response))
    return 0 if status_code < 400 else 1


if __name__ == "__main__":
    if arcpy is not None:
        raise SystemExit(run_as_script_tool())
    raise SystemExit(run_as_cli(sys.argv))
