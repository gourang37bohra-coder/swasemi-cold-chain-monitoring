"""Shipment lifecycle gate client to query active shipments from the backend REST API."""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("coldchain.simulator.gate")


@dataclass
class ActiveShipmentInfo:
    """Active shipment metadata associated with a tracker."""
    shipment_id: str
    tracker_id: str
    status: str
    min_temperature: float
    max_temperature: float


class ShipmentGateClient:
    """Polls backend REST API to detect active shipment lifecycle states for trackers."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        username: str = "operator@apexpharma.com",
        password: str = "Password@123",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._access_token: Optional[str] = None
        self._active_shipments: Dict[str, ActiveShipmentInfo] = {}

    def _login(self) -> bool:
        """Authenticate with backend API and obtain JWT bearer token."""
        url = f"{self.base_url}/auth/login"
        payload = json.dumps({"email": self.username, "password": self.password}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._access_token = data.get("access_token")
                logger.debug("Successfully authenticated with backend API.")
                return True
        except Exception as exc:
            logger.warning("Failed to authenticate with backend API (%s): %s", url, exc)
            self._access_token = None
            return False

    def refresh_active_shipments(self) -> Dict[str, ActiveShipmentInfo]:
        """Fetch all shipments from the backend API and index active ones by tracker_id."""
        if not self._access_token:
            if not self._login():
                return self._active_shipments

        url = f"{self.base_url}/shipments?page_size=100"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])
                new_active: Dict[str, ActiveShipmentInfo] = {}

                for s in items:
                    if s.get("status") == "ACTIVE":
                        t_id = s.get("tracker_id")
                        if t_id:
                            new_active[str(t_id)] = ActiveShipmentInfo(
                                shipment_id=str(s["id"]),
                                tracker_id=str(t_id),
                                status="ACTIVE",
                                min_temperature=float(s.get("minimum_temperature", 2.0)),
                                max_temperature=float(s.get("maximum_temperature", 8.0)),
                            )

                self._active_shipments = new_active
                logger.debug("Refreshed active shipments: %d active tracker(s)", len(new_active))
                return self._active_shipments

        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                # Token expired, retry once with fresh login
                logger.debug("Access token expired (401), refreshing credentials...")
                if self._login():
                    return self.refresh_active_shipments()
            logger.warning("HTTP error querying shipments from backend: %s", exc)
        except Exception as exc:
            logger.warning("Error querying active shipments from backend: %s", exc)

        return self._active_shipments

    def is_tracker_active(self, tracker_id: str) -> bool:
        """Check if the given tracker has an ACTIVE shipment."""
        return str(tracker_id) in self._active_shipments

    def get_shipment_info(self, tracker_id: str) -> Optional[ActiveShipmentInfo]:
        """Get the active shipment info for a tracker if active."""
        return self._active_shipments.get(str(tracker_id))
