
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

NETBOX_URL = os.getenv("NETBOX_URL", "").rstrip("/")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
NETBOX_SITE_ID = os.getenv("NETBOX_SITE_ID")


SESSION_COMMANDS = {
    "enable",
    "configure terminal",
    "conf t",
    "end",
    "exit",
    "write memory",
    "write",
    "copy running-config startup-config",
}


def get_device_configs():
    """Retrieve active device configurations from NetBox."""

    if not NETBOX_URL or not NETBOX_TOKEN:
        raise RuntimeError(
            "NETBOX_URL or NETBOX_TOKEN is missing from .env"
        )

    url = f"{NETBOX_URL}/api/dcim/devices/"

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

    devices = []

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
            device_name = device.get("name", "Unknown")

            context = device.get("local_context_data") or {}
            config = context.get("cli_config")
            primary_ip = device.get("primary_ip4")

            if not isinstance(config, str) or not config.strip():
                print(f"SKIP: {device_name} has no valid cli_config.")
                continue

            if not primary_ip or not primary_ip.get("address"):
                print(
                    f"SKIP: {device_name} has no primary IPv4 address."
                )
                continue

            devices.append({
                "name": device_name,
                "ip": primary_ip["address"].split("/")[0],
                "config": config,
            })

        url = data.get("next")
        params = None

    return devices


def main():
    devices = get_device_configs()

    if not devices:
        raise SystemExit(
            "No active device configurations found in NetBox."
        )

    print(
        f"\nDRY RUN: Found {len(devices)} device configuration(s)."
    )
    print("No SSH connections will be opened and no changes will be made.")

    for device in devices:
        config_lines = [
            line
            for line in device["config"].splitlines()
            if line.strip()
        ]

        print(
            f"\nDevice: {device['name']}"
            f"\nIP: {device['ip']}"
            f"\nConfiguration commands available: {len(config_lines)}"
        )

    print("\nDRY RUN COMPLETE: Nothing was applied to any device.")


if __name__ == "__main__":
    main()
