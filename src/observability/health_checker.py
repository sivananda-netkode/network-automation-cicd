from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from src.observability.metrics_collector import MetricsCollector
from src.observability.prometheus_client import PrometheusClient

logger = logging.getLogger(__name__)


class HealthChecker:
    """Evaluates telemetry from Prometheus to generate a structured Deployment Health Report."""

    def __init__(
        self,
        client: Optional[PrometheusClient] = None,
        collector: Optional[MetricsCollector] = None,
    ):
        self.client = client or PrometheusClient()
        self.collector = collector or MetricsCollector(client=self.client)

    def evaluate_device_health(
        self,
        device_telemetry: Dict[str, Any],
        deployment_result: str = "SUCCESS",
    ) -> Dict[str, Any]:
        """Determine health status for a single device based on collected metrics."""
        device_name = device_telemetry.get("device", "unknown")
        ip = device_telemetry.get("ip", "unknown")
        role = device_telemetry.get("role", "unknown")
        metrics = device_telemetry.get("metrics", {})

        unsupported_metrics: List[str] = []
        warnings: List[str] = []
        critical_issues: List[str] = []
        stale_metrics: List[str] = []

        # Analyze each parameter
        for metric_name, m_data in metrics.items():
            if not isinstance(m_data, dict):
                continue

            status = m_data.get("status")
            if status == "UNSUPPORTED":
                unsupported_metrics.append(metric_name)
            elif status == "CRITICAL":
                critical_issues.append(f"{metric_name}: {m_data.get('details', 'Critical threshold exceeded')}")
            elif status == "WARNING":
                warnings.append(f"{metric_name}: {m_data.get('details', 'Warning threshold exceeded')}")

            if m_data.get("is_stale"):
                stale_metrics.append(metric_name)

        # Device availability check
        avail = metrics.get("availability", {})
        if avail.get("status") == "CRITICAL" or avail.get("value") == 0:
            overall_status = "CRITICAL"
            critical_issues.insert(0, "Device is DOWN / unreachable via SNMP")
        elif critical_issues:
            overall_status = "CRITICAL"
        elif warnings:
            overall_status = "WARNING"
        elif avail.get("status") == "UNKNOWN":
            overall_status = "UNKNOWN"
        else:
            overall_status = "HEALTHY"

        return {
            "device": device_name,
            "ip": ip,
            "role": role,
            "deployment_result": deployment_result,
            "health_status": overall_status,
            "metrics": metrics,
            "critical_issues": critical_issues,
            "warnings": warnings,
            "unsupported_metrics": unsupported_metrics,
            "stale_metrics": stale_metrics,
        }

    def generate_deployment_health_report(
        self,
        targets: List[Dict[str, Any]],
        deployment_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a complete Deployment Health Report for all targets."""
        dep_id = deployment_id or f"dep-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # Step 1: Check Prometheus connectivity
        health_check = self.client.check_health()
        if not health_check.get("reachable"):
            return {
                "deployment_id": dep_id,
                "timestamp": timestamp,
                "prometheus_status": "UNREACHABLE",
                "overall_health": "UNKNOWN",
                "error": health_check.get("message"),
                "devices": [],
                "summary": {
                    "total_devices": len(targets),
                    "healthy": 0,
                    "warning": 0,
                    "critical": 0,
                    "unknown": len(targets),
                },
            }

        device_reports = []
        healthy_count = 0
        warning_count = 0
        critical_count = 0
        unknown_count = 0

        for target in targets:
            ip = target.get("ip")
            name = target.get("name") or target.get("device")
            role = target.get("role")
            dep_res = target.get("deployment", "SUCCESS")

            if not ip:
                continue

            try:
                telemetry = self.collector.collect_device_metrics(ip=ip, name=name, role=role)
                report = self.evaluate_device_health(telemetry, deployment_result=dep_res)
            except Exception as err:
                logger.error("Failed to evaluate telemetry for %s: %s", name, err)
                report = {
                    "device": name or ip,
                    "ip": ip,
                    "role": role or "unknown",
                    "deployment_result": dep_res,
                    "health_status": "UNKNOWN",
                    "metrics": {},
                    "critical_issues": [f"Telemetry collection failed: {err}"],
                    "warnings": [],
                    "unsupported_metrics": [],
                    "stale_metrics": [],
                }

            status = report["health_status"]
            if status == "HEALTHY":
                healthy_count += 1
            elif status == "WARNING":
                warning_count += 1
            elif status == "CRITICAL":
                critical_count += 1
            else:
                unknown_count += 1

            device_reports.append(report)

        if critical_count > 0:
            overall = "CRITICAL"
        elif warning_count > 0:
            overall = "WARNING"
        elif unknown_count > 0 and healthy_count == 0:
            overall = "UNKNOWN"
        else:
            overall = "HEALTHY"

        return {
            "deployment_id": dep_id,
            "timestamp": timestamp,
            "prometheus_status": "REACHABLE",
            "overall_health": overall,
            "devices": device_reports,
            "summary": {
                "total_devices": len(device_reports),
                "healthy": healthy_count,
                "warning": warning_count,
                "critical": critical_count,
                "unknown": unknown_count,
            },
        }

