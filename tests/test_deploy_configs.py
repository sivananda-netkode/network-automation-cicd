import pytest
from unittest.mock import Mock, patch

from src.network.deploy_configs import get_device_configs


@patch("src.network.deploy_configs.NETBOX_URL", "http://netbox.example")
@patch("src.network.deploy_configs.NETBOX_TOKEN", "test-token")
@patch("src.network.deploy_configs.requests.get")
def test_get_device_configs_returns_all_eligible_devices(mock_get):
    mock_response = Mock()

    mock_response.json.return_value = {
        "results": [
            {
                "name": "R1",
                "primary_ip4": {"address": "192.168.1.1/24"},
                "local_context_data": {
                    "cli_config": "ip dhcp pool VLAN10\n network 192.168.10.0 255.255.255.0"
                },
                "site": {"name": "Hyderabad Netkode", "slug": "hyderabad-netkode"},
            },
            {
                "name": "SW1",
                "primary_ip4": {"address": "192.168.4.2/24"},
                "local_context_data": {
                    "cli_config": "vlan 10\n name ECE"
                },
                "site": {"name": "Hyderabad Netkode", "slug": "hyderabad-netkode"},
            },
        ],
        "next": None,
    }

    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    devices = get_device_configs()

    assert len(devices) == 2
    assert devices[0]["name"] == "R1"
    assert devices[0]["ip"] == "192.168.1.1"
    assert "ip dhcp pool VLAN10" in devices[0]["config"]
    assert devices[0]["site_slug"] == "hyderabad-netkode"

    assert devices[1]["name"] == "SW1"
    assert devices[1]["ip"] == "192.168.4.2"
    assert "vlan 10" in devices[1]["config"]
    assert devices[1]["site_slug"] == "hyderabad-netkode"


@patch("src.network.deploy_configs.NETBOX_URL", "http://netbox.example")
@patch("src.network.deploy_configs.NETBOX_TOKEN", "test-token")
@patch("src.network.deploy_configs.requests.get")
def test_get_device_configs_skips_devices_without_ip_or_config(mock_get):
    mock_response = Mock()

    mock_response.json.return_value = {
        "results": [
            {
                "name": "R1",
                "primary_ip4": {"address": "192.168.1.1/24"},
                "local_context_data": {
                    "cli_config": "hostname R1"
                },
            },
            {
                "name": "SW2",
                "primary_ip4": None,
                "local_context_data": {
                    "cli_config": "hostname SW2"
                },
            },
            {
                "name": "SW3",
                "primary_ip4": {"address": "192.168.5.2/24"},
                "local_context_data": {},
            },
        ],
        "next": None,
    }

    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    devices = get_device_configs()

    assert len(devices) == 1
    assert devices[0]["name"] == "R1"


@patch("src.network.deploy_configs.NETBOX_URL", "http://netbox.example")
@patch("src.network.deploy_configs.NETBOX_TOKEN", "test-token")
@patch("src.network.deploy_configs.requests.get")
def test_get_device_configs_handles_pagination(mock_get):
    first_page = Mock()
    first_page.json.return_value = {
        "results": [
            {
                "name": "R1",
                "primary_ip4": {"address": "192.168.1.1/24"},
                "local_context_data": {"cli_config": "hostname R1"},
            }
        ],
        "next": "http://netbox.example/api/dcim/devices/?offset=1",
    }

    second_page = Mock()
    second_page.json.return_value = {
        "results": [
            {
                "name": "SW1",
                "primary_ip4": {"address": "192.168.4.2/24"},
                "local_context_data": {"cli_config": "hostname SW1"},
            }
        ],
        "next": None,
    }

    first_page.raise_for_status.return_value = None
    second_page.raise_for_status.return_value = None

    mock_get.side_effect = [first_page, second_page]

    devices = get_device_configs()

    assert len(devices) == 2
    assert [device["name"] for device in devices] == ["R1", "SW1"]
    assert mock_get.call_count == 2


@patch("src.network.deploy_configs.NETBOX_URL", "http://netbox.example")
@patch("src.network.deploy_configs.NETBOX_TOKEN", "test-token")
@patch("src.network.deploy_configs.requests.get")
def test_get_device_configs_staging_environment_filter(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "name": "R1",
                "primary_ip4": {"address": "192.168.1.1/24"},
                "local_context_data": {"cli_config": "hostname R1"},
                "site": {"name": "Hyderabad Netkode", "slug": "hyderabad-netkode"},
            }
        ],
        "next": None,
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    devices = get_device_configs(environment="staging")

    assert len(devices) == 1
    assert devices[0]["name"] == "R1"
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["site"] == "hyderabad-netkode"


@patch("src.network.deploy_configs.NETBOX_URL", "http://netbox.example")
@patch("src.network.deploy_configs.NETBOX_TOKEN", "test-token")
@patch("src.network.deploy_configs.requests.get")
def test_get_device_configs_production_environment_filter(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "name": "R4",
                "primary_ip4": {"address": "192.168.6.1/24"},
                "local_context_data": {"cli_config": "hostname R4"},
                "site": {"name": "Vizag Netkode", "slug": "vizag-netkode"},
            },
            {
                "name": "switch3",
                "primary_ip4": {"address": "192.168.9.2/24"},
                "local_context_data": {"cli_config": "hostname switch3"},
                "site": {"name": "Vizag Netkode", "slug": "vizag-netkode"},
            },
        ],
        "next": None,
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    devices = get_device_configs(environment="production")

    assert len(devices) == 2
    assert devices[0]["name"] == "R4"
    assert devices[1]["name"] == "switch3"
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["site"] == "vizag-netkode"


@patch("src.network.deploy_configs.NETBOX_URL", "http://netbox.example")
@patch("src.network.deploy_configs.NETBOX_TOKEN", "test-token")
@patch("src.network.deploy_configs.requests.get")
def test_get_device_configs_cross_pollution_prevention(mock_get):
    # Simulate a mistake where production returns R1 (a staging device)
    mock_response = Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "name": "R1",
                "primary_ip4": {"address": "192.168.1.1/24"},
                "local_context_data": {"cli_config": "hostname R1"},
            }
        ],
        "next": None,
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    with pytest.raises(ValueError, match="CRITICAL CROSS-ENVIRONMENT VIOLATION"):
        get_device_configs(environment="production")
