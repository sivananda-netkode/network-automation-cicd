import logging
from typing import Any, Dict, Optional

from src.observability.config import (
    BANDWIDTH_CRITICAL_THRESHOLD,
    BANDWIDTH_WARNING_THRESHOLD,
    CPU_CRITICAL_THRESHOLD,
    CPU_WARNING_THRESHOLD,
    LATENCY_CRITICAL_MS,
    LATENCY_WARNING_MS,
    MEMORY_CRITICAL_THRESHOLD,
    MEMORY_WARNING_THRESHOLD,
)
from src.observability.prometheus_client import PrometheusClient

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and normalizes the 10 core network observability parameters."""

    def __init__(self, client: Optional[PrometheusClient] = None):
        self.client = client or PrometheusClient()

    def _target_filter(self, ip: str, name: Optional[str] = None) -> str:
        """Build regex selector matching target by IP or device label."""
        if name:
            return f'instance=~"{ip}(:\\\\d+)?|{name}"'
        return f'instance=~"{ip}(:\\\\d+)?"'

    def collect_device_metrics(
        self,
        ip: str,
        name: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Collect all 10 parameters for a target device."""
        selector = self._target_filter(ip, name)

        availability = self._get_availability(selector)
        uptime = self._get_uptime(selector)
        cpu = self._get_cpu_utilization(selector)
        memory = self._get_memory_utilization(selector)
        interfaces = self._get_interface_metrics(selector)
        ospf = self._get_ospf_status(selector, role)
        latency = self._get_latency(selector)

        return {
            "device": name or ip,
            "ip": ip,
            "role": role or "unknown",
            "metrics": {
                "availability": availability,
                "uptime": uptime,
                "cpu_utilization": cpu,
                "memory_utilization": memory,
                "interface_status": interfaces.get("status", {}),
                "interface_traffic": interfaces.get("traffic", {}),
                "bandwidth_utilization": interfaces.get("bandwidth", {}),
                "interface_errors": interfaces.get("errors", {}),
                "ospf_neighbor_status": ospf,
                "network_latency": latency,
            },
        }

    # 1. Device Availability
    def _get_availability(self, selector: str) -> Dict[str, Any]:
        promql = f"snmp_scrape_success{{{selector}}} or up{{{selector}}}"
        res = self.client.query(promql)

        if not res["success"]:
            return {
                "status": "UNKNOWN",
                "value": None,
                "error": res["error"],
                "is_stale": False,
                "details": f"Query failed: {res['error']}",
            }

        if not res["results"]:
            return {
                "status": "UNKNOWN",
                "value": None,
                "error": "No availability metrics found in Prometheus.",
                "is_stale": False,
                "details": "Target has not been scraped yet or target is not in Prometheus.",
            }

        first = res["results"][0]
        val = first.get("value")
        is_up = val == 1.0 or val == 1

        return {
            "status": "HEALTHY" if is_up else "CRITICAL",
            "value": 1.0 if is_up else 0.0,
            "is_up": is_up,
            "is_stale": first.get("is_stale", False),
            "age_seconds": first.get("age_seconds"),
            "details": "Device reachable via SNMP" if is_up else "Device unreachable / scrape failed",
        }

    # 2. Device Uptime
    def _get_uptime(self, selector: str) -> Dict[str, Any]:
        promql = f"sysUpTime{{{selector}}} / 100"
        res = self.client.query(promql)

        if not res["success"] or not res["results"]:
            return {
                "status": "UNKNOWN",
                "value": None,
                "uptime_hours": None,
                "details": res.get("error") or "sysUpTime metric not found.",
                "is_stale": False,
            }

        first = res["results"][0]
        seconds = first.get("value")
        if seconds is None:
            return {"status": "UNKNOWN", "value": None, "details": "No numeric uptime value", "is_stale": False}

        hours = round(seconds / 3600.0, 2)
        days = round(hours / 24.0, 2)
        # Warning if device rebooted in the last 10 minutes (600s)
        status = "WARNING" if seconds < 600 else "HEALTHY"
        msg = f"Rebooted {round(seconds, 0)}s ago" if seconds < 600 else f"Uptime: {days} days ({hours} hrs)"

        return {
            "status": status,
            "value": seconds,
            "uptime_seconds": seconds,
            "uptime_hours": hours,
            "uptime_days": days,
            "details": msg,
            "is_stale": first.get("is_stale", False),
            "age_seconds": first.get("age_seconds"),
        }

    # 3. CPU Utilization
    def _get_cpu_utilization(self, selector: str) -> Dict[str, Any]:
        promql = f"cpmCPUTotal5min{{{selector}}} or cpmCPUTotal1min{{{selector}}}"
        res = self.client.query(promql)

        if not res["success"]:
            return {
                "status": "UNKNOWN",
                "value": None,
                "details": f"Query error: {res['error']}",
                "is_stale": False,
            }

        if not res["results"]:
            return {
                "status": "UNSUPPORTED",
                "value": None,
                "details": "Unsupported: Cisco Process CPU MIB not exposed by this device.",
                "is_stale": False,
            }

        first = res["results"][0]
        val = first.get("value")
        if val is None:
            return {"status": "UNKNOWN", "value": None, "details": "Non-numeric CPU value", "is_stale": False}

        if val >= CPU_CRITICAL_THRESHOLD:
            status = "CRITICAL"
        elif val >= CPU_WARNING_THRESHOLD:
            status = "WARNING"
        else:
            status = "HEALTHY"

        return {
            "status": status,
            "value": val,
            "details": f"CPU load: {val}%",
            "is_stale": first.get("is_stale", False),
            "age_seconds": first.get("age_seconds"),
        }

    # 4. Memory Utilization
    def _get_memory_utilization(self, selector: str) -> Dict[str, Any]:
        used_q = f"ciscoMemoryPoolUsed{{{selector}}}"
        free_q = f"ciscoMemoryPoolFree{{{selector}}}"
        pct_q = (
            f"({used_q} / ({used_q} + {free_q})) * 100"
        )
        res = self.client.query(pct_q)

        if not res["success"]:
            return {
                "status": "UNKNOWN",
                "value": None,
                "details": f"Query error: {res['error']}",
                "is_stale": False,
            }

        if not res["results"]:
            return {
                "status": "UNSUPPORTED",
                "value": None,
                "details": "Unsupported: Cisco Memory Pool MIB not exposed by this device.",
                "is_stale": False,
            }

        first = res["results"][0]
        val = first.get("value")
        if val is None:
            return {"status": "UNKNOWN", "value": None, "details": "Non-numeric memory value", "is_stale": False}

        val = round(val, 2)
        if val >= MEMORY_CRITICAL_THRESHOLD:
            status = "CRITICAL"
        elif val >= MEMORY_WARNING_THRESHOLD:
            status = "WARNING"
        else:
            status = "HEALTHY"

        return {
            "status": status,
            "value": val,
            "details": f"Memory utilization: {val}%",
            "is_stale": first.get("is_stale", False),
            "age_seconds": first.get("age_seconds"),
        }

    # Helper for interface metrics (5. Status, 6. Traffic, 7. Bandwidth, 8. Errors)
    def _get_interface_metrics(self, selector: str) -> Dict[str, Any]:
        oper_q = f"ifOperStatus{{{selector}}}"
        in_q = f"rate(ifHCInOctets{{{selector}}}[2m]) * 8"
        out_q = f"rate(ifHCOutOctets{{{selector}}}[2m]) * 8"
        speed_q = f"ifHighSpeed{{{selector}}}"
        in_err_q = f"rate(ifInErrors{{{selector}}}[5m])"
        out_err_q = f"rate(ifOutErrors{{{selector}}}[5m])"

        oper_res = self.client.query(oper_q)
        in_res = self.client.query(in_q)
        out_res = self.client.query(out_q)
        speed_res = self.client.query(speed_q)
        in_err_res = self.client.query(in_err_q)
        out_err_res = self.client.query(out_err_q)

        # Build map of ifIndex -> name / status
        if_status_list = []
        down_count = 0
        up_count = 0

        for r in oper_res.get("results", []):
            if_idx = r["metric"].get("ifIndex")
            name = r["metric"].get("ifDescr") or f"Interface #{if_idx}"
            val = r.get("value")
            is_up = val == 1.0 or val == 1
            if is_up:
                up_count += 1
            else:
                down_count += 1
            if_status_list.append({
                "index": if_idx,
                "name": name,
                "operational_status": "UP" if is_up else "DOWN",
                "raw_value": val,
            })

        total_if = up_count + down_count
        if total_if > 0:
            status_health = "HEALTHY" if up_count > 0 else "WARNING"
            status_details = f"{up_count} UP, {down_count} DOWN of {total_if} interfaces"
        else:
            status_health = "UNKNOWN"
            status_details = "No interface status metrics found"

        # Traffic
        traffic_data = []
        max_in_rate = 0.0
        max_out_rate = 0.0
        for r in in_res.get("results", []):
            val = r.get("value") or 0.0
            if val > max_in_rate:
                max_in_rate = val
            if_idx = r["metric"].get("ifIndex")
            traffic_data.append({"index": if_idx, "in_bps": round(val, 2)})

        for r in out_res.get("results", []):
            val = r.get("value") or 0.0
            if val > max_out_rate:
                max_out_rate = val

        traffic_health = "HEALTHY" if in_res.get("success") else "UNKNOWN"
        traffic_details = (
            f"Peak Inbound: {round(max_in_rate / 1000, 2)} kbps, "
            f"Peak Outbound: {round(max_out_rate / 1000, 2)} kbps"
        )

        # Bandwidth utilization
        speed_map = {}
        for r in speed_res.get("results", []):
            if_idx = r["metric"].get("ifIndex")
            speed_mbps = r.get("value") or 0.0
            speed_map[if_idx] = speed_mbps

        bw_health = "HEALTHY"
        peak_bw_pct = 0.0
        for item in traffic_data:
            idx = item.get("index")
            speed = speed_map.get(idx)
            if speed and speed > 0:
                in_bps = item.get("in_bps", 0.0)
                bw_pct = round((in_bps / (speed * 1_000_000)) * 100, 2)
                if bw_pct > peak_bw_pct:
                    peak_bw_pct = bw_pct

        if peak_bw_pct >= BANDWIDTH_CRITICAL_THRESHOLD:
            bw_health = "CRITICAL"
        elif peak_bw_pct >= BANDWIDTH_WARNING_THRESHOLD:
            bw_health = "WARNING"
        bw_details = f"Peak interface bandwidth utilization: {peak_bw_pct}%"

        # Errors
        in_err_rate = sum(r.get("value") or 0.0 for r in in_err_res.get("results", []))
        out_err_rate = sum(r.get("value") or 0.0 for r in out_err_res.get("results", []))
        total_errors = in_err_rate + out_err_rate

        if total_errors > 0.0:
            err_health = "WARNING"
            err_details = f"Active packet errors detected: {round(total_errors, 2)} errors/sec"
        else:
            err_health = "HEALTHY"
            err_details = "0 errors detected on monitored interfaces"

        return {
            "status": {
                "status": status_health,
                "up_count": up_count,
                "down_count": down_count,
                "total": total_if,
                "interfaces": if_status_list,
                "details": status_details,
            },
            "traffic": {
                "status": traffic_health,
                "peak_in_bps": max_in_rate,
                "peak_out_bps": max_out_rate,
                "details": traffic_details,
            },
            "bandwidth": {
                "status": bw_health,
                "peak_utilization_pct": peak_bw_pct,
                "details": bw_details,
            },
            "errors": {
                "status": err_health,
                "in_error_rate": in_err_rate,
                "out_error_rate": out_err_rate,
                "details": err_details,
            },
        }

    # 9. OSPF Neighbor Status
    def _get_ospf_status(self, selector: str, role: Optional[str] = None) -> Dict[str, Any]:
        promql = f"ospfNbrState{{{selector}}}"
        res = self.client.query(promql)

        if not res["success"]:
            return {
                "status": "UNKNOWN",
                "value": None,
                "details": f"Query error: {res['error']}",
                "is_stale": False,
            }

        if not res["results"]:
            # If device role is a pure switch or device doesn't run OSPF
            is_switch = role and "switch" in role.lower()
            return {
                "status": "NOT_CONFIGURED" if is_switch else "NOT_CONFIGURED",
                "value": None,
                "details": "No active OSPF sessions found (OSPF not running or MIB not queried).",
                "is_stale": False,
            }

        neighbors = []
        all_full = True
        for r in res["results"]:
            state_val = r.get("value")
            # 8 = Full state in standard OSPF-MIB
            is_full = state_val == 8.0 or state_val == 8
            if not is_full:
                all_full = False
            neighbors.append({
                "neighbor": r["metric"].get("ospfNbrIpAddr") or r["metric"].get("neighbor_id", "unknown"),
                "state": "FULL" if is_full else f"STATE_{state_val}",
                "raw_value": state_val,
            })

        status = "HEALTHY" if all_full else "WARNING"
        details = f"{len(neighbors)} neighbor(s) established (All FULL)" if all_full else "One or more OSPF neighbors not in FULL state"

        return {
            "status": status,
            "neighbors": neighbors,
            "details": details,
            "all_full": all_full,
        }

    # 10. Network Latency
    def _get_latency(self, selector: str) -> Dict[str, Any]:
        promql = f"scrape_duration_seconds{{{selector}}} * 1000"
        res = self.client.query(promql)

        if not res["success"] or not res["results"]:
            return {
                "status": "UNKNOWN",
                "value": None,
                "latency_ms": None,
                "details": "Latency metric unavailable.",
                "is_stale": False,
            }

        first = res["results"][0]
        val = first.get("value")
        if val is None:
            return {"status": "UNKNOWN", "value": None, "details": "Non-numeric latency", "is_stale": False}

        val = round(val, 2)
        if val >= LATENCY_CRITICAL_MS:
            status = "CRITICAL"
        elif val >= LATENCY_WARNING_MS:
            status = "WARNING"
        else:
            status = "HEALTHY"

        return {
            "status": status,
            "value": val,
            "latency_ms": val,
            "details": f"SNMP transaction latency: {val} ms",
            "is_stale": first.get("is_stale", False),
            "age_seconds": first.get("age_seconds"),
        }
