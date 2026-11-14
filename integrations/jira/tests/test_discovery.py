from unittest.mock import MagicMock
import pytest

from integrations.jira.discovery import JiraDiscovery, JiraDiscoveryError


def test_discover_project_success():
    mock_client = MagicMock()
    mock_client.config.project_key = "OPS"
    mock_client.get_project.return_value = {
        "id": "10000",
        "key": "OPS",
        "name": "Operations Service Project",
        "projectTypeKey": "service_desk",
    }

    disco = JiraDiscovery(client=mock_client)
    res = disco.discover_project()

    assert res["id"] == "10000"
    assert res["key"] == "OPS"
    assert res["name"] == "Operations Service Project"


def test_discover_service_desk_success():
    mock_client = MagicMock()
    mock_client.config.project_key = "OPS"
    mock_client.get_project.return_value = {"id": "10000", "key": "OPS"}
    mock_client.get_service_desks.return_value = [
        {"id": "1", "projectId": "10000", "projectKey": "OPS", "projectName": "Operations Service Desk"},
        {"id": "2", "projectId": "20000", "projectKey": "IT", "projectName": "IT Helpdesk"},
    ]

    disco = JiraDiscovery(client=mock_client)
    sd = disco.discover_service_desk()

    assert sd["id"] == "1"
    assert sd["projectName"] == "Operations Service Desk"


def test_discover_service_desk_not_found_raises():
    mock_client = MagicMock()
    mock_client.config.project_key = "OPS"
    mock_client.get_project.return_value = {"id": "10000", "key": "OPS"}
    mock_client.get_service_desks.return_value = []

    disco = JiraDiscovery(client=mock_client)
    with pytest.raises(JiraDiscoveryError, match="No Jira Service Desk found for project"):
        disco.discover_service_desk()


def test_discover_incident_request_type():
    mock_client = MagicMock()
    mock_client.get_request_types.return_value = [
        {"id": "1", "name": "Get IT help", "description": "Need assistance"},
        {"id": "8", "name": "Report a system problem", "description": "System problem or incident"},
    ]

    disco = JiraDiscovery(client=mock_client)
    rt = disco.discover_incident_request_type("1")

    assert rt["id"] == "8"
    assert "Report a system problem" in rt["name"]


def test_discover_request_type_fields_and_options():
    mock_client = MagicMock()
    mock_client.get_request_type_fields.return_value = {
        "requestTypeFields": [
            {"fieldId": "summary", "name": "Summarize the problem", "required": True},
            {"fieldId": "description", "name": "Describe what happened", "required": True},
            {
                "fieldId": "customfield_10050",
                "name": "How urgently does this need to be fixed?",
                "required": False,
                "validValues": [
                    {"value": "10020", "label": "Critical"},
                    {"value": "10021", "label": "High"},
                ],
            },
            {
                "fieldId": "customfield_10004",
                "name": "How big of an impact is the problem?",
                "required": False,
                "validValues": [
                    {"value": "10000", "label": "Extensive / Widespread"},
                    {"value": "10001", "label": "Significant / Large"},
                ],
            },
            {"fieldId": "customfield_10045", "name": "Affected services", "required": False},
        ]
    }

    disco = JiraDiscovery(client=mock_client)
    fields = disco.discover_request_type_fields("1", "8")

    assert "summary" in fields["required_fields"]
    assert "description" in fields["required_fields"]
    assert fields["field_id_map"]["urgency"] == "customfield_10050"
    assert fields["field_id_map"]["impact"] == "customfield_10004"
    assert fields["urgency_options"]["Critical"] == "10020"
    assert fields["impact_options"]["Significant / Large"] == "10001"


def test_discover_incident_metadata_caching():
    mock_client = MagicMock()
    mock_client.config.project_key = "OPS"
    mock_client.get_project.return_value = {"id": "10000", "key": "OPS"}
    mock_client.get_service_desks.return_value = [{"id": "1", "projectId": "10000", "projectKey": "OPS"}]
    mock_client.get_request_types.return_value = [{"id": "8", "name": "Report a system problem"}]
    mock_client.get_request_type_fields.return_value = {
        "requestTypeFields": [{"fieldId": "summary", "required": True}]
    }

    disco = JiraDiscovery(client=mock_client)
    meta1 = disco.discover_incident_metadata()
    meta2 = disco.discover_incident_metadata()

    # Second call should use cache, client.get_project called once
    assert meta1 == meta2
    assert mock_client.get_project.call_count == 1
