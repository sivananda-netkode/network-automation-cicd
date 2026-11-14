"""Prometheus Alertmanager Webhook Gateway for Jira Service Management.

Listens for incoming alert notifications from Prometheus Alertmanager,
transforms network alert payloads into NetworkIncident objects, and manages
automated incident creation, deduplication, and resolution in Jira Service Management.
"""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from typing import Any, Dict, List, Optional
import urllib.parse

from integrations.jira.client import JiraClient
from integrations.jira.config import load_jira_config
from integrations.jira.netbox_validator import NetBoxValidator
from integrations.jira.ticket_manager import JiraTicketManager, NetworkIncident

logger = logging.getLogger(__name__)


class JiraAlertProcessor:
    """Processes Alertmanager alert payloads and triggers Jira incident lifecycle actions."""

    def __init__(
        self,
        ticket_manager: Optional[JiraTicketManager] = None,
        netbox_validator: Optional[NetBoxValidator] = None,
    ):
        if ticket_manager:
            self.ticket_manager = ticket_manager
        else:
            config = load_jira_config()
            client = JiraClient(config)
            self.ticket_manager = JiraTicketManager(client=client)

        self.netbox_validator = netbox_validator or NetBoxValidator()

    def process_alertmanager_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process incoming Alertmanager webhook payload containing multiple alerts."""
        alerts = payload.get("alerts", [])
        if not alerts:
            logger.info("Received empty alert list from Alertmanager.")
            return []

        results: List[Dict[str, Any]] = []

        for alert in alerts:
            status = alert.get("status", "firing").lower()
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})

            device_name = labels.get("device") or labels.get("instance") or "Network-Device"
            base_alert = labels.get("alertname", "NetworkAlert")
            if_descr = labels.get("ifDescr")
            alert_name = f"{base_alert}:{if_descr}" if if_descr else base_alert

            if status == "firing":
                res = self._handle_firing_alert(device_name, alert_name, labels, annotations, alert)
                results.append(res)
            elif status == "resolved":
                res = self._handle_resolved_alert(device_name, alert_name, labels, alert)
                results.append(res)
            else:
                logger.warning("Unknown alert status: %s", status)
                results.append({"status": status, "action": "IGNORED_UNKNOWN_STATUS"})

        return results

    def _handle_firing_alert(
        self,
        device_name: str,
        alert_name: str,
        labels: Dict[str, str],
        annotations: Dict[str, str],
        raw_alert: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Convert a firing alert into a NetworkIncident and process via JiraTicketManager."""
        if_descr = labels.get("ifDescr")
        if if_descr and not self.netbox_validator.is_interface_monitored(device_name, if_descr):
            logger.info("Ignoring firing alert for %s:%s - not active/enabled in NetBox SSoT.", device_name, if_descr)
            return {
                "status": "firing",
                "device": device_name,
                "alert": alert_name,
                "action": "SKIPPED_NOT_IN_NETBOX",
                "message": f"Interface {if_descr} on {device_name} is not documented/enabled in NetBox SSoT.",
            }

        severity = labels.get("severity", "High").capitalize()
        instance_ip = labels.get("instance", "").split(":")[0] if labels.get("instance") else None
        role = labels.get("role", "Router" if "R" in device_name.upper() else "Switch")
        monitoring_source = labels.get("monitoring_source", "Prometheus / SNMP")

        summary = annotations.get("summary") or f"[ALERT] {alert_name} on {device_name} ({severity})"
        description = annotations.get("description") or f"Alert {alert_name} firing on {device_name}."

        telemetry: Dict[str, Any] = {
            "starts_at": raw_alert.get("startsAt"),
            "generator_url": raw_alert.get("generatorURL", ""),
        }
        for k in ["ifIndex", "ifDescr", "job", "instance"]:
            if k in labels:
                telemetry[k] = labels[k]

        incident = NetworkIncident(
            device_name=device_name,
            alert_name=alert_name,
            alert_severity=severity,
            alert_description=description,
            device_ip=instance_ip,
            device_role=role,
            monitoring_source=monitoring_source,
            device_status="Down" if ("Down" in alert_name or "Unreachable" in alert_name) else "Degraded",
            telemetry=telemetry,
            summary=summary,
        )

        logger.info("Processing firing alert for %s (%s)", device_name, alert_name)
        res = self.ticket_manager.process_network_alert(incident)
        return {
            "status": "firing",
            "device": device_name,
            "alert": alert_name,
            "result": res,
        }

    def _handle_resolved_alert(
        self,
        device_name: str,
        alert_name: str,
        labels: Dict[str, str],
        raw_alert: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Auto-resolve the active Jira incident corresponding to the cleared alert."""
        clean_dev = device_name.strip().upper()
        clean_alert = alert_name.strip().upper().replace(" ", "_")
        fingerprint = f"network-incident:{clean_dev}:{clean_alert}"

        logger.info("Processing resolved alert for fingerprint %s", fingerprint)
        existing = self.ticket_manager.find_active_incident(fingerprint)

        if not existing:
            logger.info("No active ticket found for resolved alert %s", fingerprint)
            return {
                "status": "resolved",
                "device": device_name,
                "alert": alert_name,
                "action": "NOOP_NO_ACTIVE_TICKET",
                "fingerprint": fingerprint,
            }

        issue_key = existing["key"]
        resolved_at = raw_alert.get("endsAt") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        comment = (
            f"[AUTO-RESOLUTION: {alert_name}]\n"
            f"Prometheus Alertmanager reports that this alert has CLEARED.\n"
            f"Device       : {device_name}\n"
            f"Resolved At  : {resolved_at}\n"
            f"Operational telemetry confirms normal service restored."
        )

        try:
            res = self.ticket_manager.resolve_ticket(issue_key, resolution_comment=comment)
            logger.info("Successfully auto-resolved ticket %s for %s", issue_key, fingerprint)
            return {
                "status": "resolved",
                "device": device_name,
                "alert": alert_name,
                "action": "AUTO_RESOLVED",
                "issue_key": issue_key,
                "transition_result": res,
            }
        except Exception as err:
            logger.error("Failed to auto-resolve ticket %s: %s", issue_key, err)
            return {
                "status": "resolved",
                "device": device_name,
                "alert": alert_name,
                "action": "RESOLUTION_FAILED",
                "issue_key": issue_key,
                "error": str(err),
            }


class AlertmanagerHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Prometheus Alertmanager Webhooks."""

    processor: Optional[JiraAlertProcessor] = None

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        """Handle health check endpoint."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/healthz", "/health"):
            self._send_json(200, {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service": "jira-alertmanager-gateway",
            })
        else:
            self._send_json(404, {"error": "Not Found", "valid_endpoints": ["/healthz", "/api/v1/alerts"]})

    def do_POST(self) -> None:
        """Handle Alertmanager webhook notifications."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ("/api/v1/alerts", "/alerts"):
            self._send_json(404, {"error": "Not Found", "valid_endpoints": ["/api/v1/alerts"]})
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_json(400, {"error": "Empty request body"})
                return

            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body)
        except Exception as err:
            logger.warning("Malformed JSON received: %s", err)
            self._send_json(400, {"error": f"Invalid JSON payload: {err}"})
            return

        processor = self.processor or JiraAlertProcessor()
        try:
            results = processor.process_alertmanager_payload(payload)
            self._send_json(200, {
                "status": "success",
                "processed_count": len(results),
                "results": results,
            })
        except Exception as err:
            logger.error("Error processing Alertmanager payload: %s", err, exc_info=True)
            self._send_json(500, {"error": f"Internal server error: {err}"})

    def log_message(self, format: str, *args: Any) -> None:
        """Redirect server logs to standard logger."""
        logger.info("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)


def create_gateway_server(
    host: str = "0.0.0.0",
    port: int = 5050,
    processor: Optional[JiraAlertProcessor] = None,
) -> ThreadingHTTPServer:
    """Factory to create a configured ThreadingHTTPServer instance."""
    handler_class = AlertmanagerHTTPRequestHandler
    handler_class.processor = processor or JiraAlertProcessor()
    server = ThreadingHTTPServer((host, port), handler_class)
    return server


def run_gateway(host: str = "0.0.0.0", port: int = 5050) -> None:
    """Run the Alertmanager Webhook Gateway."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting Jira Alertmanager Webhook Gateway on %s:%d ...", host, port)
    server = create_gateway_server(host=host, port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down gateway server...")
        server.server_close()


if __name__ == "__main__":
    run_gateway()

