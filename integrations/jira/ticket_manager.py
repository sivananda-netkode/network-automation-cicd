from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, Union

from integrations.jira.client import JiraAPIError, JiraClient, JiraClientError
from integrations.jira.discovery import JiraDiscovery
from integrations.jira.issue_manager import JiraIssueManager

logger = logging.getLogger(__name__)


@dataclass
class NetworkIncident:
    """Represents a structured network incident alert."""
    device_name: str
    alert_name: str
    alert_severity: str = "High"
    alert_description: str = ""
    device_ip: Optional[str] = None
    device_role: Optional[str] = None
    site: Optional[str] = None
    first_detected: Optional[str] = None
    monitoring_source: str = "Prometheus / SNMP"
    device_status: str = "Degraded"
    telemetry: Dict[str, Any] = field(default_factory=dict)
    urgency: Optional[str] = None
    impact: Optional[str] = None
    summary: Optional[str] = None

    def get_fingerprint(self) -> str:
        """Deterministic correlation key to identify identical active incidents."""
        clean_dev = self.device_name.strip().upper()
        clean_alert = self.alert_name.strip().upper().replace(" ", "_")
        return f"network-incident:{clean_dev}:{clean_alert}"

    def get_formatted_summary(self) -> str:
        """Generate a concise, standardized incident summary."""
        if self.summary:
            return self.summary.strip()
        return f"[NETWORK INCIDENT] {self.device_name} - {self.alert_name} ({self.alert_severity})"

    def get_formatted_description(self) -> str:
        """Format a comprehensive network alert description."""
        ts = self.first_detected or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"=== NETWORK INCIDENT: {self.alert_name} ===",
            f"Device Name       : {self.device_name}",
            f"Device IP         : {self.device_ip or 'N/A'}",
            f"Device Role       : {self.device_role or 'N/A'}",
            f"Site Location     : {self.site or 'N/A'}",
            f"Device Status     : {self.device_status}",
            f"Alert Severity    : {self.alert_severity}",
            f"Monitoring Source : {self.monitoring_source}",
            f"First Detected    : {ts}",
            "",
            "--- ALERT DETAILS ---",
            self.alert_description or "Automated operational anomaly detected.",
        ]

        if self.telemetry:
            lines.append("")
            lines.append("--- LIVE TELEMETRY SNAPSHOT ---")
            for k, v in self.telemetry.items():
                clean_k = k.replace("_", " ").title()
                lines.append(f"- {clean_k}: {v}")

        lines.append("")
        lines.append(f"Correlation-Key: {self.get_fingerprint()}")
        lines.append("==============================================")
        return "\n".join(lines)


class JiraTicketManager:
    """Manages Jira Service Management incident lifecycle for network alerts."""

    def __init__(
        self,
        client: Optional[JiraClient] = None,
        discovery: Optional[JiraDiscovery] = None,
        issue_manager: Optional[JiraIssueManager] = None,
    ):
        self.client = client or JiraClient()
        self.discovery = discovery or JiraDiscovery(client=self.client)
        self.issue_manager = issue_manager or JiraIssueManager(client=self.client)

    def _normalize_incident(self, incident: Union[NetworkIncident, Dict[str, Any]]) -> NetworkIncident:
        """Convert a dictionary to a NetworkIncident object if necessary."""
        if isinstance(incident, NetworkIncident):
            return incident
        if isinstance(incident, dict):
            return NetworkIncident(
                device_name=incident.get("device_name") or incident.get("device", "Unknown"),
                alert_name=incident.get("alert_name") or incident.get("alert", "Network Anomaly"),
                alert_severity=incident.get("alert_severity") or incident.get("severity", "High"),
                alert_description=incident.get("alert_description") or incident.get("description", ""),
                device_ip=incident.get("device_ip") or incident.get("ip"),
                device_role=incident.get("device_role") or incident.get("role"),
                site=incident.get("site"),
                first_detected=incident.get("first_detected"),
                monitoring_source=incident.get("monitoring_source", "Prometheus / SNMP"),
                device_status=incident.get("device_status", "Degraded"),
                telemetry=incident.get("telemetry", {}),
                urgency=incident.get("urgency"),
                impact=incident.get("impact"),
                summary=incident.get("summary"),
            )
        raise ValueError("Incident must be a NetworkIncident instance or dictionary.")

    def create_incident_ticket(
        self,
        incident: Union[NetworkIncident, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a Jira Service Management customer request for a network incident."""
        inc = self._normalize_incident(incident)
        meta = self.discovery.discover_incident_metadata()

        service_desk_id = meta["service_desk"]["id"]
        request_type_id = meta["request_type"]["id"]
        field_map = meta["fields"]["field_id_map"]
        urgency_options = meta["fields"]["urgency_options"]
        impact_options = meta["fields"]["impact_options"]

        # 1. Build required field values
        summary_text = inc.get_formatted_summary()
        description_text = inc.get_formatted_description()

        request_fields: Dict[str, Any] = {
            field_map.get("summary", "summary"): summary_text,
            field_map.get("description", "description"): description_text,
        }

        # 2. Populate Urgency dynamically
        urgency_val = inc.urgency or inc.alert_severity
        urgency_field = field_map.get("urgency")
        if urgency_field and urgency_options:
            matched_option_id = None
            for label, opt_id in urgency_options.items():
                if label.lower() == urgency_val.lower():
                    matched_option_id = opt_id
                    break
            if not matched_option_id:
                # Default to Medium if not matched
                matched_option_id = urgency_options.get("Medium", list(urgency_options.values())[0])
            request_fields[urgency_field] = {"id": matched_option_id}

        # 3. Populate Impact dynamically
        impact_val = inc.impact
        impact_field = field_map.get("impact")
        if impact_field and impact_options:
            matched_impact_id = None
            if impact_val:
                for label, opt_id in impact_options.items():
                    if impact_val.lower() in label.lower():
                        matched_impact_id = opt_id
                        break
            if not matched_impact_id:
                # Default to Moderate / Limited if not specified
                for label, opt_id in impact_options.items():
                    if "moderate" in label.lower():
                        matched_impact_id = opt_id
                        break
                if not matched_impact_id:
                    matched_impact_id = list(impact_options.values())[0]
            request_fields[impact_field] = {"id": matched_impact_id}

        # 4. Validate that all required fields from Jira schema are satisfied
        required_fields = meta["fields"]["required_fields"]
        missing_fields = [f for f in required_fields if f not in request_fields or not request_fields[f]]
        if missing_fields:
            raise JiraAPIError(f"Cannot submit ticket: required fields are missing: {missing_fields}")

        # 5. Submit Customer Request to Jira Service Management API
        try:
            res = self.client.create_customer_request(
                service_desk_id=service_desk_id,
                request_type_id=request_type_id,
                field_values=request_fields,
            )
            issue_key = res.get("issueKey") or res.get("id")
            logger.info("Successfully created Jira incident request: %s", issue_key)
            return {
                "success": True,
                "action": "CREATED",
                "issue_key": issue_key,
                "issue_id": res.get("issueId"),
                "request_id": res.get("id"),
                "summary": summary_text,
                "status": res.get("currentStatus", {}).get("status", "Open"),
                "created_at": res.get("createdDate", {}).get("iso8601"),
                "fingerprint": inc.get_fingerprint(),
                "web_url": res.get("_links", {}).get("web"),
            }
        except JiraClientError as err:
            logger.error("Failed to create Jira incident: %s", err)
            raise

    def get_ticket(self, issue_key: str) -> Dict[str, Any]:
        """Retrieve ticket details."""
        return self.issue_manager.get_issue_summary(issue_key)

    def get_ticket_status(self, issue_key: str) -> Dict[str, Any]:
        """Retrieve ticket status."""
        return self.issue_manager.get_status(issue_key)

    def add_ticket_comment(self, issue_key: str, comment: str, is_public: bool = True) -> Dict[str, Any]:
        """Add a comment to an existing ticket."""
        return self.issue_manager.add_comment(issue_key, comment, is_public=is_public)

    def transition_ticket(
        self,
        issue_key: str,
        transition_name_or_id: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a workflow transition on a ticket."""
        return self.issue_manager.transition_issue(issue_key, transition_name_or_id, comment=comment)

    def resolve_ticket(
        self,
        issue_key: str,
        resolution_comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attempt to resolve or close an incident ticket."""
        return self.issue_manager.resolve_incident(issue_key, resolution_comment=resolution_comment)

    def find_active_incident(
        self,
        incident_or_fingerprint: Union[NetworkIncident, str],
    ) -> Optional[Dict[str, Any]]:
        """Search for an existing active (not resolved) ticket with a matching correlation key."""
        if isinstance(incident_or_fingerprint, NetworkIncident):
            fingerprint = incident_or_fingerprint.get_fingerprint()
        else:
            fingerprint = str(incident_or_fingerprint).strip()

        project_key = self.client.config.project_key
        # Search for open issues in this project containing the fingerprint
        jql = f'project = "{project_key}" AND statusCategory != Done AND description ~ "\\"{fingerprint}\\""'

        try:
            issues = self.client.search_issues(jql=jql, max_results=5, fields=["summary", "status", "description", "created"])
        except JiraClientError as err:
            logger.warning("JQL search for duplicate detection failed (%s). Falling back to search without exact phrase.", err)
            fallback_jql = f'project = "{project_key}" AND statusCategory != Done'
            try:
                issues = self.client.search_issues(jql=fallback_jql, max_results=20, fields=["summary", "status", "description", "created"])
            except JiraClientError:
                return None

        # Confirm exact fingerprint match in description
        for iss in issues:
            desc = (iss.get("fields", {}).get("description") or "")
            # Jira ADF or plain text description
            desc_text = str(desc)
            if fingerprint in desc_text:
                return {
                    "key": iss.get("key"),
                    "id": iss.get("id"),
                    "summary": iss.get("fields", {}).get("summary"),
                    "status": (iss.get("fields", {}).get("status") or {}).get("name"),
                    "fingerprint": fingerprint,
                }

        return None

    def process_network_alert(
        self,
        incident: Union[NetworkIncident, Dict[str, Any]],
        update_comment_if_duplicate: bool = True,
    ) -> Dict[str, Any]:
        """Process an alert with automated duplicate prevention.

        If an active ticket already exists for this (device, alert), appends an update
        comment instead of creating a duplicate. Otherwise creates a new incident.
        """
        inc = self._normalize_incident(incident)
        fingerprint = inc.get_fingerprint()

        existing = self.find_active_incident(inc)
        if existing:
            issue_key = existing["key"]
            logger.info("Found existing active incident %s for fingerprint %s", issue_key, fingerprint)

            if update_comment_if_duplicate:
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                comment_lines = [
                    f"[AUTOMATED ALERT RE-OCCURRENCE: {inc.alert_name}]",
                    f"Timestamp : {now_str}",
                    f"Severity  : {inc.alert_severity}",
                    f"Status    : {inc.device_status}",
                ]
                if inc.telemetry:
                    comment_lines.append("\nLatest Telemetry Snapshot:")
                    for k, v in inc.telemetry.items():
                        clean_k = k.replace("_", " ").title()
                        comment_lines.append(f"- {clean_k}: {v}")

                comment_lines.append(f"\nAlert remains active on device {inc.device_name}.")
                comment_body = "\n".join(comment_lines)
                self.add_ticket_comment(issue_key, comment_body)

            return {
                "success": True,
                "action": "UPDATED_EXISTING",
                "issue_key": issue_key,
                "issue_id": existing.get("id"),
                "summary": existing.get("summary"),
                "fingerprint": fingerprint,
                "message": f"Active incident {issue_key} already exists. Added operational update comment.",
            }

        # No duplicate found -> Create fresh incident
        return self.create_incident_ticket(inc)
