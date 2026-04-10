"""ArcGIS OAuth and FeatureServer update helpers (requests-only)."""

import json
import logging
import time
from typing import Dict, Optional

import requests

from config import (
    ARCGIS_REST_API_URL,
    FEATURE_LAYER_URL,
    LAST_RECORDED_FIELD,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_GRANT_TYPE,
    TEMPERATURE_FIELD,
)

logger = logging.getLogger(__name__)


class ArcGISAuthenticator:
    """Handles OAuth2 client-credentials authentication."""

    def __init__(
        self,
        client_id: str = OAUTH_CLIENT_ID,
        client_secret: str = OAUTH_CLIENT_SECRET,
        api_url: str = ARCGIS_REST_API_URL,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = api_url
        self._token: Optional[str] = None
        self._expires_at = 0.0

    def get_token(self) -> Optional[str]:
        """Return a cached token when valid, otherwise fetch a new token."""
        now = time.time()
        if self._token and now < (self._expires_at - 60.0):
            return self._token

        if not self.client_id or not self.client_secret:
            logger.error("Missing OAUTH_CLIENT_ID or OAUTH_CLIENT_SECRET")
            return None

        try:
            response = requests.post(
                self.api_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": OAUTH_GRANT_TYPE,
                    "f": "json",
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()

            if payload.get("error"):
                logger.error("Authentication error: %s", payload["error"])
                return None

            token = payload.get("access_token")
            if not token:
                logger.error("Authentication response missing access_token")
                return None

            expires_in = float(payload.get("expires_in") or 1800.0)
            self._token = str(token)
            self._expires_at = now + expires_in
            return self._token
        except Exception as exc:
            logger.error("Failed to request token: %s", exc)
            return None


class ArcGISFeatureUpdater:
    """Updates ArcGIS FeatureServer features by ObjectID."""

    def __init__(self, feature_layer_url: str = FEATURE_LAYER_URL, authenticator: Optional[ArcGISAuthenticator] = None):
        self.feature_layer_url = feature_layer_url.rstrip("/")
        self.authenticator = authenticator or ArcGISAuthenticator()

    def authenticate_and_connect(self) -> bool:
        """Validate credentials and layer reachability before runtime loop starts."""
        if not self.feature_layer_url:
            logger.error("FEATURE_LAYER_URL is not configured")
            return False

        token = self.authenticator.get_token()
        if not token:
            return False

        try:
            response = requests.get(
                f"{self.feature_layer_url}/query",
                params={
                    "f": "json",
                    "where": "1=1",
                    "outFields": "OBJECTID",
                    "returnGeometry": "false",
                    "resultRecordCount": 1,
                    "token": token,
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                logger.error("Failed to connect to feature layer: %s", payload["error"])
                return False

            logger.info("Connected to feature layer")
            return True
        except Exception as exc:
            logger.error("Failed to connect to feature layer: %s", exc)
            return False

    def update_temperature_batch(self, sensor_data: Dict[str, dict], sensor_to_object_id: Dict[str, int]) -> bool:
        """Batch update temperature and timestamp fields for known sensors."""
        if not sensor_data:
            logger.warning("No sensor readings provided for batch update")
            return True

        token = self.authenticator.get_token()
        if not token:
            return False

        updates = []
        for sensor_id, data in sensor_data.items():
            object_id = sensor_to_object_id.get(sensor_id)
            if not object_id:
                logger.warning("No ObjectID mapping found for %s, skipping", sensor_id)
                continue

            attrs = {
                "OBJECTID": object_id,
                TEMPERATURE_FIELD: data.get("temperature_F"),
            }
            if LAST_RECORDED_FIELD and data.get("last_updated"):
                attrs[LAST_RECORDED_FIELD] = data["last_updated"]

            updates.append({"attributes": attrs})

        if not updates:
            logger.warning("No valid updates to send")
            return False

        try:
            response = requests.post(
                f"{self.feature_layer_url}/applyEdits",
                data={
                    "f": "json",
                    "updates": json.dumps(updates),
                    "token": token,
                },
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()

            if payload.get("error"):
                logger.error("Batch update failed: %s", payload["error"])
                return False

            update_results = payload.get("updateResults") or []
            success_count = sum(1 for item in update_results if item.get("success"))
            logger.info("Batch update: %s/%s features updated successfully", success_count, len(updates))
            return success_count == len(updates)
        except Exception as exc:
            logger.error("Failed to perform batch temperature update: %s", exc)
            return False
