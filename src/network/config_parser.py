
import re
import textwrap


# Cisco IOS configuration section patterns.
# These describe command structures, not device-specific values.
CONTEXT_PATTERNS = [
    r"^interface\s+\S+.*$",
    r"^vlan\s+\d+$",
    r"^ip\s+dhcp\s+pool\s+\S+$",
    r"^router\s+\S+.*$",
    r"^ip\s+access-list\s+\S+.*$",
    r"^line\s+\S+.*$",
    r"^policy-map\s+\S+.*$",
    r"^class-map\s+.*$",
    r"^route-map\s+\S+.*$",
    r"^crypto\s+\S+.*$",
    r"^key\s+chain\s+\S+.*$",
    r"^track\s+\S+.*$",
    r"^template\s+\S+.*$",
    r"^vrf\s+definition\s+\S+.*$",
    r"^control-plane$",
    r"^monitor\s+session\s+\S+.*$",
]


IGNORED_COMMANDS = {
    "enable",
    "configure terminal",
    "conf t",
    "end",
    "exit",
    "write memory",
    "write",
    "do",
}


def normalize_line(line):
    """Normalize whitespace without changing command values."""
    return " ".join(line.strip().split())


def identify_context(line):
    """Identify supported Cisco IOS configuration sections."""

    normalized = normalize_line(line)

    for pattern in CONTEXT_PATTERNS:
        if re.fullmatch(pattern, normalized, re.IGNORECASE):
            return normalized

    return None


def parse_config(config_text):
    """
    Parse Cisco IOS configuration into global commands and sections.

    Recognized top-level sections retain their child commands.
    Unknown top-level commands are preserved as global commands.
    """

    if not isinstance(config_text, str):
        raise TypeError("Configuration must be a string.")

    config_text = textwrap.dedent(config_text)

    parsed = {
        "global": [],
        "sections": {},
    }

    current_context = None

    for raw_line in config_text.splitlines():

        if not raw_line.strip():
            continue

        if raw_line.lstrip().startswith("!"):
            current_context = None
            continue

        indentation = len(raw_line) - len(raw_line.lstrip())
        line = normalize_line(raw_line)

        if not line:
            continue

        if line.casefold() in IGNORED_COMMANDS:
            current_context = None
            continue

        # Identify top-level configuration sections.
        if indentation == 0:

            context = identify_context(line)

            if context:
                current_context = context
                parsed["sections"].setdefault(
                    current_context, []
                )
                continue

            # Global commands, including numbered ACL commands.
            current_context = None
            parsed["global"].append(line)
            continue

        # Preserve child commands under their parent section.
        if current_context is not None:
            parsed["sections"][current_context].append(line)
        else:
            parsed["global"].append(line)

    return parsed


def parse_vlan_database(vlan_output):
    """Parse VLAN information from Cisco show vlan brief output."""

    if not isinstance(vlan_output, str):
        raise TypeError("VLAN output must be a string.")

    vlans = {}

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

        vlans[f"vlan {vlan_id}"] = {
            "name": vlan_name,
        }

    return vlans


def print_parsed_config(parsed):
    """Display parsed configuration."""

    print("\n===== GLOBAL CONFIGURATION =====")

    for command in parsed["global"]:
        print(command)

    print("\n===== CONFIGURATION SECTIONS =====")

    for section, commands in parsed["sections"].items():

        print(f"\n[{section}]")

        for command in commands:
            print(f"  {command}")
