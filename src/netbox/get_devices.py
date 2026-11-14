import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
from dotenv import load_dotenv

from src.network.environment_config import (
    get_environment_config,
    validate_device_for_environment,
)

load_dotenv(PROJECT_ROOT / ".env")

NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
NETBOX_SITE_ID = os.getenv("NETBOX_SITE_ID")


def get_devices(
    site_slug: Optional[str] = None,
    site_id: Optional[Union[str, int]] = None,
    environment: Optional[str] = None,
    validate_env: bool = True,
) -> List[Dict[str, Any]]:
    """Retrieve active devices and primary IPv4 addresses from NetBox.

    Supports dynamic environment-based filtering ('staging' vs. 'production')
    as well as direct site_slug or site_id filtering, while preserving full
    backward compatibility for parameterless invocations.

    Args:
        site_slug: Optional NetBox site slug (e.g. 'hyderabad-netkode', 'vizag-netkode').
        site_id: Optional NetBox site ID (e.g. 1, 2).
        environment: Optional target environment ('staging' or 'production').
                     Resolves to the corresponding site_slug and enforces anti-cross-pollution checks.
        validate_env: If True and environment is specified, validates that each retrieved
                      device is authorized for the environment.

    Returns:
        List of dictionaries with device inventory data.
    """
    if not NETBOX_URL or not NETBOX_TOKEN:
        raise RuntimeError(
            "NetBox URL or API token is missing."
        )

    url = f"{NETBOX_URL.rstrip('/')}/api/dcim/devices/"

    headers = {
        "Authorization": f"Token {NETBOX_TOKEN}",
        "Accept": "application/json",
    }

    params: Dict[str, Any] = {
        "limit": 100,
        "status": "active",
    }

    # Determine site filter based on environment, site_slug, or site_id
    target_site_slug = site_slug
    target_site_id = site_id

    if environment:
        env_profile = get_environment_config(environment)
        if not target_site_slug:
            target_site_slug = env_profile.site_slug

    if target_site_slug:
        params["site"] = target_site_slug
    elif target_site_id is not None:
        params["site_id"] = str(target_site_id)
    elif NETBOX_SITE_ID:
        params["site_id"] = NETBOX_SITE_ID

    inventory: List[Dict[str, Any]] = []

    while url:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        for device in data.get("results", []):
            primary_ip = device.get("primary_ip4")

            if not primary_ip:
                print(
                    f"Skipping {device.get('name', 'Unknown')}: "
                    "no primary IPv4 address"
                )
                continue

            dev_name = device["name"]

            # Strict environment anti-cross-pollution validation
            if environment and validate_env:
                validate_device_for_environment(dev_name, environment)

            site_info = device.get("site") or {}

            inventory.append({
                "name": dev_name,
                "ip": primary_ip["address"].split("/")[0],
                "role": (device.get("role") or {}).get("name"),
                "status": (device.get("status") or {}).get("label"),
                "site": site_info.get("name"),
                "site_slug": site_info.get("slug"),
            })

        # Follow pagination
        url = data.get("next")
        params = None

    return inventory


if __name__ == "__main__":
    import sys
    target_env = sys.argv[1] if len(sys.argv) > 1 else None
    
    if target_env:
        print(f"\nRetrieving inventory for environment: '{target_env}'...")
        devices = get_devices(environment=target_env)
    else:
        print("\nRetrieving default inventory...")
        devices = get_devices()

    print("\nDevice inventory retrieved from NetBox:")
    for device in devices:
        print(
            f"Device: {device['name']:<10} | "
            f"IP: {device['ip']:<15} | "
            f"Role: {str(device['role']):<10} | "
            f"Site: {str(device['site']):<20} | "
            f"Status: {device['status']}"
        )

    print(f"\nTotal devices retrieved: {len(devices)}")
