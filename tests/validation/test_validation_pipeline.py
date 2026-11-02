
from src.network.config_parser import parse_config
from src.network.config_model import build_config_model
from src.network.validate_device_configs import validate_device_models


def build_test_device(config_text):
    """Build a device model without NetBox or SSH."""

    parsed = parse_config(config_text)
    model = build_config_model(parsed)

    return {
        "device": "TEST_DEVICE",
        "ip": "127.0.0.1",
        "model": model,
    }


def test_complete_pipeline_validates_generated_configuration():
    """Test parser, model and validators together."""

    config_lines = []

    # Generate multiple VLANs.
    for vlan_id in range(10, 20):
        config_lines.extend([
            f"vlan {vlan_id}",
            f" name VLAN_{vlan_id}",
            "!",
        ])

    # Generate multiple DHCP pools.
    for index in range(1, 11):
        config_lines.extend([
            f"ip dhcp pool POOL_{index}",
            f" network 10.{index}.0.0 255.255.255.0",
            f" default-router 10.{index}.0.1",
            " dns-server 8.8.8.8",
            "!",
        ])

    config_text = "\n".join(config_lines)

    device = build_test_device(config_text)

    results = validate_device_models([device])

    assert len(results) == 20
    assert all(result["valid"] for result in results)

    assert sum(
        result["type"] == "VLAN" for result in results
    ) == 10

    assert sum(
        result["type"] == "DHCP" for result in results
    ) == 10


def test_complete_pipeline_detects_invalid_configuration():
    """Ensure invalid objects are detected by the complete pipeline."""

    config_text = """
vlan 5000
 name INVALID_VLAN
!
ip dhcp pool INVALID_POOL
 network 10.1.0.0 255.255.255.0
 default-router 10.2.0.1
 dns-server 8.8.8.8
!
"""

    device = build_test_device(config_text)

    results = validate_device_models([device])

    assert len(results) == 2
    assert all(not result["valid"] for result in results)


def test_complete_pipeline_handles_empty_configuration():
    """An empty configuration should produce no validation objects."""

    device = build_test_device("")

    results = validate_device_models([device])

    assert results == []
