
def build_config_model(parsed_config):
    """
    Convert parsed Cisco configuration into structured data.

    Does not depend on specific device names, VLAN IDs,
    IP addresses or DHCP pool names.
    """

    model = {
        "vlans": [],
        "dhcp_pools": [],
        "dhcp_excluded_addresses": [],
        "other_global_commands": [],
        "other_sections": {},
        "parse_errors": [],
    }

    # Dynamically process all configuration sections.
    for section, commands in parsed_config.get(
        "sections", {}
    ).items():

        section_lower = section.lower()

        # VLAN processing
        if section_lower.startswith("vlan "):

            vlan_id_text = section.split(maxsplit=1)[1]

            try:
                vlan = {
                    "id": int(vlan_id_text),
                    "name": None,
                }
            except ValueError:
                model["parse_errors"].append(
                    f"Invalid VLAN section: {section}"
                )
                continue

            for command in commands:
                parts = command.split(maxsplit=1)

                if parts and parts[0].lower() == "name":
                    vlan["name"] = (
                        parts[1] if len(parts) > 1 else None
                    )

            model["vlans"].append(vlan)

        # DHCP pool processing
        elif section_lower.startswith("ip dhcp pool "):

            pool_name = section[len("ip dhcp pool "):].strip()

            pool = {
                "name": pool_name,
                "network": None,
                "default_routers": [],
                "dns_servers": [],
                "other_commands": [],
            }

            for command in commands:
                parts = command.split(maxsplit=1)

                if not parts:
                    continue

                keyword = parts[0].lower()
                value = parts[1].strip() if len(parts) > 1 else ""

                if keyword == "network":
                    if pool["network"] is not None:
                        model["parse_errors"].append(
                            f"Multiple network statements found in DHCP pool: "
                            f"{pool_name}"
                        )
                    else:
                        pool["network"] = value

                elif keyword == "default-router":
                    pool["default_routers"].extend(value.split())

                elif keyword == "dns-server":
                    pool["dns_servers"].extend(value.split())

                else:
                    pool["other_commands"].append(command)

            model["dhcp_pools"].append(pool)

        else:
            # Preserve sections not yet modeled.
            model["other_sections"][section] = commands

    # Process global commands.
    for command in parsed_config.get("global", []):

        if command.lower().startswith(
            "ip dhcp excluded-address "
        ):
            model["dhcp_excluded_addresses"].append(command)

        else:
            model["other_global_commands"].append(command)

    return model
