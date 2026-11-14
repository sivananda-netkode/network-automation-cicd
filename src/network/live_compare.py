import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from netmiko import ConnectHandler

from src.network.compare_configs import (
    compare_config_lines,
    print_comparison,
)
from src.network.deploy_configs import get_device_configs
from src.network.environment_config import get_environment_config

load_dotenv(PROJECT_ROOT / ".env")


def get_device_state(
    device_info: Dict[str, Any],
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve device state using read-only Cisco IOS commands.

    Args:
        device_info: Device dict containing 'name' and 'ip'.
        environment: Optional environment profile ('staging' or 'production').

    Returns:
        Dict with 'running_config', 'vlan_output', and 'interface_output'.
    """
    target_env = environment or device_info.get("environment")

    if target_env:
        env_cfg = get_environment_config(target_env)
        username, password = env_cfg.get_credentials()
    else:
        username = os.getenv("DEVICE_USERNAME")
        password = os.getenv("DEVICE_PASSWORD")

    device_ip = device_info.get("ip")

    if not username or not password:
        raise RuntimeError("SSH credentials are missing from environment.")

    if not device_ip:
        raise ValueError("Device IP address is missing.")

    connection_params = {
        "device_type": "cisco_ios",
        "host": device_ip,
        "username": username,
        "password": password,
        "conn_timeout": 10,
        "auth_timeout": 10,
        "banner_timeout": 10,
    }

    with ConnectHandler(**connection_params) as connection:
        running_config = connection.send_command(
            "show running-config"
        )

        try:
            vlan_output = connection.send_command(
                "show vlan brief"
            )
        except Exception:
            vlan_output = ""

        try:
            interface_output = connection.send_command(
                "show ip interface brief"
            )
        except Exception:
            interface_output = ""

    return {
        "running_config": running_config,
        "vlan_output": vlan_output,
        "interface_output": interface_output,
    }


def main():
    target_env = sys.argv[1] if len(sys.argv) > 1 else None

    if target_env:
        print(f"\nRetrieving configurations for environment '{target_env}'...")
        devices = get_device_configs(environment=target_env)
    else:
        print("\nRetrieving default device configurations...")
        devices = get_device_configs()

    if not devices:
        raise SystemExit(
            "No active device configurations found in NetBox."
        )

    print("\n===== NETWORK STATE COMPARISON =====")
    print("Fetching live device state using read-only SSH.")
    print("Comparing NetBox desired state against running configurations.\n")

    successful_devices = []
    failed_devices = []

    for device in devices:
        device_name = device["name"]
        device_ip = device["ip"]

        print(f"\n--- Checking {device_name} ({device_ip}) ---")

        try:
            device_state = get_device_state(device, environment=target_env)

            if not device_state["running_config"]:
                raise RuntimeError(
                    "Unable to retrieve running-config from device."
                )

            print(f"Retrieved running-config for {device_name}.")

            if device_state["vlan_output"]:
                print(f"Retrieved VLAN database for {device_name}.")
            else:
                print(f"No VLAN database returned for {device_name}.")

            if device_state["interface_output"]:
                print(f"Retrieved interface status for {device_name}:")
                print(device_state["interface_output"])

            results = compare_config_lines(
                device["config"],
                device_state["running_config"],
                device_state["vlan_output"],
                device_state["interface_output"],
            )

            print_comparison(device_name, results)
            successful_devices.append(device_name)

        except Exception as error:
            failed_devices.append(device_name)
            print(
                f"FAILED: {device_name}: "
                f"{type(error).__name__}: {error}"
            )

    print("\n===== LIVE COMPARISON SUMMARY =====")
    print(f"Total devices: {len(devices)}")
    print(f"Successful: {len(successful_devices)}")
    print(f"Failed: {len(failed_devices)}")

    if successful_devices:
        print(
            "Successfully compared: "
            + ", ".join(successful_devices)
        )

    if failed_devices:
        print(
            "Failed devices: "
            + ", ".join(failed_devices)
        )

    print("\nREAD-ONLY DEVICE COMPARISON FINISHED.")
    print("No configuration changes were sent to devices.")

    if failed_devices:
        raise SystemExit(
            f"Live comparison failed for "
            f"{len(failed_devices)} device(s)."
        )

    print("All device comparisons completed successfully.")


if __name__ == "__main__":
    main()
