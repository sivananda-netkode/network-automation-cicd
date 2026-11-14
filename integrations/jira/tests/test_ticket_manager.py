from unittest.mock import MagicMock
import pytest

from integrations.jira.client import JiraAPIError
from integrations.jira.ticket_manager import JiraTicketManager, NetworkIncident


@pytest.fixture
def mock_metadata():
    return {
        "project": {"id": "10000", "key": "OPS"},
        "service_desk": {"id": "1", "projectName": "Operations Service Desk"},
        "request_type": {"id": "8", "name": "Report a system problem"},
        "fields": {
            "required_fields": ["summary", "description"],
            "field_id_map": {
                "summary": "summary",
                "description": "description",
                "urgency": "customfield_10050",
                "impact": "customfield_10004",
            },
            "urgency_options": {
                "Critical": "10020",
                "High": "10021",
                "Medium": "10022",
                "Low": "10023",
            },
            "impact_options": {
                "Extensive / Widespread": "10000",
                "Significant / Large": "10001",
                "Moderate / Limited": "10002",
                "Minor / Localized": "10003",
            },
        },
    }


def test_network_incident_fingerprint_and_formatting():
    inc = NetworkIncident(
        device_name="SW1",
        alert_name="INTERFACE_DOWN",
        alert_severity="High",
        device_ip="192.168.4.2",
        device_role="Switch",
        telemetry={"interface": "GigabitEthernet0/1", "status": "DOWN"},
    )
    assert inc.get_fingerprint() == "network-incident:SW1:INTERFACE_DOWN"
    summary = inc.get_formatted_summary()
    assert "[NETWORK INCIDENT] SW1 - INTERFACE_DOWN (High)" == summary
    desc = inc.get_formatted_description()
    assert "Device Name       : SW1" in desc
    assert "Interface: GigabitEthernet0/1" in desc
    assert "network-incident:SW1:INTERFACE_DOWN" in desc


def test_create_incident_ticket_constructs_jsm_payload(mock_metadata):
    mock_client = MagicMock()
    mock_client.create_customer_request.return_value = {
        "issueKey": "OPS-101",
        "issueId": "10101",
        "id": "req-101",
        "currentStatus": {"status": "Waiting for support"},
        "_links": {"web": "https://example.atlassian.net/servicedesk/customer/portal/1/OPS-101"},
    }

    mock_discovery = MagicMock()
    mock_discovery.discover_incident_metadata.return_value = mock_metadata

    tm = JiraTicketManager(client=mock_client, discovery=mock_discovery)
    inc = NetworkIncident(
        device_name="R1",
        alert_name="BGP_SESSION_DOWN",
        alert_severity="Critical",
        device_ip="192.168.1.1",
        urgency="Critical",
        impact="Extensive / Widespread",
    )

    res = tm.create_incident_ticket(inc)

    assert res["success"] is True
    assert res["issue_key"] == "OPS-101"
    assert res["action"] == "CREATED"

    # Verify JSM API call parameters
    mock_client.create_customer_request.assert_called_once()
    call_kwargs = mock_client.create_customer_request.call_args.kwargs
    assert call_kwargs["service_desk_id"] == "1"
    assert call_kwargs["request_type_id"] == "8"

    fields = call_kwargs["field_values"]
    assert "R1 - BGP_SESSION_DOWN" in fields["summary"]
    assert fields["customfield_10050"] == {"id": "10020"}  # Critical mapped
    assert fields["customfield_10004"] == {"id": "10000"}  # Extensive mapped


def test_create_incident_ticket_missing_required_fields_fails(mock_metadata):
    mock_client = MagicMock()
    mock_discovery = MagicMock()
    # Force required field that is not populated
    mock_metadata["fields"]["required_fields"] = ["summary", "description", "customfield_mandatory"]
    mock_discovery.discover_incident_metadata.return_value = mock_metadata

    tm = JiraTicketManager(client=mock_client, discovery=mock_discovery)
    inc = NetworkIncident(device_name="R1", alert_name="LATENCY_SPIKE")

    with pytest.raises(JiraAPIError, match="required fields are missing"):
        tm.create_incident_ticket(inc)


def test_duplicate_prevention_routes_to_comment_when_active_ticket_exists(mock_metadata):
    mock_client = MagicMock()
    mock_client.config.project_key = "OPS"
    # Return existing open issue with matching fingerprint in description
    mock_client.search_issues.return_value = [
        {
            "key": "OPS-50",
            "id": "10050",
            "fields": {
                "summary": "[NETWORK INCIDENT] R1 - HIGH_CPU",
                "description": "Correlation-Key: network-incident:R1:HIGH_CPU",
                "status": {"name": "In Progress"},
            },
        }
    ]

    mock_discovery = MagicMock()
    mock_discovery.discover_incident_metadata.return_value = mock_metadata

    tm = JiraTicketManager(client=mock_client, discovery=mock_discovery)
    inc = NetworkIncident(device_name="R1", alert_name="HIGH_CPU", alert_severity="High")

    res = tm.process_network_alert(inc)

    assert res["action"] == "UPDATED_EXISTING"
    assert res["issue_key"] == "OPS-50"
    # Verify create_customer_request was NOT called
    mock_client.create_customer_request.assert_not_called()
    # Verify comment was added to the existing ticket
    mock_client.add_comment.assert_called_once()


def test_duplicate_prevention_creates_fresh_ticket_when_no_active_ticket(mock_metadata):
    mock_client = MagicMock()
    mock_client.config.project_key = "OPS"
    mock_client.search_issues.return_value = []  # No existing tickets
    mock_client.create_customer_request.return_value = {
        "issueKey": "OPS-51",
        "id": "req-51",
        "currentStatus": {"status": "Open"},
    }

    mock_discovery = MagicMock()
    mock_discovery.discover_incident_metadata.return_value = mock_metadata

    tm = JiraTicketManager(client=mock_client, discovery=mock_discovery)
    inc = NetworkIncident(device_name="R1", alert_name="PACKET_LOSS")

    res = tm.process_network_alert(inc)

    assert res["action"] == "CREATED"
    assert res["issue_key"] == "OPS-51"
    mock_client.create_customer_request.assert_called_once()


def test_ticket_retrieval_and_status():
    mock_client = MagicMock()
    mock_client.get_issue.return_value = {
        "key": "OPS-12",
        "id": "10012",
        "fields": {
            "summary": "Switch port flapping",
            "status": {"name": "Resolved", "statusCategory": {"key": "done", "name": "Done"}},
            "created": "2026-11-06T10:00:00.000+0000",
            "updated": "2026-11-06T12:00:00.000+0000",
            "assignee": {"displayName": "Sivananda"},
        },
    }

    tm = JiraTicketManager(client=mock_client)
    summary = tm.get_ticket("OPS-12")

    assert summary["key"] == "OPS-12"
    assert summary["status"] == "Resolved"
    assert summary["is_resolved"] is True
    assert summary["assignee"] == "Sivananda"


def test_resolve_ticket_transitions_issue():
    mock_client = MagicMock()
    mock_client.get_transitions.return_value = [
        {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
        {"id": "31", "name": "Resolve this issue", "to": {"name": "Resolved"}},
    ]

    tm = JiraTicketManager(client=mock_client)
    res = tm.resolve_ticket("OPS-12", resolution_comment="Restored OSPF adjacency")

    assert res["success"] is True
    assert res["transition_id"] == "31"
    mock_client.transition_issue.assert_called_once_with(
        "OPS-12", "31", comment="Restored OSPF adjacency"
    )
