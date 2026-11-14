import json
from unittest.mock import patch
import pytest

from src.observability.discovery import (
    build_prometheus_target_entry,
    generate_prometheus_targets,
)


def test_build_prometheus_target_entry_success():
    device = {
        "name": "R1",
        "ip": "192.168.1.1",
        "role": "Router",
        "status": "Active",
    }
    entry = build_prometheus_target_entry(device)
    assert entry["targets"] == ["192.168.1.1"]
    assert entry["labels"]["device"] == "R1"
    assert entry["labels"]["role"] == "Router"
    assert entry["labels"]["status"] == "Active"
    assert entry["labels"]["ip"] == "192.168.1.1"


def test_build_prometheus_target_entry_missing_ip():
    device = {"name": "R1", "role": "Router"}
    with pytest.raises(ValueError, match="missing an IP address"):
        build_prometheus_target_entry(device)


def test_generate_prometheus_targets_with_explicit_devices(tmp_path):
    out_file = tmp_path / "targets.json"
    devices = [
        {"name": "R1", "ip": "192.168.1.1", "role": "Router", "status": "Active"},
        {"name": "SW1", "ip": "192.168.4.2", "role": "Switch", "status": "Active"},
    ]

    targets = generate_prometheus_targets(devices=devices, output_path=out_file)
    assert len(targets) == 2
    assert out_file.exists()

    with open(out_file, encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 2
    assert data[0]["labels"]["device"] == "R1"
    assert data[1]["labels"]["device"] == "SW1"


def test_generate_prometheus_targets_queries_netbox_dynamically(tmp_path):
    out_file = tmp_path / "targets.json"
    mock_netbox_devices = [
        {"name": "R1", "ip": "10.0.0.1", "role": "Core", "status": "Active"}
    ]

    with patch("src.observability.discovery.get_devices", return_value=mock_netbox_devices):
        targets = generate_prometheus_targets(devices=None, output_path=out_file)
        assert len(targets) == 1
        assert targets[0]["targets"] == ["10.0.0.1"]
        assert targets[0]["labels"]["device"] == "R1"

