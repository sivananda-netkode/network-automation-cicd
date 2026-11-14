import base64
import logging
from typing import Any, Dict, List, Optional, Union
import requests

from integrations.jira.config import JiraConfig, load_jira_config

logger = logging.getLogger(__name__)


class JiraClientError(Exception):
    """Base exception for all Jira client errors."""
    pass


class JiraAuthenticationError(JiraClientError):
    """Raised when authentication with Jira fails (HTTP 401/403)."""
    pass


class JiraNotFoundError(JiraClientError):
    """Raised when a requested Jira resource is not found (HTTP 404)."""
    pass


class JiraRateLimitError(JiraClientError):
    """Raised when Jira API rate limit is exceeded (HTTP 429)."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class JiraAPIError(JiraClientError):
    """Raised when Jira returns an API error response (HTTP 400/500)."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class JiraClient:
    """Robust, reusable HTTP client for Jira Cloud and Jira Service Management REST APIs."""

    def __init__(
        self,
        config: Optional[JiraConfig] = None,
        session: Optional[requests.Session] = None,
    ):
        self.config = config or load_jira_config()
        self.session = session or requests.Session()
        self._init_session()

    def _init_session(self) -> None:
        """Configure default headers and HTTP Basic Authentication securely."""
        # HTTP Basic Auth format for Atlassian Cloud: base64(email:api_token)
        credentials = f"{self.config.email}:{self.config.api_token}"
        encoded_auth = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

        self.session.headers.update({
            "Authorization": f"Basic {encoded_auth}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-ExperimentalApi": "opt-in",
        })

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute an HTTP request against Jira REST API with secure error handling."""
        url = f"{self.config.base_url}/{endpoint.lstrip('/')}"
        method = method.upper()

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.config.timeout,
            )
        except requests.exceptions.Timeout as err:
            raise JiraClientError(f"Connection to Jira timed out after {self.config.timeout}s") from err
        except requests.exceptions.RequestException as err:
            raise JiraClientError(f"Unable to connect to Jira at {self.config.base_url}: {type(err).__name__}") from err

        return self._handle_response(response, endpoint)

    def _handle_response(self, response: requests.Response, endpoint: str) -> Any:
        """Parse response and map HTTP errors to specific exceptions without leaking secrets."""
        status_code = response.status_code

        # HTTP 204 No Content
        if status_code == 204:
            return {}

        # Success (200 OK, 201 Created)
        if status_code in (200, 201):
            try:
                return response.json()
            except ValueError:
                return {"text": response.text}

        # Authentication / Authorization Failure
        if status_code in (401, 403):
            raise JiraAuthenticationError(
                f"Jira authentication failed (HTTP {status_code}). Verify JIRA_EMAIL and JIRA_API_TOKEN."
            )

        # Resource Not Found
        if status_code == 404:
            raise JiraNotFoundError(f"Resource not found at endpoint: {endpoint}")

        # Rate Limiting
        if status_code == 429:
            retry_after_str = response.headers.get("Retry-After")
            retry_after = int(retry_after_str) if retry_after_str and retry_after_str.isdigit() else None
            raise JiraRateLimitError(
                f"Jira API rate limit exceeded. Retry after {retry_after or 'unknown'} seconds.",
                retry_after=retry_after,
            )

        # Extract structured Jira error messages safely
        error_detail = ""
        try:
            error_payload = response.json()
            messages = error_payload.get("errorMessages", [])
            field_errors = error_payload.get("errors", {})
            if messages:
                error_detail = "; ".join(messages)
            elif field_errors:
                error_detail = "; ".join(f"{k}: {v}" for k, v in field_errors.items())
            elif "message" in error_payload:
                error_detail = error_payload["message"]
        except Exception:
            error_detail = response.text[:200]

        msg = f"Jira API error (HTTP {status_code}) on {endpoint}: {error_detail}"
        raise JiraAPIError(msg, status_code=status_code)

    # -------------------------------------------------------------------------
    # Reusable High-Level API Methods
    # -------------------------------------------------------------------------

    def get_current_user(self) -> Dict[str, Any]:
        """Retrieve current authenticated user profile."""
        return self.request("GET", "/rest/api/3/myself")

    def check_connection(self) -> Dict[str, Any]:
        """Verify Jira credentials and connectivity."""
        try:
            user = self.get_current_user()
            return {
                "connected": True,
                "email": user.get("emailAddress", self.config.email),
                "displayName": user.get("displayName", "Unknown"),
                "accountId": user.get("accountId"),
                "active": user.get("active", True),
            }
        except JiraAuthenticationError as err:
            return {"connected": False, "error": str(err)}
        except JiraClientError as err:
            return {"connected": False, "error": str(err)}

    def get_project(self, project_key_or_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve project details by project key or ID."""
        key = (project_key_or_id or self.config.project_key).strip().upper()
        return self.request("GET", f"/rest/api/3/project/{key}")

    def get_service_desks(self) -> List[Dict[str, Any]]:
        """Retrieve all service desks accessible to the user."""
        res = self.request("GET", "/rest/servicedeskapi/servicedesk")
        return res.get("values", [])

    def get_request_types(self, service_desk_id: Union[int, str]) -> List[Dict[str, Any]]:
        """Retrieve all customer request types for a given service desk."""
        res = self.request("GET", f"/rest/servicedeskapi/servicedesk/{service_desk_id}/requesttype")
        return res.get("values", [])

    def get_request_type_fields(
        self,
        service_desk_id: Union[int, str],
        request_type_id: Union[int, str],
    ) -> Dict[str, Any]:
        """Retrieve dynamic field schema and options for a customer request type."""
        res = self.request(
            "GET",
            f"/rest/servicedeskapi/servicedesk/{service_desk_id}/requesttype/{request_type_id}/field",
        )
        return res

    def create_customer_request(
        self,
        service_desk_id: Union[int, str],
        request_type_id: Union[int, str],
        field_values: Dict[str, Any],
        raise_on_behalf_of: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new Jira Service Management customer request/incident."""
        payload: Dict[str, Any] = {
            "serviceDeskId": str(service_desk_id),
            "requestTypeId": str(request_type_id),
            "requestFieldValues": field_values,
        }
        if raise_on_behalf_of:
            payload["raiseOnBehalfOf"] = raise_on_behalf_of

        return self.request("POST", "/rest/servicedeskapi/request", json_data=payload)

    def get_issue(self, issue_id_or_key: str) -> Dict[str, Any]:
        """Retrieve an issue or incident ticket by issue key/ID."""
        return self.request("GET", f"/rest/api/3/issue/{issue_id_or_key}")

    def update_issue(self, issue_id_or_key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Update fields on an existing issue."""
        return self.request("PUT", f"/rest/api/3/issue/{issue_id_or_key}", json_data={"fields": fields})

    def get_transitions(self, issue_id_or_key: str) -> List[Dict[str, Any]]:
        """Retrieve available workflow transitions for an issue."""
        res = self.request("GET", f"/rest/api/3/issue/{issue_id_or_key}/transitions")
        return res.get("transitions", [])

    def transition_issue(
        self,
        issue_id_or_key: str,
        transition_id: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a workflow transition (e.g. resolve, close) on an issue."""
        payload: Dict[str, Any] = {
            "transition": {"id": str(transition_id)}
        }
        if comment:
            payload["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": comment}],
                                    }
                                ],
                            }
                        }
                    }
                ]
            }
        return self.request("POST", f"/rest/api/3/issue/{issue_id_or_key}/transitions", json_data=payload)

    def add_comment(
        self,
        issue_id_or_key: str,
        body: str,
        is_public: bool = True,
    ) -> Dict[str, Any]:
        """Add a comment to an issue via Jira Service Management or Jira Core."""
        # Try JSM customer request comment endpoint first
        try:
            payload = {"body": body, "public": is_public}
            return self.request(
                "POST",
                f"/rest/servicedeskapi/request/{issue_id_or_key}/comment",
                json_data=payload,
            )
        except JiraClientError:
            # Fallback to standard Jira Core issue comment
            adf_body = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": body}],
                        }
                    ],
                }
            }
            return self.request(
                "POST",
                f"/rest/api/3/issue/{issue_id_or_key}/comment",
                json_data=adf_body,
            )

    def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search issues using Jira Query Language (JQL) via Atlassian's modern search API."""
        payload: Dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
        }
        if fields:
            payload["fields"] = fields

        # Try modern /rest/api/3/search/jql first, fallback to /rest/api/3/search
        try:
            res = self.request("POST", "/rest/api/3/search/jql", json_data=payload)
            return res.get("issues", [])
        except JiraAPIError as err:
            if err.status_code == 404:
                res = self.request("POST", "/rest/api/3/search", json_data=payload)
                return res.get("issues", [])
            raise
