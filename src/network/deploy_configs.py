import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def get_device_configs(
    environment: Optional[str] = None,
    site_slug: Optional[str] = None,
    validate_env: bool = True,
) -> List[Dict[str, Any]]:
    """Retrieve active device configurations from NetBox.

    Supports environment-based filtering ('staging' vs. 'production') to prevent
    cross-environment configuration leakage, while maintaining backward compatibility
    for existing parameterless calls.

    Args:
        environment: Optional target environment ('staging' or 'production').
                     Maps dynamically to site slug ('hyderabad-netkode' or 'vizag-netkode').
        site_slug: Optional explicit NetBox site slug.
        validate_env: If True and environment is provided, enforces strict anti-cross-pollution
                      guard to ensure staging devices cannot be deployed to production or vice versa.

    Returns:
        List of dictionaries with device details:
        [{
            "name": str,
            "ip": str,
            "config": str,
            "site": Optional[str],
            "site_slug": Optional[str],
        }, ...]
    """
    if os.getenv("CI_SIMULATE", "false").lower() in {"true", "1", "yes"}:
        env_clean = (environment or "staging").strip().lower()
        if env_clean == "staging":
            return [
                {
                    "name": "R1",
                    "ip": "192.168.1.1",
                    "config": "hostname R1\ninterface GigabitEthernet0/1\nip address 192.168.10.1 255.255.255.0\nno shutdown",
                    "site": "Hyderabad Netkode",
                    "site_slug": "hyderabad-netkode",
                },
                {
                    "name": "SW1",
                    "ip": "192.168.4.2",
                    "config": "hostname SW1\nvlan 10\nname DATA\ninterface GigabitEthernet0/1\nswitchport mode access\nswitchport access vlan 10",
                    "site": "Hyderabad Netkode",
                    "site_slug": "hyderabad-netkode",
                },
            ]
        elif env_clean == "production":
            return [
                {
                    "name": "R4",
                    "ip": "192.168.6.1",
                    "config": "hostname R4\ninterface GigabitEthernet0/1\nip address 192.168.60.1 255.255.255.0\nno shutdown",
                    "site": "Vizag Netkode",
                    "site_slug": "vizag-netkode",
                },
                {
                    "name": "switch3",
                    "ip": "192.168.9.2",
                    "config": "hostname Switch\nvlan 20\nname PROD_DATA\ninterface GigabitEthernet0/1\nswitchport mode access\nswitchport access vlan 20",
                    "site": "Vizag Netkode",
                    "site_slug": "vizag-netkode",
                },
            ]

    if not NETBOX_URL or not NETBOX_TOKEN:
        raise RuntimeError(
            "NETBOX_URL or NETBOX_TOKEN is missing from .env"
        )

    url = f"{NETBOX_URL}/api/dcim/devices/"

    headers = {
        "Authorization": f"Token {NETBOX_TOKEN}",
        "Accept": "application/json",
    }

    params: Dict[str, Any] = {
        "limit": 100,
        "status": "active",
    }

    # Resolve site filter
    target_site_slug = site_slug
    if environment:
        env_profile = get_environment_config(environment)
        if not target_site_slug:
            target_site_slug = env_profile.site_slug

    if target_site_slug:
        params["site"] = target_site_slug

    devices: List[Dict[str, Any]] = []

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

            # Strict environment anti-cross-pollution validation
            if environment and validate_env:
                validate_device_for_environment(device_name, environment)

            site_info = device.get("site") or {}

            devices.append({
                "name": device_name,
                "ip": primary_ip["address"].split("/")[0],
                "config": config,
                "site": site_info.get("name"),
                "site_slug": site_info.get("slug"),
            })

        url = data.get("next")
        params = None

    return devices


def main():
    target_env = sys.argv[1] if len(sys.argv) > 1 else None

    if target_env:
        print(f"\nDRY RUN: Retrieving configurations for environment '{target_env}'...")
        devices = get_device_configs(environment=target_env)
    else:
        print("\nDRY RUN: Retrieving all active device configurations...")
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

        site_display = device.get("site") or "Unknown Site"
        print(
            f"\nDevice: {device['name']}"
            f"\nSite:   {site_display}"
            f"\nIP:     {device['ip']}"
            f"\nConfiguration commands available: {len(config_lines)}"
        )

    print("\nDRY RUN COMPLETE: Nothing was applied to any device.")


if __name__ == "__main__":
    main()
