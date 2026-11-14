
import re
from collections import Counter

from src.network.config_parser import parse_config


GLOBAL_SECTION = "__global__"

# These are Cisco IOS command keywords, not device-specific values.
MULTI_VALUE_PREFIXES = (
    "ip helper-address ",
    "ip access-group ",
    "default-router ",
    "dns-server ",
    "service-policy ",
    "neighbor ",
)

SINGLE_VALUE_PREFIXES = (
    "ip address ",
    "name ",
    "description ",
    "encapsulation ",
    "switchport mode ",
    "switchport access vlan ",
    "switchport trunk native vlan ",
    "vrf forwarding ",
    "router-id ",
    "network ",
)


def normalize_config_line(line):
    """Normalize whitespace and command casing for comparison."""
    return " ".join(line.strip().split()).casefold()


def normalize_section_name(line):
    """Normalize section names while preserving their values."""

    line = " ".join(line.strip().split())

    # Normalize Cisco VLAN interfaces:
    # interface vlan 10 == interface Vlan10
    match = re.match(
        r"^interface\s+vlan\s*(\d+)$",
        line,
        re.IGNORECASE,
    )

    if match:
        return f"interface vlan{match.group(1)}"

    match = re.match(
        r"^interface\s+(.+)$",
        line,
        re.IGNORECASE,
    )

    if match:
        return f"interface {match.group(1).casefold()}"

    match = re.match(
        r"^vlan\s+(\d+)$",
        line,
        re.IGNORECASE,
    )

    if match:
        return f"vlan {match.group(1)}"

    match = re.match(
        r"^ip dhcp pool\s+(.+)$",
        line,
        re.IGNORECASE,
    )

    if match:
        return f"ip dhcp pool {match.group(1).casefold()}"

    return normalize_config_line(line)

def extract_sections(config):
    """Parse configuration into normalized global and section commands."""
    parsed = parse_config(config)

    sections = {
        GLOBAL_SECTION: [
            normalize_config_line(command)
            for command in parsed["global"]
        ]
    }

    for section, commands in parsed["sections"].items():
        normalized_section = normalize_section_name(section)

        existing = sections.setdefault(normalized_section, [])

        existing.extend(
            normalize_config_line(command)
            for command in commands
        )

    return sections

def extract_vlan_database(vlan_output):
    """Extract VLAN IDs and names from show vlan brief output."""
    vlan_sections = {}

    if not isinstance(vlan_output, str):
        return vlan_sections

    for line in vlan_output.splitlines():
        match = re.match(
            r"^\s*(\d+)\s+(\S+)\s+"
            r"(?:active|act/unsup|suspend)\b",
            line,
            re.IGNORECASE,
        )

        if not match:
            continue

        vlan_id, vlan_name = match.groups()

        vlan_sections[f"vlan {vlan_id}"] = [
            f"name {vlan_name}".casefold()
        ]

    return vlan_sections


def _command_prefix(command):
    """Identify the command family used for generic comparison."""
    for prefix in SINGLE_VALUE_PREFIXES + MULTI_VALUE_PREFIXES:
        if command.startswith(prefix):
            return prefix.strip()

    return None


def _section_has_conflict(intended_commands, running_commands):
    """
    Detect incompatible single-value settings.

    Multi-value commands are additive:
    missing values are handled separately as MISSING.
    """

    intended_groups = {}
    running_groups = {}

    for command in intended_commands:
        prefix = _command_prefix(command)

        if prefix in {
            item.strip() for item in SINGLE_VALUE_PREFIXES
        }:
            intended_groups.setdefault(prefix, []).append(command)

    for command in running_commands:
        prefix = _command_prefix(command)

        if prefix in {
            item.strip() for item in SINGLE_VALUE_PREFIXES
        }:
            running_groups.setdefault(prefix, []).append(command)

    for prefix, intended_values in intended_groups.items():

        running_values = running_groups.get(prefix, [])

        if running_values and set(intended_values) != set(running_values):
            return True

    return False


def _compare_global_commands(intended_commands, running_commands):
    """Compare global commands independently."""
    running_set = set(running_commands)

    return [
        {
            "status": (
                "ALREADY EXISTS"
                if command in running_set
                else "MISSING"
            ),
            "command": command,
        }
        for command in intended_commands
    ]


def compare_config_lines(
    intended_config,
    running_config,
    vlan_output="",
    interface_output="",
):
    """Compare intended configuration against read-only live state."""
    intended_sections = extract_sections(intended_config)
    running_sections = extract_sections(running_config)

    if vlan_output:
        vlan_sections = extract_vlan_database(vlan_output)

        for section, commands in vlan_sections.items():
            existing = running_sections.setdefault(section, [])

            for command in commands:
                if command not in existing:
                    existing.append(command)

    results = []

    for section, intended_commands in intended_sections.items():

        if section == GLOBAL_SECTION:
            results.extend(
                _compare_global_commands(
                    intended_commands,
                    running_sections.get(section, []),
                )
            )
            continue

        running_commands = running_sections.get(section)

        if running_commands is None:
            results.append({
                "status": "MISSING",
                "command": section,
            })

            for command in intended_commands:
                results.append({
                    "status": "MISSING",
                    "command": command,
                })

            continue

        section_conflict = _section_has_conflict(
            intended_commands,
            running_commands,
        )

        results.append({
            "status": (
                "CONFLICT"
                if section_conflict
                else "ALREADY EXISTS"
            ),
            "command": section,
        })

        running_counts = Counter(running_commands)

        for command in intended_commands:
            if section_conflict:
                status = "CONFLICT"
            elif running_counts[command] > 0:
                status = "ALREADY EXISTS"
                running_counts[command] -= 1
            elif (
                normalize_config_line(command) == "no shutdown"
                and interface_is_enabled(section, interface_output)
            ):
                status = "ALREADY EXISTS"
            else:
                status = "MISSING"

            results.append({
                "status": status,
                "command": command,
            })

    return results
def interface_is_enabled(section, interface_output):
    """Check whether an interface is not administratively shut down."""

    if not interface_output or not section.startswith("interface "):
        return False

    intended_name = section.split(" ", 1)[1].replace(" ", "").casefold()

    for line in interface_output.splitlines():
        fields = line.split()

        if len(fields) < 6:
            continue

        live_name = fields[0].replace(" ", "").casefold()

        if live_name != intended_name:
            continue

        status = " ".join(fields[4:-1]).casefold()

        return status in {"up", "down"}

    return False


def print_comparison(device_name, results):
    """Display comparison summary without exposing configuration values."""

    print(f"\n===== {device_name}: CONFIGURATION COMPARISON =====")

    status_counts = {}

    for item in results:
        status = item["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    for status, count in sorted(status_counts.items()):
        print(f"{status}: {count}")

    print(f"Total comparison entries: {len(results)}")
    print("Configuration command values hidden for security.")


if __name__ == "__main__":
    print("Comparison module loaded.")
    print("Read-only mode: no device configuration will be changed.")
