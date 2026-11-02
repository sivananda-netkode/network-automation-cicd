
import ipaddress
import uuid

import pytest

from src.network.config_parser import (
    identify_context,
    normalize_line,
    parse_config,
    parse_vlan_database,
)


def unique_name(prefix):
    """Generate a unique test identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def unique_vlan_id():
    """Generate a valid Cisco IOS VLAN ID."""
    return uuid.uuid4().int % 4093 + 1


def unique_network():
    """Generate a valid private IPv4 test network."""
    octet = uuid.uuid4().int % 250 + 1
    return ipaddress.ip_network(f"10.{octet}.0.0/24")


def test_normalize_line():
    value = unique_name("interface")

    assert normalize_line(f"  {value}   example  ") == (
        f"{value} example"
    )


@pytest.mark.parametrize(
    "prefix",
    [
        "interface",
        "vlan",
        "ip dhcp pool",
        "router",
        "ip access-list extended",
        "line vty",
        "policy-map",
        "route-map",
    ],
)
def test_identify_supported_contexts(prefix):
    """Verify supported Cisco IOS context patterns."""

    if prefix == "vlan":
        line = f"vlan {unique_vlan_id()}"
    else:
        line = f"{prefix} {unique_name('object')}"

    assert identify_context(line) == line


def test_unknown_context_is_not_recognized():
    assert identify_context(unique_name("unknown")) is None


def test_parse_multiple_contexts():
    """Verify parsing of multiple dynamically generated contexts."""

    network = unique_network()

    interface = (
        f"interface GigabitEthernet"
        f"{uuid.uuid4().int % 10}/{uuid.uuid4().int % 10}"
    )

    pool = f"ip dhcp pool {unique_name('pool')}"

    router = f"router ospf {uuid.uuid4().int % 65535 + 1}"

    hostname = unique_name("device")

    config = f"""
hostname {hostname}
!
{interface}
 description {unique_name("description")}
 ip address {network.network_address + 1} {network.netmask}
!
{pool}
 network {network.network_address} {network.netmask}
 default-router {network.network_address + 1}
!
{router}
 network {network.network_address} 0.0.0.255 area 0
!
"""

    parsed = parse_config(config)

    assert parsed["global"] == [f"hostname {hostname}"]

    assert interface in parsed["sections"]
    assert pool in parsed["sections"]
    assert router in parsed["sections"]

    assert parsed["sections"][interface][0].startswith("description ")
    assert parsed["sections"][pool][0].startswith("network ")
    assert parsed["sections"][router][0].startswith("network ")


def test_parse_preserves_unknown_child_commands():
    context = (
        f"interface GigabitEthernet"
        f"{uuid.uuid4().int % 10}/{uuid.uuid4().int % 10}"
    )

    command = unique_name("custom-command")

    config = f"""
{context}
 {command}
!
"""

    parsed = parse_config(config)

    assert parsed["sections"][context] == [command]


def test_parse_handles_different_capitalization():
    context = (
        f"INTERFACE GigabitEthernet"
        f"{uuid.uuid4().int % 10}/{uuid.uuid4().int % 10}"
    )

    description = unique_name("description")

    parsed = parse_config(
        f"{context}\n DESCRIPTION {description}\n!"
    )

    assert context in parsed["sections"]
    assert parsed["sections"][context] == [
        f"DESCRIPTION {description}"
    ]


def test_parse_rejects_non_string_input():
    with pytest.raises(TypeError):
        parse_config(None)


def test_parse_vlan_database():
    """Verify dynamic extraction of VLAN IDs and names."""

    generated_vlans = {
        unique_vlan_id(): unique_name("VLAN")
        for _ in range(10)
    }

    output = "\n".join(
        f"{vlan_id} {name} active"
        for vlan_id, name in generated_vlans.items()
    )

    parsed_vlans = parse_vlan_database(output)

    for vlan_id, name in generated_vlans.items():
        assert parsed_vlans[f"vlan {vlan_id}"] == {
            "name": name
        }


def test_parse_rejects_non_string_vlan_output():
    with pytest.raises(TypeError):
        parse_vlan_database(None)


def test_parse_empty_configuration():
    parsed = parse_config("")

    assert parsed == {
        "global": [],
        "sections": {},
    }


def test_parse_preserves_unknown_global_commands():
    command = unique_name("global-command")

    parsed = parse_config(command)

    assert parsed["global"] == [command]
