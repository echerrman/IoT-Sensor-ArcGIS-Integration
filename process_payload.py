#!/usr/bin/env python3
"""
process_payload.py

Refactored from ingest_server.py into a script-tool friendly module.

Usage inside ArcGIS Pro (script tool):
 - Use arcpy.GetParameterAsText(...) to supply parameters:
     - payload_json_or_path (string): JSON payload text OR path to a JSON file
     - devices_yaml_path (string): path to devices.yaml
     - feature_layer_url (string): feature layer REST URL (where to call applyEdits)
     - token_url (string): token endpoint URL (ArcGIS token/OAuth)
     - oauth_client_id (string)
     - oauth_client_secret (string)
     - latest_out_path (string): path to write latest_temperature.json (optional)
     - write_latest (string/boolean): "True"/"False"
     - timeout_seconds (string/int): optional HTTP timeout

Usage from CLI:
    python process_payload.py --payload-file ./sample.json --devices devices.example.yaml \
        --feature-layer https://.../FeatureServer/0 --token-url https://.../oauth2/token \
        --client-id ID --client-secret SECRET --latest ./latest_temperature.json --write-latest

The script prints a JSON result to stdout and returns an exit code (0 on success).
"""

from __future__ import annotations
import os
import sys
import json
import yaml
import time
import logging
import argparse
from typing import Dict, Any, Optional, Tuple
import requests

# Try to import arcpy when running inside ArcGIS Pro; if not available, proceed without it.
try:
    import arcpy  # type: ignore
    HAS_ARCPY = True
except Exception:
    HAS_ARCPY = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------
# Utility / core functions
# ---------------------------
def load_json_or_file(input_str: str) -> Dict[str, Any]:
    """Accept either a JSON string or a path to a JSON file; return dict."""
    if os.path.exists(input_str):
        with open(input_str, "r", encoding="utf-8") as fh:
            return json.load(fh)
    else:
        return json.loads(input_str)


def load_devices_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def fetch_arcgis_token(token_url: str, client_id: str, client_secret: str, timeout: int = 10) -> str:
    """
    Obtain token via OAuth2 client_credentials token endpoint.
    The exact params may vary by ArcGIS Enterprise setup; adapt as needed.
    """
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(token_url, data=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise RuntimeError(f"No access token found in token response: {data}")
    return token


def call_apply_edits(feature_layer_url: str, edits: Dict[str, Any], token: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Post to the layer's applyEdits endpoint. 'edits' is a dict with keys like addFeatures/updateFeatures/deleteFeatures.
    """
    url = feature_layer_url.rstrip("/") + "/applyEdits"
    params = {
        "f": "json",
        "token": token
    }
    # applyEdits expects form-data with JSON strings for keys
    data = {}
    for k, v in edits.items():
        data[k] = json.dumps(v)
    r = requests.post(url, params=params, data=data, timeout=timeout)
    r.raise_for_status()
    return r.json()


def build_feature_from_payload(payload: Dict[str, Any], device_meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert incoming payload and device registry metadata into a feature dict suitable for applyEdits addFeatures/updateFeatures.
    Assumes payload contains at least temperature, humidity, timestamp and optionally lat/lon if not in device_meta.
    Adjust to match your feature layer's field names.
    """
    # Example mapping, adapt field names to your hosted feature layer
    attributes = {}
    attributes["sensor_id"] = payload.get("sensor_id") or device_meta.get("id")
    attributes["temperatureF"] = payload.get("temperatureF") or payload.get("temperature") or None
    attributes["humidity"] = payload.get("humidity")
    # Use device registry for lat/lon if needed
    lon = payload.get("lon") or device_meta.get("lon")
    lat = payload.get("lat") or device_meta.get("lat")
    # timestamp handling: attempt ISO string or epoch (seconds)
    ts = payload.get("timestamp") or payload.get("time") or int(time.time())
    attributes["timestamp"] = ts

    feature = {
        "attributes": attributes
    }
    if lat is not None and lon is not None:
        feature["geometry"] = {"x": float(lon), "y": float(lat)}
    return feature


def write_latest_reading(latest_path: str, payload: Dict[str, Any]):
    try:
        with open(latest_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except Exception as ex:
        logger.warning("Failed to write latest reading to %s: %s", latest_path, ex)


# ---------------------------
# High-level process function
# ---------------------------
def process_payload(
    payload: Dict[str, Any],
    devices_path: str,
    feature_layer_url: str,
    token_url: str,
    oauth_client_id: str,
    oauth_client_secret: str,
    latest_out_path: Optional[str] = None,
    write_latest: bool = False,
    timeout_seconds: int = 15,
) -> Dict[str, Any]:
    """
    Process a single payload dict:
      - validate payload against devices registry
      - build feature(s)
      - call applyEdits on the target feature layer
      - optionally write latest_out_path
    Returns a result dict with keys: success(bool), message(str), applyEdits_result(dict)
    """
    result: Dict[str, Any] = {"success": False, "message": "", "applyEdits_result": None}

    # Load device registry
    if not os.path.exists(devices_path):
        result["message"] = f"Devices file not found: {devices_path}"
        logger.error(result["message"])
        return result

    devices = load_devices_yaml(devices_path) or {}
    # devices.yaml expected structure sample: { devices: { "sensor_id1": {id:...,lat:...,lon:...}, ... } }
    # adapt lookup strategy to your devices.example.yaml structure
    sensor_id = payload.get("sensor_id") or payload.get("id")
    if not sensor_id:
        result["message"] = "Payload missing sensor_id"
        logger.error(result["message"])
        return result

    device_meta = devices.get(sensor_id) or {}
    if not device_meta:
        logger.warning("Sensor id '%s' not found in devices registry", sensor_id)

    # Build feature(s)
    feature = build_feature_from_payload(payload, device_meta)

    # Acquire token
    try:
        token = fetch_arcgis_token(token_url, oauth_client_id, oauth_client_secret, timeout=timeout_seconds)
    except Exception as ex:
        result["message"] = f"Failed to fetch token: {ex}"
        logger.exception(result["message"])
        return result

    # Prepare edits: we will use addFeatures for history; for current reading you might update by sensor_id
    # Example: add to history layer (single feature in this example)
    edits = {"addFeatures": [feature]}

    try:
        apply_resp = call_apply_edits(feature_layer_url, edits, token, timeout=timeout_seconds)
    except Exception as ex:
        result["message"] = f"applyEdits failed: {ex}"
        logger.exception(result["message"])
        return result

    result["applyEdits_result"] = apply_resp
    # Heuristic success detection
    if isinstance(apply_resp, dict) and any(k in apply_resp for k in ("addResults", "updateResults", "deleteResults")):
        result["success"] = True
        result["message"] = "applyEdits succeeded"
    else:
        # Some services return success structures under different keys
        if "error" in apply_resp:
            result["message"] = f"applyEdits error: {apply_resp.get('error')}"
        else:
            result["message"] = "applyEdits returned unexpected response"
    # Optionally write latest
    if write_latest and latest_out_path:
        try:
            write_latest_reading(latest_out_path, payload)
        except Exception:
            logger.exception("Failed to write latest reading")

    return result


# ---------------------------
# Script entrypoints
# ---------------------------
def run_with_arcpy():
    """Read parameters via arcpy.GetParameterAsText and call process_payload."""
    # Define parameters order to match script tool parameter definitions in ArcGIS Pro
    payload_in = arcpy.GetParameterAsText(0)         # payload JSON string OR path
    devices_yaml = arcpy.GetParameterAsText(1)      # devices.yaml path
    feature_layer_url = arcpy.GetParameterAsText(2) # feature layer REST URL
    token_url = arcpy.GetParameterAsText(3)         # token endpoint
    client_id = arcpy.GetParameterAsText(4)
    client_secret = arcpy.GetParameterAsText(5)
    latest_out_path = arcpy.GetParameterAsText(6) or None
    write_latest = arcpy.GetParameterAsText(7).lower() in ("true", "1", "yes")
    timeout_seconds = int(arcpy.GetParameterAsText(8) or 15)

    payload_dict = load_json_or_file(payload_in)
    result = process_payload(
        payload=payload_dict,
        devices_path=devices_yaml,
        feature_layer_url=feature_layer_url,
        token_url=token_url,
        oauth_client_id=client_id,
        oauth_client_secret=client_secret,
        latest_out_path=latest_out_path,
        write_latest=write_latest,
        timeout_seconds=timeout_seconds,
    )
    # Set ArcGIS script tool outputs (if desired)
    # Write result to a text file param or use arcpy.SetParameter if you defined output params
    arcpy.AddMessage(json.dumps(result))
    # Optionally set a boolean output parameter for success (if you create one)
    # arcpy.SetParameter(9, str(result["success"]))
    return result


def run_with_cli(argv=None):
    parser = argparse.ArgumentParser(description="Process sensor payload and write to ArcGIS feature layer")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--payload-file", help="Path to JSON file containing payload")
    g.add_argument("--payload-json", help="Payload JSON string")
    parser.add_argument("--devices", required=True, help="Path to devices.yaml")
    parser.add_argument("--feature-layer", required=True, help="Feature layer REST URL (e.g. https://.../FeatureServer/0)")
    parser.add_argument("--token-url", required=True, help="Token endpoint URL")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--latest", help="Path to write latest_temperature.json (optional)")
    parser.add_argument("--write-latest", action="store_true", help="Whether to write latest file")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args(argv)

    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    else:
        payload = json.loads(args.payload_json)

    result = process_payload(
        payload=payload,
        devices_path=args.devices,
        feature_layer_url=args.feature_layer,
        token_url=args.token_url,
        oauth_client_id=args.client_id,
        oauth_client_secret=args.client_secret,
        latest_out_path=args.latest,
        write_latest=args.write_latest,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(result, indent=2))
    if result.get("success"):
        sys.exit(0)
    else:
        sys.exit(2)


if __name__ == "__main__":
    if HAS_ARCPY:
        run_with_arcpy()
    else:
        run_with_cli()