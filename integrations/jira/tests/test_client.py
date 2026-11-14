from unittest.mock import MagicMock
import pytest
import requests

from integrations.jira.client import (
    JiraAPIError,
    JiraAuthenticationError,
    JiraClient,
    JiraClientError,
    JiraNotFoundError,
    JiraRateLimitError,
)
from integrations.jira.config import JiraConfig, JiraConfigError


def test_config_loading_and_token_redaction():
    cfg = JiraConfig(
        base_url="https://example.atlassian.net",
        email="dev@example.com",
        api_token="supersecrettoken123",
        project_key="OPS",
    )
    cfg.validate()
    repr_str = repr(cfg)
    assert "supersecrettoken123" not in repr_str
    assert "***REDACTED***" in repr_str
    assert cfg.project_key == "OPS"


def test_config_missing_variables_raises_error():
    cfg = JiraConfig(base_url="", email="", api_token="", project_key="")
    with pytest.raises(JiraConfigError, match="Missing required Jira configuration variables"):
        cfg.validate()


def test_client_auth_header_construction():
    cfg = JiraConfig(
        base_url="https://example.atlassian.net",
        email="user@test.com",
        api_token="mytoken",
        project_key="OPS",
    )
    client = JiraClient(config=cfg)
    auth_header = client.session.headers.get("Authorization")
    assert auth_header is not None
    assert auth_header.startswith("Basic ")
    # Verify mytoken is not bare in headers
    assert "mytoken" not in auth_header


def test_client_request_success_200():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"key": "OPS-1", "id": "10001"}
    mock_session.request.return_value = mock_resp

    cfg = JiraConfig("https://example.atlassian.net", "u@t.com", "tok", "OPS")
    client = JiraClient(config=cfg, session=mock_session)

    res = client.request("GET", "/rest/api/3/issue/OPS-1")
    assert res["key"] == "OPS-1"


def test_client_authentication_failure_401():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_session.request.return_value = mock_resp

    cfg = JiraConfig("https://example.atlassian.net", "u@t.com", "tok", "OPS")
    client = JiraClient(config=cfg, session=mock_session)

    with pytest.raises(JiraAuthenticationError, match="Jira authentication failed"):
        client.request("GET", "/rest/api/3/myself")


def test_client_resource_not_found_404():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_session.request.return_value = mock_resp

    cfg = JiraConfig("https://example.atlassian.net", "u@t.com", "tok", "OPS")
    client = JiraClient(config=cfg, session=mock_session)

    with pytest.raises(JiraNotFoundError, match="Resource not found"):
        client.request("GET", "/rest/api/3/issue/NONEXISTENT-99")


def test_client_rate_limiting_429():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "60"}
    mock_session.request.return_value = mock_resp

    cfg = JiraConfig("https://example.atlassian.net", "u@t.com", "tok", "OPS")
    client = JiraClient(config=cfg, session=mock_session)

    with pytest.raises(JiraRateLimitError) as exc_info:
        client.request("GET", "/rest/api/3/myself")
    assert exc_info.value.retry_after == 60


def test_client_timeout_handling():
    mock_session = MagicMock()
    mock_session.request.side_effect = requests.exceptions.Timeout("Read timeout")

    cfg = JiraConfig("https://example.atlassian.net", "u@t.com", "tok", "OPS", timeout=5.0)
    client = JiraClient(config=cfg, session=mock_session)

    with pytest.raises(JiraClientError, match="timed out"):
        client.request("GET", "/rest/api/3/myself")


def test_client_api_error_message_extraction():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "errorMessages": ["Field 'summary' is mandatory for this request."],
        "errors": {},
    }
    mock_session.request.return_value = mock_resp

    cfg = JiraConfig("https://example.atlassian.net", "u@t.com", "tok", "OPS")
    client = JiraClient(config=cfg, session=mock_session)

    with pytest.raises(JiraAPIError, match="Field 'summary' is mandatory"):
        client.request("POST", "/rest/servicedeskapi/request", json_data={})


def test_client_check_connection():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "emailAddress": "admin@example.com",
        "displayName": "Network Admin",
        "accountId": "acc-12345",
        "active": True,
    }
    mock_session.request.return_value = mock_resp

    cfg = JiraConfig("https://example.atlassian.net", "admin@example.com", "tok", "OPS")
    client = JiraClient(config=cfg, session=mock_session)

    status = client.check_connection()
    assert status["connected"] is True
    assert status["displayName"] == "Network Admin"
