from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "configs" / "intended" / "R1_interface.cfg"


def test_interface_configuration_contains_expected_commands():
    config = CONFIG_FILE.read_text(encoding="utf-8")

    assert "interface GigabitEthernet0/1" in config
    assert "description UPLINK-TO-SWITCH" in config


def test_interface_configuration_is_not_empty():
    config = CONFIG_FILE.read_text(encoding="utf-8").strip()

    assert config, "The intended configuration must not be empty."
