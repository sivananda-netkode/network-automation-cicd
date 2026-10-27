import os

import requests
from dotenv import load_dotenv

load_dotenv()

NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
SITE_ID = 1


def get_devices():
    """Retrieve devices from the configured NetBox site."""

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

    return response.json()["results"]


if __name__ == "__main__":
    devices = get_devices()

    print("Devices retrieved from NetBox:")
    for device in devices:
        print(
            f"- {device['name']} | "
            f"Role: {device.get('role', {}).get('name')} | "
            f"Status: {device.get('status', {}).get('label')}"
        )
