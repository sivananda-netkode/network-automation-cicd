
import os

import requests
from dotenv import load_dotenv

load_dotenv()

NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
SITE_ID = 1


def get_devices():
    """Get devices and their primary IP addresses from NetBox."""

    if not NETBOX_URL or not NETBOX_TOKEN:
        raise RuntimeError("NetBox URL or API token is missing.")

    url = f"{NETBOX_URL.rstrip('/')}/api/dcim/devices/"
    headers = {
        "Authorization": f"Token {NETBOX_TOKEN}",
        "Accept": "application/json",
    }
    params = {
        "site_id": SITE_ID,
        "limit": 100,
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=15,
    )
    response.raise_for_status()

    devices = response.json()["results"]

    inventory = []

    for device in devices:
        primary_ip = device.get("primary_ip4")

        if not primary_ip:
            print(f"Skipping {device['name']}: no primary IPv4 address")
            continue

        inventory.append({
            "name": device["name"],
            "ip": primary_ip["address"].split("/")[0],
            "role": (device.get("role") or {}).get("name"),
            "status": (device.get("status") or {}).get("label"),
        })

    return inventory


if __name__ == "__main__":
    devices = get_devices()

    print("Device inventory retrieved from NetBox:")

    for device in devices:
        print(
            f"{device['name']} | "
            f"IP: {device['ip']} | "
            f"Role: {device['role']} | "
            f"Status: {device['status']}"
        )
