import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from netmiko import ConnectHandler

from src.network.deploy_configs import get_device_configs
from src.network.environment_config import get_environment_config

load_dotenv(PROJECT_ROOT / ".env")


def get_connection(
    device: Dict[str, Any],
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    """Build SSH connection parameters for target device and environment."""
    target_env = environment or device.get("environment")

    if target_env:
        env_cfg = get_environment_config(target_env)
        username, password = env_cfg.get_credentials()
    else:
        username = os.getenv("DEVICE_USERNAME")
        password = os.getenv("DEVICE_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "Device SSH credentials are missing from environment."
        )

    return {
        "device_type": "cisco_ios",
        "host": device["ip"],
        "username": username,
        "password": password,
        "conn_timeout": 10,
        "auth_timeout": 10,
        "banner_timeout": 10,
    }


def validate_device(
    device: Dict[str, Any],
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    """Run read-only operational commands to verify health and configuration."""
    commands = {
        "INTERFACES": "show ip interface brief",
        "OSPF NEIGHBORS": "show ip ospf neighbor",
        "ROUTING TABLE": "show ip route",
        "VLAN DATABASE": "show vlan brief",
    }

    results: Dict[str, Any] = {
        "device": device["name"],
        "ip": device["ip"],
        "site": device.get("site", "Unknown"),
        "checks": {},
    }

    print(f"\nConnecting to {device['name']} ({device['ip']})...")

    if os.getenv("CI_SIMULATE", "false").lower() in {"true", "1", "yes"}:
        print(f"[CI SIMULATION] Performing operational checks for {device['name']} ({device['ip']})...")
        results["checks"] = {
            "INTERFACES": "FastEthernet0/0 is up, line protocol is up\nFastEthernet0/1 is up, line protocol is up",
            "OSPF NEIGHBORS": "Neighbor 192.168.1.1 Full/BDR",
            "ROUTING TABLE": "O 192.168.10.0/24 [110/2] via 192.168.1.1\nC 192.168.1.0/24 is directly connected",
            "VLAN DATABASE": "1 default active\n10 DATA active\n20 PROD_DATA active",
        }
        return results

    with ConnectHandler(**get_connection(device, environment=environment)) as connection:
        # Verify prompt identity
        prompt = connection.find_prompt()
        if device["name"].lower() not in prompt.lower():
            print(f"WARNING: Connected prompt '{prompt}' does not explicitly match '{device['name']}'")

        for check_name, command in commands.items():
            try:
                output = connection.send_command(
                    command,
                    read_timeout=30,
                )
                results["checks"][check_name] = output
            except Exception as error:
                results["checks"][check_name] = (
                    f"COMMAND FAILED: {type(error).__name__}: {error}"
                )

    return results


def run_validation(environment: Optional[str] = None) -> bool:
    """Execute operational verification for all devices in the target environment.

    Returns:
        True if all devices validated successfully, False otherwise.
    """
    devices = get_device_configs(environment=environment)

    if not devices:
        print(f"No eligible devices found in NetBox for environment: {environment or 'default'}")
        return False

    env_label = environment.upper() if environment else "DEFAULT"
    print(f"\n===== NETWORK OPERATIONAL VALIDATION [{env_label}] =====")
    print(f"Discovered devices: {len(devices)}")

    successful = 0
    failed = 0

    for device in devices:
        try:
            result = validate_device(device, environment=environment)
            successful += 1

            for check_name, output in result["checks"].items():
                print(f"\n--- {result['device']}: {check_name} ---")
                print(output)

        except Exception as error:
            failed += 1
            print(
                f"\nFAILED: {device['name']}: "
                f"{type(error).__name__}: {error}"
            )

    print(f"\n===== OPERATIONAL VALIDATION SUMMARY [{env_label}] =====")
    print(f"Total devices: {len(devices)}")
    print(f"SSH successful: {successful}")
    print(f"SSH failed: {failed}")
    print("\nRead-only validation completed.")
    print("No device configuration changes were sent.")

    return failed == 0


def main():
    target_env = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TARGET_ENVIRONMENT")
    success = run_validation(environment=target_env)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
