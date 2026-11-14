import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.netbox.get_devices import get_devices
from src.observability.config import TARGETS_FILE_PATH

logger = logging.getLogger(__name__)


def build_prometheus_target_entry(device: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a NetBox device dict into a Prometheus file_sd entry with environment labels."""
    ip = device.get("ip")
    name = device.get("name", "unknown")
    role = device.get("role") or "unknown"
    status = device.get("status") or "unknown"

    if not ip:
        raise ValueError(f"Device '{name}' is missing an IP address.")

    site_name = device.get("site") or ""
    site_slug = device.get("site_slug") or ""
    environment = device.get("environment")

    if not environment:
        if "vizag" in site_slug.lower() or "vizag" in site_name.lower():
            environment = "production"
        else:
            environment = "staging"

    labels: Dict[str, str] = {
        "device": name,
        "role": str(role),
        "status": str(status),
        "ip": str(ip),
        "environment": str(environment),
    }

    if site_name:
        labels["site"] = str(site_name)

    return {
        "targets": [ip],
        "labels": labels,
    }


def generate_prometheus_targets(
    devices: Optional[List[Dict[str, Any]]] = None,
    output_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieve active devices from NetBox across environments and write Prometheus file_sd target JSON."""
    if devices is None:
        try:
            # Query staging and production devices from NetBox dynamically
            staging_devices = get_devices(environment="staging")
            prod_devices = get_devices(environment="production")
            combined = staging_devices + prod_devices

            # Deduplicate by IP
            seen_ips = set()
            devices = []
            for d in combined:
                if d.get("ip") not in seen_ips:
                    devices.append(d)
                    seen_ips.add(d.get("ip"))
        except Exception as query_err:
            logger.warning("Environment query fallback to default get_devices: %s", query_err)
            devices = get_devices()

    target_entries = []
    for device in devices:
        try:
            entry = build_prometheus_target_entry(device)
            target_entries.append(entry)
        except Exception as error:
            logger.warning("Skipping device %s: %s", device.get("name", "Unknown"), error)

    dest = Path(output_path) if output_path else TARGETS_FILE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)

    temp_file = dest.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(target_entries, f, indent=2)
        f.write("\n")

    temp_file.replace(dest)
    logger.info("Prometheus targets saved to %s (%d devices)", dest, len(target_entries))
    return target_entries


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print("\n===== DYNAMIC PROMETHEUS TARGET DISCOVERY =====")
    try:
        targets = generate_prometheus_targets()
        print(f"Discovered and generated {len(targets)} target(s) at {TARGETS_FILE_PATH}:")
        for t in targets:
            labels = t.get("labels", {})
            print(
                f"  - Device: {labels.get('device'):<10} | "
                f"Env: {labels.get('environment'):<12} | "
                f"Target: {str(t.get('targets')):<18} | "
                f"Site: {labels.get('site', 'N/A')}"
            )
    except Exception as error:
        print(f"Discovery Error: Unable to retrieve devices from NetBox: {error}")
    print("================================================\n")


if __name__ == "__main__":
    main()
