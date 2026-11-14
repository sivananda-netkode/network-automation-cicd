import pytest
from unittest.mock import Mock, patch

from src.netbox.get_devices import get_devices


@patch("src.netbox.get_devices.NETBOX_URL", "http://netbox.example")
@patch("src.netbox.get_devices.NETBOX_TOKEN", "test-token")
@patch("src.netbox.get_devices.requests.get")
def test_get_devices_returns_netbox_inventory(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "name": "R1",
                "primary_ip4": {"address": "192.168.1.1/24"},
                "role": {"name": "Router"},
                "status": {"label": "Active"},
                "site": {"name": "Hyderabad Netkode", "slug": "hyderabad-netkode"},
            },
            {
                "name": "SW1",
                "primary_ip4": {"address": "192.168.4.2/24"},
                "role": {"name": "Switch"},
                "status": {"label": "Active"},
                "site": {"name": "Hyderabad Netkode", "slug": "hyderabad-netkode"},
            },
        ]
    }

    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    devices = get_devices()

    assert len(devices) == 2

    assert devices[0]["name"] == "R1"
    assert devices[0]["ip"] == "192.168.1.1"
    assert devices[0]["role"] == "Router"
    assert devices[0]["site_slug"] == "hyderabad-netkode"

    assert devices[1]["name"] == "SW1"
    assert devices[1]["ip"] == "192.168.4.2"
    assert devices[1]["role"] == "Switch"
    assert devices[1]["site_slug"] == "hyderabad-netkode"

    mock_get.assert_called_once()


@patch("src.netbox.get_devices.NETBOX_URL", "http://netbox.example")
@patch("src.netbox.get_devices.NETBOX_TOKEN", "test-token")
@patch("src.netbox.get_devices.requests.get")
def test_get_devices_staging_environment_filter(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "name": "R1",
                "primary_ip4": {"address": "192.168.1.1/24"},
                "role": {"name": "Router"},
                "status": {"label": "Active"},
                "site": {"name": "Hyderabad Netkode", "slug": "hyderabad-netkode"},
            }
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    devices = get_devices(environment="staging")

    assert len(devices) == 1
    assert devices[0]["name"] == "R1"
    # Verify query params included site="hyderabad-netkode"
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["site"] == "hyderabad-netkode"
    assert "site_id" not in kwargs["params"]


@patch("src.netbox.get_devices.NETBOX_URL", "http://netbox.example")
@patch("src.netbox.get_devices.NETBOX_TOKEN", "test-token")
@patch("src.netbox.get_devices.requests.get")
def test_get_devices_production_environment_filter(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "name": "R4",
                "primary_ip4": {"address": "192.168.6.1/24"},
                "role": {"name": "Router"},
                "status": {"label": "Active"},
                "site": {"name": "Vizag Netkode", "slug": "vizag-netkode"},
            },
            {
                "name": "switch3",
                "primary_ip4": {"address": "192.168.9.2/24"},
                "role": {"name": "Switch"},
                "status": {"label": "Active"},
                "site": {"name": "Vizag Netkode", "slug": "vizag-netkode"},
            },
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    devices = get_devices(environment="production")

    assert len(devices) == 2
    assert devices[0]["name"] == "R4"
    assert devices[1]["name"] == "switch3"
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["site"] == "vizag-netkode"
    assert "site_id" not in kwargs["params"]


@patch("src.netbox.get_devices.NETBOX_URL", "http://netbox.example")
@patch("src.netbox.get_devices.NETBOX_TOKEN", "test-token")
@patch("src.netbox.get_devices.requests.get")
def test_get_devices_cross_pollution_prevention(mock_get):
    # Simulate a mistake where production inventory returned a staging device
    mock_response = Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "name": "R1",  # R1 is staging device!
                "primary_ip4": {"address": "192.168.1.1/24"},
                "role": {"name": "Router"},
                "status": {"label": "Active"},
            }
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    with pytest.raises(ValueError, match="CRITICAL CROSS-ENVIRONMENT VIOLATION"):
        get_devices(environment="production")
