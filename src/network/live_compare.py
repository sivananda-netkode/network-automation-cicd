
import os
from pathlib import Path

from dotenv import load_dotenv
from netmiko import ConnectHandler

from src.network.compare_configs import (
    compare_config_lines,
    print_comparison,
)
from src.network.deploy_configs import get_device_configs


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def get_device_state(device_info):
    """Retrieve device state using read-only Cisco IOS commands."""

    username = os.getenv("DEVICE_USERNAME")
    password = os.getenv("DEVICE_PASSWORD")
    device_ip = device_info.get("ip")

    if not username or not password:
        raise RuntimeError("SSH credentials are missing from .env")

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

        # Supplementary information; these commands may not
        # be supported on every Cisco IOS device.
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

    if (
        not running_config
        or "% Invalid input" in running_config
    ):
        raise RuntimeError(
            "Could not retrieve running configuration."
        )

    return {
        "running_config": running_config,
        "vlan_output": vlan_output,
        "interface_output": interface_output,
    }


def main():
    """Compare NetBox intended configuration with live device state."""

    devices = get_device_configs()

    if not devices:
        raise SystemExit(
            "No device configurations found in NetBox."
        )

    failed_devices = []
    successful_devices = []

    for device in devices:
        device_name = device["name"]

        print(
            f"\nReading {device_name} ({device['ip']})..."
        )

        try:
            device_state = get_device_state(device)

            print("\n--- VLAN INFORMATION ---")

            if (
                not device_state["vlan_output"]
                or "% Invalid input" in device_state["vlan_output"]
            ):
                print("VLAN information unavailable.")
            else:
                print(device_state["vlan_output"])

            print("\n--- INTERFACE INFORMATION ---")

            if (
                not device_state["interface_output"]
                or "% Invalid input" in device_state["interface_output"]
            ):
                print("Interface information unavailable.")
            else:
                print(device_state["interface_output"])

            results = compare_config_lines(
                device["config"],
                device_state["running_config"],
                device_state["vlan_output"],
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
