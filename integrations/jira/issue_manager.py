import logging
from typing import Any, Dict, List, Optional

from integrations.jira.client import JiraAPIError, JiraClient

logger = logging.getLogger(__name__)


class JiraIssueManager:
    """Manages existing Jira issues, comments, transitions, and status retrieval."""

    def __init__(self, client: Optional[JiraClient] = None):
        self.client = client or JiraClient()

    def get_issue(self, issue_id_or_key: str) -> Dict[str, Any]:
        """Retrieve full details of an existing Jira issue."""
        return self.client.get_issue(issue_id_or_key)

    def get_issue_summary(self, issue_id_or_key: str) -> Dict[str, Any]:
        """Retrieve a standardized summary of an issue's status and lifecycle."""
        raw = self.get_issue(issue_id_or_key)
        fields = raw.get("fields", {})
        status_obj = fields.get("status", {})
        category_obj = status_obj.get("statusCategory", {})

        return {
            "key": raw.get("key"),
            "id": raw.get("id"),
            "summary": fields.get("summary"),
            "status": status_obj.get("name"),
            "status_category": category_obj.get("name"),
            "is_resolved": category_obj.get("key") == "done",
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "assignee": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
        }

    def get_status(self, issue_id_or_key: str) -> Dict[str, Any]:
        """Retrieve only the current workflow status of an issue."""
        summary = self.get_issue_summary(issue_id_or_key)
        return {
            "key": summary["key"],
            "status": summary["status"],
            "status_category": summary["status_category"],
            "is_resolved": summary["is_resolved"],
        }

    def add_comment(
        self,
        issue_id_or_key: str,
        comment: str,
        is_public: bool = True,
    ) -> Dict[str, Any]:
        """Add an operational update or comment to an issue."""
        if not comment or not comment.strip():
            raise ValueError("Comment text cannot be empty.")

        res = self.client.add_comment(issue_id_or_key, comment.strip(), is_public=is_public)
        logger.info("Added comment to issue %s", issue_id_or_key)
        return {
            "success": True,
            "issue_key": issue_id_or_key,
            "comment_id": res.get("id"),
        }

    def update_fields(self, issue_id_or_key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Update fields on an existing issue."""
        if not fields:
            raise ValueError("Fields dictionary cannot be empty.")

        self.client.update_issue(issue_id_or_key, fields)
        logger.info("Updated fields on issue %s", issue_id_or_key)
        return {"success": True, "issue_key": issue_id_or_key}

    def get_available_transitions(self, issue_id_or_key: str) -> List[Dict[str, Any]]:
        """List workflow transitions currently possible for the issue."""
        transitions = self.client.get_transitions(issue_id_or_key)
        return [
            {
                "id": str(t.get("id")),
                "name": t.get("name"),
                "to_status": t.get("to", {}).get("name"),
            }
            for t in transitions
        ]

    def transition_issue(
        self,
        issue_id_or_key: str,
        transition_name_or_id: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a workflow transition by transition name or numeric ID."""
        transitions = self.get_available_transitions(issue_id_or_key)
        target_id = None

        # Check if direct ID match
        for t in transitions:
            if t["id"] == str(transition_name_or_id):
                target_id = t["id"]
                break

        # Check by name (case-insensitive substring)
        if not target_id:
            for t in transitions:
                if transition_name_or_id.lower() in t["name"].lower():
                    target_id = t["id"]
                    break

        if not target_id:
            valid_names = [f"'{t['name']}' (ID: {t['id']})" for t in transitions]
            raise JiraAPIError(
                f"Transition '{transition_name_or_id}' is not available for issue {issue_id_or_key}. "
                f"Available transitions: {', '.join(valid_names) or 'None'}"
            )

        self.client.transition_issue(issue_id_or_key, target_id, comment=comment)
        logger.info("Transitioned issue %s using transition %s", issue_id_or_key, target_id)
        return {
            "success": True,
            "issue_key": issue_id_or_key,
            "transition_id": target_id,
        }

    def resolve_incident(
        self,
        issue_id_or_key: str,
        resolution_comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attempt to resolve or close an incident ticket."""
        comment_text = resolution_comment or "Automated recovery verified. Incident resolved."
        # Search for typical resolution transitions
        transitions = self.get_available_transitions(issue_id_or_key)
        resolution_keywords = ["resolve", "close", "done", "complete", "cancel"]

        for keyword in resolution_keywords:
            for t in transitions:
                if keyword in t["name"].lower() or keyword in (t.get("to_status") or "").lower():
                    return self.transition_issue(issue_id_or_key, t["id"], comment=comment_text)

        valid_names = [f"'{t['name']}'" for t in transitions]
        raise JiraAPIError(
            f"No resolution transition found for issue {issue_id_or_key}. Available: {', '.join(valid_names)}"
        )
