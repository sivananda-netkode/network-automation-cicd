import json
from typing import Any, Dict


class ReportFormatter:
    """Formats the Deployment Health Report for terminal console display."""

    @staticmethod
    def to_json(report: Dict[str, Any], indent: int = 2) -> str:
        return json.dumps(report, indent=indent)

    @staticmethod
    def format_console(report: Dict[str, Any]) -> str:
        lines = []
        lines.append("=" * 72)
        lines.append("         DEPLOYMENT OBSERVABILITY HEALTH REPORT")
        lines.append("=" * 72)

        dep_id = report.get("deployment_id", "N/A")
        ts = report.get("timestamp", "N/A")
        prom_status = report.get("prometheus_status", "UNKNOWN")
        overall = report.get("overall_health", "UNKNOWN")

        lines.append(f"Deployment ID : {dep_id}")
        lines.append(f"Generated At  : {ts}")
        lines.append(f"Prometheus API: {prom_status}")
        lines.append(f"Overall Health: [{overall}]")
        lines.append("-" * 72)

        if prom_status != "REACHABLE":
            lines.append("! WARNING: Prometheus server is unreachable.")
            lines.append(f"! Error detail: {report.get('error')}")
            lines.append("=" * 72)
            return "\n".join(lines)

        devices = report.get("devices", [])
        if not devices:
            lines.append("No devices evaluated.")
            lines.append("=" * 72)
            return "\n".join(lines)

        for dev in devices:
            dev_name = dev.get("device", "Unknown")
            ip = dev.get("ip", "Unknown")
            role = dev.get("role", "Unknown")
            health = dev.get("health_status", "UNKNOWN")
            dep_res = dev.get("deployment_result", "N/A")

            lines.append(f"\n[DEVICE] {dev_name} ({ip}) | Role: {role}")
            lines.append(f"  - Deployment Result : {dep_res}")
            lines.append(f"  - Health Assessment : [{health}]")

            metrics = dev.get("metrics", {})
            lines.append("  - Monitored Telemetry:")

            # 1. Availability
            avail = metrics.get("availability", {})
            lines.append(f"    1. Availability     : [{avail.get('status', 'N/A')}] {avail.get('details', '')}")

            # 2. Uptime
            uptime = metrics.get("uptime", {})
            lines.append(f"    2. Uptime           : [{uptime.get('status', 'N/A')}] {uptime.get('details', '')}")

            # 3. CPU
            cpu = metrics.get("cpu_utilization", {})
            lines.append(f"    3. CPU Utilization  : [{cpu.get('status', 'N/A')}] {cpu.get('details', '')}")

            # 4. Memory
            mem = metrics.get("memory_utilization", {})
            lines.append(f"    4. Memory Usage     : [{mem.get('status', 'N/A')}] {mem.get('details', '')}")

            # 5. Interface Status
            if_stat = metrics.get("interface_status", {})
            lines.append(f"    5. Interface Status : [{if_stat.get('status', 'N/A')}] {if_stat.get('details', '')}")

            # 6. Interface Traffic
            if_traf = metrics.get("interface_traffic", {})
            lines.append(f"    6. Interface Traffic: [{if_traf.get('status', 'N/A')}] {if_traf.get('details', '')}")

            # 7. Bandwidth Utilization
            bw = metrics.get("bandwidth_utilization", {})
            lines.append(f"    7. Bandwidth Util   : [{bw.get('status', 'N/A')}] {bw.get('details', '')}")

            # 8. Interface Errors
            errs = metrics.get("interface_errors", {})
            lines.append(f"    8. Interface Errors : [{errs.get('status', 'N/A')}] {errs.get('details', '')}")

            # 9. OSPF Neighbors
            ospf = metrics.get("ospf_neighbor_status", {})
            lines.append(f"    9. OSPF Neighbors   : [{ospf.get('status', 'N/A')}] {ospf.get('details', '')}")

            # 10. Latency
            lat = metrics.get("network_latency", {})
            lines.append(f"   10. Network Latency  : [{lat.get('status', 'N/A')}] {lat.get('details', '')}")

            # Flag unsupported or stale
            unsupported = dev.get("unsupported_metrics", [])
            if unsupported:
                lines.append(f"  * Gracefully Handled Unsupported MIBs: {', '.join(unsupported)}")

            stale = dev.get("stale_metrics", [])
            if stale:
                lines.append(f"  ! Warning: Stale metrics detected: {', '.join(stale)}")

            crit = dev.get("critical_issues", [])
            for c in crit:
                lines.append(f"  ! CRITICAL: {c}")

        lines.append("\n" + "-" * 72)
        summary = report.get("summary", {})
        lines.append("SUMMARY:")
        lines.append(
            f"  Total: {summary.get('total_devices', 0)} | "
            f"Healthy: {summary.get('healthy', 0)} | "
            f"Warning: {summary.get('warning', 0)} | "
            f"Critical: {summary.get('critical', 0)} | "
            f"Unknown: {summary.get('unknown', 0)}"
        )
        lines.append("=" * 72)
        return "\n".join(lines)

