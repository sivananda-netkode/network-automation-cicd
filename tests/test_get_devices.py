from unittest.mock import Mock, patch

from src.netbox.get_devices import get_devices


@patch("src.netbox.get_devices.requests.get")
def test_get_devices_returns_netbox_inventory(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "name": "R1",
                "role": {"name": "Router"},
                "status": {"label": "Active"},
            },
            {
                "name": "SW1",
                "role": {"name": "Switch"},
                "status": {"label": "Active"},
            },
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    devices = get_devices()

    assert len(devices) == 2
    assert devices[0]["name"] == "R1"
    assert devices[1]["name"] == "SW1"

    mock_get.assert_called_once()
