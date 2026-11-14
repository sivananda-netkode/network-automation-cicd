from unittest.mock import MagicMock, patch

from src.network.operational_validation import (
    get_connection,
    run_validation,
    validate_device,
)


def test_get_connection_credentials_resolution():
    device = {"name": "R1", "ip": "192.168.1.1"}
    with patch.dict("os.environ", {"DEVICE_USERNAME": "netkode_stage", "DEVICE_PASSWORD": "stage_password"}):
        conn = get_connection(device, environment="staging")
        assert conn["username"] == "netkode_stage"
        assert conn["password"] == "stage_password"
        assert conn["host"] == "192.168.1.1"


@patch.dict("os.environ", {"DEVICE_USERNAME": "test_user", "DEVICE_PASSWORD": "test_password"})
@patch("src.network.operational_validation.ConnectHandler")
def test_validate_device_executes_operational_commands(mock_connect):
    mock_conn = MagicMock()
    mock_conn.find_prompt.return_value = "R1#"
    mock_conn.send_command.side_effect = lambda cmd, **kwargs: f"Output for {cmd}"
    mock_connect.return_value.__enter__.return_value = mock_conn

    device = {"name": "R1", "ip": "192.168.1.1", "site": "Hyderabad Netkode"}
    res = validate_device(device, environment="staging")

    assert res["device"] == "R1"
    assert "INTERFACES" in res["checks"]
    assert "OSPF NEIGHBORS" in res["checks"]
    assert "ROUTING TABLE" in res["checks"]
    assert "VLAN DATABASE" in res["checks"]


@patch("src.network.operational_validation.validate_device")
@patch("src.network.operational_validation.get_device_configs")
def test_run_validation_summary(mock_get_configs, mock_val_dev):
    mock_get_configs.return_value = [
        {"name": "R1", "ip": "192.168.1.1", "config": "hostname R1"},
        {"name": "SW1", "ip": "192.168.4.2", "config": "hostname SW1"},
    ]
    mock_val_dev.return_value = {"device": "R1", "checks": {"INTERFACES": "up"}}

    success = run_validation(environment="staging")
    assert success is True
    assert mock_val_dev.call_count == 2

