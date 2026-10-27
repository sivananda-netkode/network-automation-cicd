
import os

from dotenv import load_dotenv
from netmiko import ConnectHandler
from src.netbox.get_devices import get_devices
load_dotenv(".env")


def check_device(device_info):
    """Connect to one device and run a read-only command."""

    device = {
        "device_type": "cisco_ios",
        "host": device_info["ip"],
        "username": os.environ["DEVICE_USERNAME"],
        "password": os.environ["DEVICE_PASSWORD"],
        "conn_timeout": 10,
        "auth_timeout": 10,
        "banner_timeout": 10,
    }

    print(f"\nConnecting to {device_info['name']} ({device_info['ip']})...")

    try:
        with ConnectHandler(**device) as connection:
            output = connection.send_command("show ip interface brief")
            print(f"SUCCESS: Connected to {device_info['name']}")
            print(output)
            return True

    except Exception as error:
        print(f"FAILED: {device_info['name']}: {type(error).__name__}: {error}")
        return False


if __name__ == "__main__":
    devices = get_devices()

    if not devices:
        raise SystemExit("No devices with primary IPv4 addresses found in NetBox.")

    results = [check_device(device) for device in devices]

    successful = sum(results)
    failed = len(results) - successful

    print(f"\nSummary: {successful} successful, {failed} failed.")
