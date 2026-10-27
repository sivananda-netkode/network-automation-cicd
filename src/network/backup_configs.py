
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from netmiko import ConnectHandler

from src.netbox.get_devices import get_devices

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = PROJECT_ROOT / "backups"


def backup_device(device_info):
    """Save one device's current running configuration."""

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
            config = connection.send_command("show running-config")

        if not config or "% Invalid input" in config:
            raise RuntimeError("Running configuration was not retrieved.")

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{device_info['name']}_{timestamp}.cfg"
        backup_path = BACKUP_DIR / filename

        backup_path.write_text(config + "\n", encoding="utf-8")

        print(f"SUCCESS: Backup saved to {backup_path}")
        return True

    except Exception as error:
        print(
            f"FAILED: {device_info['name']}: "
            f"{type(error).__name__}: {error}"
        )
        return False


if __name__ == "__main__":
    devices = get_devices()

    if not devices:
        raise SystemExit("No devices with primary IPv4 addresses found in NetBox.")

    results = [backup_device(device) for device in devices]

    successful = sum(results)
    failed = len(results) - successful

    print(f"\nBackup summary: {successful} successful, {failed} failed.")

    if failed:
        raise SystemExit(1)
