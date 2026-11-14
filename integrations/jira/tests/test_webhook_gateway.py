"""Unit tests for the Prometheus Alertmanager Webhook Gateway."""

import io
import json
from unittest.mock import MagicMock

from integrations.jira.ticket_manager import JiraTicketManager
from integrations.jira.webhook_gateway import (
    AlertmanagerHTTPRequestHandler,
    JiraAlertProcessor,
)


def test_processor_firing_alert_creates_incident():
    """Verify that a firing alert properly maps to a NetworkIncident and calls process_network_alert."""
    mock_tm = MagicMock(spec=JiraTicketManager)
    mock_tm.process_network_alert.return_value = {
        "success": True,
        "action": "CREATED",
        "issue_key": "OPS-20",
        "summary": "Interface GigabitEthernet0/1 is DOWN on R1",
    }

    mock_nb = MagicMock()
    mock_nb.is_interface_monitored.return_value = True

    processor = JiraAlertProcessor(ticket_manager=mock_tm, netbox_validator=mock_nb)

    payload = {
        "receiver": "jira-webhook-gateway",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "NetworkInterfaceDown",
                    "device": "R1",
                    "instance": "192.168.1.1:9116",
                    "ifDescr": "GigabitEthernet0/1",
                    "ifIndex": "1",
                    "severity": "High",
                    "monitoring_source": "Prometheus / SNMP",
                },
                "annotations": {
                    "summary": "Interface GigabitEthernet0/1 is DOWN on R1",
                    "description": "Interface GigabitEthernet0/1 transitioned to operational DOWN (status=2).",
                },
                "startsAt": "2026-11-10T12:00:00Z",
            }
        ],
    }

    results = processor.process_alertmanager_payload(payload)

    assert len(results) == 1
    res = results[0]
    assert res["status"] == "firing"
    assert res["device"] == "R1"
    assert res["alert"] == "NetworkInterfaceDown:GigabitEthernet0/1"
    assert res["result"]["action"] == "CREATED"
    assert res["result"]["issue_key"] == "OPS-20"

    mock_tm.process_network_alert.assert_called_once()
    incident_arg = mock_tm.process_network_alert.call_args[0][0]
    assert incident_arg.device_name == "R1"
    assert incident_arg.alert_name == "NetworkInterfaceDown:GigabitEthernet0/1"
    assert incident_arg.alert_severity == "High"
    assert incident_arg.device_ip == "192.168.1.1"


def test_processor_resolved_alert_auto_closes_active_ticket():
    """Verify that a resolved alert finds the active ticket and calls resolve_ticket."""
    mock_tm = MagicMock(spec=JiraTicketManager)
    mock_tm.find_active_incident.return_value = {
        "key": "OPS-20",
        "id": "10020",
        "summary": "Interface GigabitEthernet0/1 is DOWN on R1",
    }
    mock_tm.resolve_ticket.return_value = {
        "success": True,
        "issue_key": "OPS-20",
        "transition_id": "111",
    }

    mock_nb = MagicMock()
    mock_nb.is_interface_monitored.return_value = True

    processor = JiraAlertProcessor(ticket_manager=mock_tm, netbox_validator=mock_nb)

    payload = {
        "receiver": "jira-webhook-gateway",
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "NetworkInterfaceDown",
                    "device": "R1",
                    "ifDescr": "GigabitEthernet0/1",
                },
                "endsAt": "2026-11-10T12:05:00Z",
            }
        ],
    }

    results = processor.process_alertmanager_payload(payload)

    assert len(results) == 1
    res = results[0]
    assert res["status"] == "resolved"
    assert res["action"] == "AUTO_RESOLVED"
    assert res["issue_key"] == "OPS-20"

    expected_fp = "network-incident:R1:NETWORKINTERFACEDOWN:GIGABITETHERNET0/1"
    mock_tm.find_active_incident.assert_called_once_with(expected_fp)
    mock_tm.resolve_ticket.assert_called_once()
    assert mock_tm.resolve_ticket.call_args[0][0] == "OPS-20"


def test_processor_resolved_alert_when_no_active_ticket_exists():
    """Verify graceful no-op when a resolved alert arrives for an already closed ticket."""
    mock_tm = MagicMock(spec=JiraTicketManager)
    mock_tm.find_active_incident.return_value = None

    mock_nb = MagicMock()
    mock_nb.is_interface_monitored.return_value = True

    processor = JiraAlertProcessor(ticket_manager=mock_tm, netbox_validator=mock_nb)

    payload = {
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "DeviceUnreachable",
                    "device": "SW1",
                },
            }
        ]
    }

    results = processor.process_alertmanager_payload(payload)

    assert len(results) == 1
    res = results[0]
    assert res["status"] == "resolved"
    assert res["action"] == "NOOP_NO_ACTIVE_TICKET"
    mock_tm.resolve_ticket.assert_not_called()


def test_processor_empty_alerts_returns_empty_list():
    """Verify handling of empty alert list."""
    mock_tm = MagicMock(spec=JiraTicketManager)
    mock_nb = MagicMock()
    mock_nb.is_interface_monitored.return_value = True

    processor = JiraAlertProcessor(ticket_manager=mock_tm, netbox_validator=mock_nb)

    results = processor.process_alertmanager_payload({"alerts": []})
    assert results == []


class DummyMockRequest:
    def makefile(self, *args, **kwargs):
        return io.BytesIO(b"")


def test_http_handler_get_healthz():
    """Verify that GET /healthz returns 200 with healthy status."""
    handler = AlertmanagerHTTPRequestHandler.__new__(AlertmanagerHTTPRequestHandler)
    handler.path = "/healthz"
    handler.wfile = io.BytesIO()

    responses = []
    headers = {}

    def mock_send_response(code):
        responses.append(code)

    def mock_send_header(k, v):
        headers[k] = v

    handler.send_response = mock_send_response
    handler.send_header = mock_send_header
    handler.end_headers = lambda: None

    handler.do_GET()

    assert responses == [200]
    assert headers["Content-Type"] == "application/json"

    body = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert body["status"] == "healthy"
    assert body["service"] == "jira-alertmanager-gateway"


def test_http_handler_post_alerts_success():
    """Verify that POST /api/v1/alerts dispatches to processor and returns 200."""
    handler = AlertmanagerHTTPRequestHandler.__new__(AlertmanagerHTTPRequestHandler)
    handler.path = "/api/v1/alerts"

    mock_processor = MagicMock(spec=JiraAlertProcessor)
    mock_processor.process_alertmanager_payload.return_value = [
        {"status": "firing", "action": "CREATED", "issue_key": "OPS-22"}
    ]
    handler.processor = mock_processor

    payload = {"alerts": [{"status": "firing"}]}
    raw_bytes = json.dumps(payload).encode("utf-8")
    handler.headers = {"Content-Length": str(len(raw_bytes))}
    handler.rfile = io.BytesIO(raw_bytes)
    handler.wfile = io.BytesIO()

    responses = []
    handler.send_response = lambda code: responses.append(code)
    handler.send_header = lambda k, v: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert responses == [200]
    mock_processor.process_alertmanager_payload.assert_called_once_with(payload)
    body = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert body["status"] == "success"
    assert body["processed_count"] == 1


def test_http_handler_not_found_404():
    """Verify that unknown routes return 404."""
    handler = AlertmanagerHTTPRequestHandler.__new__(AlertmanagerHTTPRequestHandler)
    handler.path = "/invalid_route"
    handler.wfile = io.BytesIO()

    responses = []
    handler.send_response = lambda code: responses.append(code)
    handler.send_header = lambda k, v: None
    handler.end_headers = lambda: None

    handler.do_GET()
    assert responses == [404]


def test_processor_skips_interface_when_not_monitored_in_netbox():
    """Verify that firing alert for an interface not documented in NetBox is skipped without ticketing."""
    mock_tm = MagicMock(spec=JiraTicketManager)
    mock_nb = MagicMock()
    mock_nb.is_interface_monitored.return_value = False

    processor = JiraAlertProcessor(ticket_manager=mock_tm, netbox_validator=mock_nb)

    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "NetworkInterfaceDown",
                    "device": "R1",
                    "ifDescr": "Serial2/3",
                    "severity": "High",
                },
                "annotations": {
                    "summary": "Interface Serial2/3 is DOWN on R1",
                },
            }
        ],
    }

    results = processor.process_alertmanager_payload(payload)

    assert len(results) == 1
    assert results[0]["action"] == "SKIPPED_NOT_IN_NETBOX"
    mock_nb.is_interface_monitored.assert_called_once_with("R1", "Serial2/3")
    mock_tm.process_network_alert.assert_not_called()

