"""Jira Service Management integration package for Network Automation CI/CD."""

from integrations.jira.client import (
    JiraAPIError,
    JiraAuthenticationError,
    JiraClient,
    JiraClientError,
    JiraNotFoundError,
    JiraRateLimitError,
)
from integrations.jira.config import JiraConfig, JiraConfigError, load_jira_config
from integrations.jira.discovery import JiraDiscovery, JiraDiscoveryError
from integrations.jira.issue_manager import JiraIssueManager
from integrations.jira.netbox_validator import NetBoxValidator
from integrations.jira.ticket_manager import JiraTicketManager, NetworkIncident
from integrations.jira.webhook_gateway import (
    JiraAlertProcessor,
    create_gateway_server,
    run_gateway,
)

__all__ = [
    "JiraConfig",
    "JiraConfigError",
    "load_jira_config",
    "JiraClient",
    "JiraClientError",
    "JiraAuthenticationError",
    "JiraNotFoundError",
    "JiraRateLimitError",
    "JiraAPIError",
    "JiraDiscovery",
    "JiraDiscoveryError",
    "JiraIssueManager",
    "JiraTicketManager",
    "NetworkIncident",
    "JiraAlertProcessor",
    "NetBoxValidator",
    "create_gateway_server",
    "run_gateway",
]

__version__ = "1.0.0"
