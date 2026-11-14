from unittest.mock import MagicMock, patch
import pytest

from src.network.deployment_engine import (
    deploy_device,
    get_configuration_commands,
    prepare_deployment_plans,
)


def test_get_configuration_commands_filters_session_commands():
    raw_commands = [
        "enable",
        "configure terminal",
        "interface GigabitEthernet0/1",
        "ip address 192.168.10.1 255.255.255.0",
        "no shutdown",
        "exit",
        "write memory",
        "copy running-config startup-config",
    ]

    filtered = get_configuration_commands(raw_commands)

    assert "enable" not in filtered
    assert "configure terminal" not in filtered
    assert "write memory" not in filtered
    assert "copy running-config startup-config" not in filtered
    assert "interface GigabitEthernet0/1" in filtered
    assert "ip address 192.168.10.1 255.255.255.0" in filtered
    assert "no shutdown" in filtered
    assert "exit" in filtered


def test_prepare_deployment_plans_rejects_invalid_mode():
    with pytest.raises(ValueError, match="Invalid deployment mode"):
        prepare_deployment_plans(mode="destructive_auto")


@patch("src.network.deployment_engine.ConnectHandler")
def test_deploy_device_blocks_on_hostname_mismatch(mock_connect):
    mock_conn_instance = MagicMock()
    # Device is R4, but connected device responds with R1 prompt
    mock_conn_instance.find_prompt.return_value = "R1#"
    mock_connect.return_value.__enter__.return_value = mock_conn_instance

    plan = {
        "name": "R4",
        "ip": "192.168.6.1",
        "commands": ["interface GigabitEthernet0/1", "no shutdown"],
        "environment": "production",
    }

    with pytest.raises(RuntimeError, match="CRITICAL HOSTNAME MISMATCH"):
        deploy_device(plan, environment="production")


@patch("src.network.deployment_engine.ConnectHandler")
def test_deploy_device_blocks_on_syntax_error(mock_connect):
    mock_conn_instance = MagicMock()
    mock_conn_instance.find_prompt.return_value = "R4#"
    mock_conn_instance.send_config_set.return_value = "% Invalid input detected at '^' marker."
    mock_connect.return_value.__enter__.return_value = mock_conn_instance

    plan = {
        "name": "R4",
        "ip": "192.168.6.1",
        "commands": ["interface GigabitEthernet0/1", "bad_syntax_command"],
        "environment": "production",
    }

    with pytest.raises(RuntimeError, match="Device returned a configuration error"):
        deploy_device(plan, environment="production")


@patch("src.network.deployment_engine.ConnectHandler")
def test_deploy_device_success(mock_connect):
    mock_conn_instance = MagicMock()
    mock_conn_instance.find_prompt.return_value = "R4#"
    mock_conn_instance.send_config_set.return_value = "interface GigabitEthernet0/1\nno shutdown"
    mock_conn_instance.send_command_timing.return_value = "[OK]\nBuilding configuration..."
    mock_connect.return_value.__enter__.return_value = mock_conn_instance

    plan = {
        "name": "R4",
        "ip": "192.168.6.1",
        "commands": ["interface GigabitEthernet0/1", "no shutdown"],
        "environment": "production",
    }

    duration = deploy_device(plan, environment="production")
    assert duration >= 0.0
    mock_conn_instance.send_config_set.assert_called_once()
    mock_conn_instance.send_command_timing.assert_called_with("write memory", read_timeout=60)

