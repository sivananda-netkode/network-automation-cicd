import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from netmiko import ConnectHandler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.netbox.get_devices import get_devices
from src.network.environment_config import get_environment_config

BACKUP_DIR = PROJECT_ROOT / "backups"
load_dotenv(PROJECT_ROOT / ".env")


def backup_device(
    device_info: Dict[str, Any],
    environment: Optional[str] = None,
) -> Optional[str]:
    """Save one device's current running configuration securely.

    Args:
        device_info: Dictionary containing at least 'name' and 'ip'.
        environment: Optional environment profile ('staging' or 'production')
                     used to resolve credentials and storage directory.

    Returns:
        The string path to the saved backup file on success, or None on failure.
    """
    device_name = device_info.get("name")
    device_ip = device_info.get("ip")
    target_env = environment or device_info.get("environment")

    try:
        if not device_name or not device_ip:
            raise ValueError("Device name or IP address is missing.")

        if target_env:
            env_cfg = get_environment_config(target_env)
            username, password = env_cfg.get_credentials()
        else:
            username = os.getenv("DEVICE_USERNAME")
            password = os.getenv("DEVICE_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                "SSH credentials are missing from environment."
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

        if not config or "% Invalid input" in config:
            raise RuntimeError(
                "Running configuration was not retrieved."
            )

        target_dir = BACKUP_DIR / target_env if target_env else BACKUP_DIR
        target_dir.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )
        target_dir.chmod(0o700)

        safe_name = re.sub(
            r"[^A-Za-z0-9_.-]",
            "_",
            device_name,
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        backup_path = target_dir / f"{safe_name}_{timestamp}.cfg"

        backup_path.write_text(
            config + "\n",
            encoding="utf-8",
        )

        # Restrict backup file permissions on Linux
        backup_path.chmod(0o600)

        print(f"SUCCESS: Backup saved to {backup_path}")
        return str(backup_path)

    except Exception as error:
        print(
            f"FAILED: {device_name or 'Unknown device'}: "
            f"{type(error).__name__}: {error}"
        )
        return None


def main():
    target_env = sys.argv[1] if len(sys.argv) > 1 else None

    if target_env:
        print(f"\nRetrieving inventory for environment '{target_env}'...")
        devices = get_devices(environment=target_env)
    else:
        print("\nRetrieving default inventory...")
        devices = get_devices()

    if not devices:
        raise SystemExit(
            "No devices with primary IPv4 addresses found in NetBox."
        )

    results = [
        backup_device(device, environment=target_env)
        for device in devices
    ]

    successful = sum(1 for r in results if r is not None)
    failed = len(results) - successful

    print(
        f"\nBackup summary: "
        f"{successful} successful, {failed} failed."
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
