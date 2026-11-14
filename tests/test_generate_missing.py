
from src.network.generate_missing import generate_missing_config


def test_blocks_plan_when_conflict_exists():
    results = [
        {"status": "CONFLICT", "command": "interface Vlan10"},
        {"status": "MISSING", "command": "no shutdown"},
    ]

    commands, message = generate_missing_config(results)

    assert commands is None
    assert "blocked" in message.lower()


def test_generates_global_commands_without_context():
    results = [
        {
            "status": "MISSING",
            "command": "ip dhcp excluded-address 192.168.10.1 192.168.10.20",
        }
    ]

    commands, message = generate_missing_config(results)

    assert commands == [
        "ip dhcp excluded-address 192.168.10.1 192.168.10.20"
    ]


def test_generates_dhcp_pool_context():
    results = [
        {"status": "MISSING", "command": "ip dhcp pool VLAN10-USERS"},
        {
            "status": "MISSING",
            "command": "network 192.168.10.0 255.255.255.0",
        },
        {
            "status": "MISSING",
            "command": "default-router 192.168.10.1",
        },
    ]

    commands, message = generate_missing_config(results)

    assert commands == [
        "ip dhcp pool VLAN10-USERS",
        " network 192.168.10.0 255.255.255.0",
        " default-router 192.168.10.1",
        "exit",
    ]


def test_generates_interface_context():
    results = [
        {"status": "MISSING", "command": "interface Vlan10"},
        {
            "status": "MISSING",
            "command": "ip address 192.168.10.1 255.255.255.0",
        },
        {"status": "MISSING", "command": "no shutdown"},
    ]

    commands, message = generate_missing_config(results)

    assert commands == [
        "interface Vlan10",
        " ip address 192.168.10.1 255.255.255.0",
        " no shutdown",
        "exit",
    ]


def test_does_not_generate_commands_when_nothing_is_missing():
    results = [
        {"status": "ALREADY EXISTS", "command": "vlan 10"},
    ]

    commands, message = generate_missing_config(results)

    assert commands == []
    assert "No missing" in message


def test_ignores_session_commands():
    results = [
        {"status": "MISSING", "command": "enable"},
        {"status": "MISSING", "command": "configure terminal"},
        {"status": "MISSING", "command": "write memory"},
        {"status": "MISSING", "command": "vlan 10"},
    ]

    commands, message = generate_missing_config(results)

    assert "enable" not in commands
    assert "configure terminal" not in commands
    assert "write memory" not in commands
    assert "vlan 10" in commands


def test_generates_vlan_context():
    results = [
        {"status": "MISSING", "command": "vlan 10"},
        {"status": "MISSING", "command": "name ECE"},
    ]

    commands, message = generate_missing_config(results)

    assert commands == [
        "vlan 10",
        " name ECE",
        "exit",
    ]


def test_preserves_existing_interface_context_for_missing_command():
    results = [
        {
            "status": "ALREADY EXISTS",
            "command": "interface Vlan10",
        },
        {
            "status": "ALREADY EXISTS",
            "command": "ip address 192.168.10.1 255.255.255.0",
        },
        {
            "status": "MISSING",
            "command": "no shutdown",
        },
    ]

    commands, message = generate_missing_config(results)

    assert commands == [
        "interface Vlan10",
        " no shutdown",
        "exit",
    ]


def test_blocks_destructive_configuration_commands():
    results = [
        {
            "status": "MISSING",
            "command": "write erase",
        }
    ]

    commands, message = generate_missing_config(results)

    assert commands is None
    assert "blocked" in message.lower()