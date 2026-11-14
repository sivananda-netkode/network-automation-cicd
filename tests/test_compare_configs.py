
import ipaddress
import uuid

from src.network.compare_configs import compare_config_lines


def unique_name(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def unique_vlan_id():
    return uuid.uuid4().int % 4093 + 1


def unique_network():
    octet = uuid.uuid4().int % 250 + 1
    return ipaddress.ip_network(f"10.{octet}.0.0/24")


def unique_dns():
    value = uuid.uuid4().int % 250 + 1
    return f"203.0.113.{value}"


def interface_context():
    return f"interface Vlan{unique_vlan_id()}"


def dhcp_context():
    return f"ip dhcp pool {unique_name('POOL')}"


def get_statuses(results):
    """Build a case-insensitive command-to-status lookup."""
    return {
        item["command"].casefold(): item["status"]
        for item in results
    }


def test_existing_and_missing_commands():
    existing_vlan = unique_vlan_id()
    missing_vlan = unique_vlan_id()

    intended = f"""
vlan {existing_vlan}
vlan {missing_vlan}
"""

    running = f"""
vlan {existing_vlan}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[f"vlan {existing_vlan}".casefold()] == "ALREADY EXISTS"
    assert statuses[f"vlan {missing_vlan}".casefold()] == "MISSING"


def test_ignores_blank_lines_and_comments():
    vlan_id = unique_vlan_id()

    intended = f"""
!
vlan {vlan_id}

"""

    running = f"""
!
vlan {vlan_id}
"""

    results = compare_config_lines(intended, running)

    assert len(results) == 1
    assert results[0]["status"] == "ALREADY EXISTS"
    assert results[0]["command"] == f"vlan {vlan_id}"


def test_empty_intended_config_returns_no_changes():
    vlan_id = unique_vlan_id()

    results = compare_config_lines("", f"vlan {vlan_id}")

    assert results == []


def test_detects_conflicting_interface_ip():
    network = unique_network()
    interface = interface_context()

    intended_ip = network.network_address + 1
    running_ip = network.network_address + 2

    intended = f"""
{interface}
 ip address {intended_ip} {network.netmask}
"""

    running = f"""
{interface}
 ip address {running_ip} {network.netmask}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    intended_command = f"ip address {intended_ip} {network.netmask}"

    assert statuses[interface.casefold()] == "CONFLICT"
    assert statuses[intended_command.casefold()] == "CONFLICT"


def test_detects_existing_vlan_and_vlan_name():
    vlan_id = unique_vlan_id()
    vlan_name = unique_name("VLAN")

    intended = f"""
vlan {vlan_id}
 name {vlan_name}
"""

    running = f"""
vlan {vlan_id}
 name {vlan_name}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[f"vlan {vlan_id}".casefold()] == "ALREADY EXISTS"
    assert statuses[f"name {vlan_name}".casefold()] == "ALREADY EXISTS"


def test_detects_vlan_name_conflict():
    vlan_id = unique_vlan_id()
    intended_name = unique_name("VLAN")
    running_name = unique_name("VLAN")

    intended = f"""
vlan {vlan_id}
 name {intended_name}
"""

    running = f"""
vlan {vlan_id}
 name {running_name}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[f"vlan {vlan_id}".casefold()] == "CONFLICT"
    assert statuses[f"name {intended_name}".casefold()] == "CONFLICT"


def test_detects_existing_dhcp_pool():
    network = unique_network()
    pool = dhcp_context()
    router = network.network_address + 1
    dns = unique_dns()

    config = f"""
{pool}
 network {network.network_address} {network.netmask}
 default-router {router}
 dns-server {dns}
"""

    results = compare_config_lines(config, config)
    statuses = get_statuses(results)

    assert statuses[pool.casefold()] == "ALREADY EXISTS"
    assert statuses[
        f"network {network.network_address} {network.netmask}".casefold()
    ] == "ALREADY EXISTS"


def test_detects_dhcp_pool_network_conflict():
    intended_network = unique_network()
    running_network = unique_network()
    pool = dhcp_context()

    intended_router = intended_network.network_address + 1

    intended = f"""
{pool}
 network {intended_network.network_address} {intended_network.netmask}
 default-router {intended_router}
"""

    running = f"""
{pool}
 network {running_network.network_address} {running_network.netmask}
 default-router {intended_router}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[pool.casefold()] == "CONFLICT"
    assert statuses[
        f"network {intended_network.network_address} {intended_network.netmask}".casefold()
    ] == "CONFLICT"


def test_detects_missing_interface_no_shutdown():
    network = unique_network()
    interface = interface_context()
    address = network.network_address + 1

    intended = f"""
{interface}
 ip address {address} {network.netmask}
 no shutdown
"""

    running = f"""
{interface}
 ip address {address} {network.netmask}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[interface.casefold()] == "ALREADY EXISTS"
    assert statuses["no shutdown"] == "MISSING"


def test_detects_dhcp_dns_conflict():
    network = unique_network()
    pool = dhcp_context()

    router = network.network_address + 1
    intended_dns = unique_dns()
    running_dns = unique_dns()

    intended = f"""
{pool}
 network {network.network_address} {network.netmask}
 default-router {router}
 dns-server {intended_dns}
"""

    running = f"""
{pool}
 network {network.network_address} {network.netmask}
 default-router {router}
 dns-server {running_dns}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[pool.casefold()] == "ALREADY EXISTS"

    intended_dns_command = f"dns-server {intended_dns}"
    assert statuses[intended_dns_command] == "MISSING"


def test_detects_existing_global_command():
    network = unique_network()

    start = network.network_address + 10
    end = network.network_address + 20

    command = f"ip dhcp excluded-address {start} {end}"

    results = compare_config_lines(command, command)

    assert results == [{
        "status": "ALREADY EXISTS",
        "command": command,
    }]


def test_detects_missing_global_command():
    network = unique_network()

    start = network.network_address + 10
    end = network.network_address + 20

    command = f"ip dhcp excluded-address {start} {end}"

    results = compare_config_lines(command, "")

    assert results == [{
        "status": "MISSING",
        "command": command,
    }]


def test_compares_multiple_global_commands_independently():
    network = unique_network()

    first_command = (
        f"ip dhcp excluded-address "
        f"{network.network_address + 10} "
        f"{network.network_address + 20}"
    )

    second_command = (
        f"ip dhcp excluded-address "
        f"{network.network_address + 30} "
        f"{network.network_address + 40}"
    )

    intended = f"""
{first_command}
{second_command}
"""

    running = first_command

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[first_command.casefold()] == "ALREADY EXISTS"
    assert statuses[second_command.casefold()] == "MISSING"


def test_ignores_enable_session_command():
    vlan_id = unique_vlan_id()

    intended = f"""
enable
vlan {vlan_id}
"""

    running = f"""
vlan {vlan_id}
"""

    results = compare_config_lines(intended, running)

    assert all(
        item["command"] != "enable"
        for item in results
    )

    assert results == [{
        "status": "ALREADY EXISTS",
        "command": f"vlan {vlan_id}",
    }]


def test_interface_commands_are_order_independent():
    network = unique_network()
    interface = interface_context()
    address = network.network_address + 1

    intended = f"""
{interface}
 ip address {address} {network.netmask}
 no shutdown
"""

    running = f"""
{interface}
 no shutdown
 ip address {address} {network.netmask}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[interface.casefold()] == "ALREADY EXISTS"
    assert statuses[
        f"ip address {address} {network.netmask}".casefold()
    ] == "ALREADY EXISTS"
    assert statuses["no shutdown"] == "ALREADY EXISTS"


def test_dhcp_commands_are_order_independent():
    network = unique_network()
    pool = dhcp_context()
    router = network.network_address + 1
    dns = unique_dns()

    intended = f"""
{pool}
 network {network.network_address} {network.netmask}
 default-router {router}
 dns-server {dns}
"""

    running = f"""
{pool}
 dns-server {dns}
 default-router {router}
 network {network.network_address} {network.netmask}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert statuses[pool.casefold()] == "ALREADY EXISTS"
    assert statuses[
        f"network {network.network_address} {network.netmask}".casefold()
    ] == "ALREADY EXISTS"
    assert statuses[f"default-router {router}".casefold()] == "ALREADY EXISTS"
    assert statuses[f"dns-server {dns}".casefold()] == "ALREADY EXISTS"



def test_detects_conflicting_values_in_unknown_section():
    process_id = unique_vlan_id()
    network = unique_network()

    intended_router_id = network.network_address + 1
    running_router_id = network.network_address + 2

    intended = f"""
router ospf {process_id}
 router-id {intended_router_id}
"""

    running = f"""
router ospf {process_id}
 router-id {running_router_id}
"""

    results = compare_config_lines(intended, running)
    statuses = get_statuses(results)

    assert intended_router_id != running_router_id

    assert statuses[
        f"router ospf {process_id}".casefold()
    ] == "CONFLICT"


def test_no_shutdown_already_exists_when_interface_is_operationally_down():
    intended = """
interface Vlan10
 ip address 192.168.10.1 255.255.255.0
 no shutdown
"""

    running = """
interface Vlan10
 ip address 192.168.10.1 255.255.255.0
"""

    interface_output = """
Interface              IP-Address      OK? Method Status                Protocol
Vlan10                 192.168.10.1    YES manual down                  down
"""

    results = compare_config_lines(
        intended,
        running,
        interface_output=interface_output,
    )

    statuses = get_statuses(results)

    assert statuses["no shutdown"] == "ALREADY EXISTS"
