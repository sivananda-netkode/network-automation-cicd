
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from netmiko import ConnectHandler

from src.netbox.get_devices import get_devices


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = PROJECT_ROOT / "backups"

load_dotenv(PROJECT_ROOT / ".env")


def backup_device(device_info):
    """Save one device's current running configuration securely."""

    device_name = device_info.get("name")
    device_ip = device_info.get("ip")

    try:
        if not device_name or not device_ip:
            raise ValueError("Device name or IP address is missing.")

        username = os.getenv("DEVICE_USERNAME")
        password = os.getenv("DEVICE_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                "SSH credentials are missing from .env"
            )

        connection_params = {
            "device_type": "cisco_ios",
            "host": device_ip,
            "username": username,
            "password": password,
            "conn_timeout": 10,
            "auth_timeout": 10,
            "banner_timeout": 10,
        }

        print(f"\nReading {device_name} ({device_ip})...")

        with ConnectHandler(**connection_params) as connection:
            config = connection.send_command(
                "show running-config"
            )

        if (
            not config
            or "% Invalid input" in config
        ):
            raise RuntimeError(
                "Running configuration was not retrieved."
            )

        BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
        )

        BACKUP_DIR.chmod(0o700)

        safe_name = re.sub(
            r"[^A-Za-z0-9_.-]",
            "_",
            device_name,
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        backup_path = BACKUP_DIR / f"{safe_name}_{timestamp}.cfg"

        backup_path.write_text(
            config + "\n",
            encoding="utf-8",
        )

        # Restrict backup file permissions on Linux.
        backup_path.chmod(0o600)

        print(f"SUCCESS: Backup saved to {backup_path}")

        return True

    except Exception as error:
        print(
            f"FAILED: {device_name or 'Unknown device'}: "
            f"{type(error).__name__}: {error}"
        )

        return False


def main():
    devices = get_devices()

    if not devices:
        raise SystemExit(
            "No devices with primary IPv4 addresses found in NetBox."
        )

    results = [
        backup_device(device)
        for device in devices
    ]

    successful = sum(results)
    failed = len(results) - successful

    print(
        f"\nBackup summary: "
        f"{successful} successful, {failed} failed."
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
