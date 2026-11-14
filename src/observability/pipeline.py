import logging
from typing import Any, Dict, List, Optional

from src.netbox.get_devices import get_devices
from src.observability.health_checker import HealthChecker
from src.observability.report_formatter import ReportFormatter

logger = logging.getLogger(__name__)


def run_post_deployment_health_check(
    results: Optional[List[Dict[str, Any]]] = None,
    targets: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Execute post-deployment observability health check against Prometheus.

    Can be invoked after deployment engine finishes or run independently.
    Ensures that any failure in Prometheus does NOT raise an uncaught exception.
    """
    print("\n========== INITIATING OBSERVABILITY HEALTH CHECK ==========")

    eval_targets: List[Dict[str, Any]] = []

    if targets:
        # Map deployment results to targets
        res_map = {r.get("name"): r.get("deployment", "UNKNOWN") for r in (results or [])}
        for t in targets:
            name = t.get("name")
            eval_targets.append({
                "name": name,
                "ip": t.get("ip"),
                "role": t.get("role", "Device"),
                "deployment": res_map.get(name, "SUCCESS"),
            })
    else:
        # Fallback: Query all active devices from NetBox dynamically
        try:
            netbox_devices = get_devices()
            for d in netbox_devices:
                eval_targets.append({
                    "name": d.get("name"),
                    "ip": d.get("ip"),
                    "role": d.get("role", "Device"),
                    "deployment": "N/A (Standalone Check)",
                })
        except Exception as nb_err:
            print(f"! Warning: Could not retrieve devices from NetBox: {nb_err}")

    if not eval_targets:
        print("No eligible targets to evaluate for observability.")
        return {"overall_health": "UNKNOWN", "devices": [], "error": "No targets"}

    try:
        checker = HealthChecker()
        report = checker.generate_deployment_health_report(eval_targets)
        formatted_output = ReportFormatter.format_console(report)
        print("\n" + formatted_output)
        return report
    except Exception as err:
        print(f"\n[OBSERVABILITY WARNING] Health check failed: {err}")
        return {"overall_health": "UNKNOWN", "error": str(err), "devices": []}


def main() -> None:
    """Standalone CLI entry point for running network observability health checks."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_post_deployment_health_check()


if __name__ == "__main__":
    main()

