
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
NETBOX_SITE_ID = os.getenv("NETBOX_SITE_ID")


def get_devices():
    """Retrieve active devices and primary IPv4 addresses from NetBox."""

    if not NETBOX_URL or not NETBOX_TOKEN:
        raise RuntimeError(
            "NetBox URL or API token is missing."
        )

    url = f"{NETBOX_URL.rstrip('/')}/api/dcim/devices/"

    headers = {
        "Authorization": f"Token {NETBOX_TOKEN}",
        "Accept": "application/json",
    }

    params = {
        "limit": 100,
        "status": "active",
    }

    if NETBOX_SITE_ID:
        params["site_id"] = NETBOX_SITE_ID

    inventory = []

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

            inventory.append({
                "name": device["name"],
                "ip": primary_ip["address"].split("/")[0],
                "role": (device.get("role") or {}).get("name"),
                "status": (device.get("status") or {}).get("label"),
            })

        # Follow the next page returned by NetBox.
        url = data.get("next")
        params = None

    return inventory


if __name__ == "__main__":
    devices = get_devices()

    print("\nDevice inventory retrieved from NetBox:")

    for device in devices:
        print(
            f"{device['name']} | "
            f"IP: {device['ip']} | "
            f"Role: {device['role']} | "
            f"Status: {device['status']}"
        )

    print(f"\nTotal devices retrieved: {len(devices)}")
