"""NetBox Source of Truth Validator for Alertmanager Webhook Gateway.

Validates whether an interface or device reported in a Prometheus alert is
documented as active and enabled in NetBox before creating a Jira ticket.
Prevents ticket spam for empty, unconnected, or decommissioned ports.
"""

import logging
import os
import time
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class NetBoxValidator:
    """Validates devices and interfaces dynamically against NetBox Single Source of Truth."""

    def __init__(
        self,
        netbox_url: Optional[str] = None,
        netbox_token: Optional[str] = None,
        cache_ttl_seconds: int = 60,
    ):
        self.netbox_url = (netbox_url or os.getenv("NETBOX_URL", "")).rstrip("/")
        self.netbox_token = netbox_token or os.getenv("NETBOX_TOKEN", "")
        self.cache_ttl = cache_ttl_seconds
        # In-memory cache: (device_name_lower, interface_name_lower) -> (is_monitored, timestamp)
        self._cache: Dict[Tuple[str, str], Tuple[bool, float]] = {}

    def is_configured(self) -> bool:
        """Check if NetBox credentials and URL are present."""
        return bool(self.netbox_url and self.netbox_token)

    def is_interface_monitored(self, device_name: str, interface_name: str) -> bool:
        """Check if an interface is documented and enabled in NetBox.

        Returns True if the interface is active/enabled in NetBox.
        Returns False if the interface is NOT in NetBox or disabled.
        If NetBox is not configured or temporarily unreachable, defaults to True (fail-open).
        """
        if not self.is_configured():
            logger.debug("NetBox not configured; allowing alert through (fail-open).")
            return True

        if not device_name or not interface_name:
            return True

        cache_key = (device_name.strip().lower(), interface_name.strip().lower())
        now = time.time()

        # Check cache
        if cache_key in self._cache:
            is_valid, cached_time = self._cache[cache_key]
            if now - cached_time < self.cache_ttl:
                return is_valid

        # Query NetBox API
        headers = {
            "Authorization": f"Token {self.netbox_token}",
            "Accept": "application/json",
        }
        url = f"{self.netbox_url}/api/dcim/interfaces/"
        params = {
            "device": device_name.strip(),
            "name": interface_name.strip(),
            "limit": 1,
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if not results:
                    logger.info(
                        "Interface %s on %s is NOT documented in NetBox. Suppressing Jira ticket.",
                        interface_name,
                        device_name,
                    )
                    self._cache[cache_key] = (False, now)
                    return False

                iface = results[0]
                is_enabled = iface.get("enabled", True)
                if not is_enabled:
                    logger.info(
                        "Interface %s on %s is disabled in NetBox. Suppressing Jira ticket.",
                        interface_name,
                        device_name,
                    )
                    self._cache[cache_key] = (False, now)
                    return False

                self._cache[cache_key] = (True, now)
                return True
            else:
                logger.warning(
                    "NetBox returned HTTP %s when checking interface %s on %s. Allowing alert through.",
                    response.status_code,
                    interface_name,
                    device_name,
                )
                return True
        except requests.RequestException as err:
            logger.warning(
                "Could not reach NetBox at %s (%s). Allowing alert through (fail-open).",
                self.netbox_url,
                err,
            )
            return True

