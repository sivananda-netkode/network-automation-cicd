
import ipaddress


def parse_dhcp_network(value):
    """Convert a CIDR or IPv4 address and subnet mask into a network."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("DHCP network is missing")

    parts = value.split()

    try:
        if len(parts) == 1:
            return ipaddress.IPv4Network(parts[0], strict=False)

        if len(parts) == 2:
            address, netmask = parts

            return ipaddress.IPv4Network(
                f"{address}/{netmask}",
                strict=False,
            )

    except ValueError as error:
        raise ValueError(str(error)) from error

    raise ValueError("Invalid DHCP network format")


def validate_dhcp_pool(pool):
    """Validate one dynamically discovered DHCP pool."""

    errors = []

    if not isinstance(pool, dict):
        return {
            "valid": False,
            "errors": ["DHCP pool must be a dictionary"],
        }

    name = pool.get("name")
    network = None

    # Validate pool name.
    if not isinstance(name, str) or not name.strip():
        errors.append("DHCP pool name is missing")

    # Validate network.
    try:
        network = parse_dhcp_network(pool.get("network"))
    except ValueError as error:
        errors.append(f"Invalid DHCP network: {error}")

    # Validate default routers.
    routers = pool.get("default_routers", [])

    if not isinstance(routers, list):
        errors.append("Default routers must be a list")
        routers = []

    if not routers:
        errors.append("At least one default router is required")

    for router in routers:
        try:
            address = ipaddress.IPv4Address(router)

            if network is not None:
                if address not in network:
                    errors.append(
                        f"Default router {router} is outside "
                        "the DHCP network"
                    )

                elif (
                    network.prefixlen <= 30
                    and address in (
                        network.network_address,
                        network.broadcast_address,
                    )
                ):
                    errors.append(
                        f"Default router {router} is not a usable host"
                    )

        except (ValueError, TypeError):
            errors.append(
                f"Invalid default-router address: {router}"
            )

    # Validate DNS servers. DNS is optional.
    dns_servers = pool.get("dns_servers", [])

    if not isinstance(dns_servers, list):
        errors.append("DNS servers must be a list")
        dns_servers = []

    for dns in dns_servers:
        try:
            ipaddress.IPv4Address(dns)
        except (ValueError, TypeError):
            errors.append(f"Invalid DNS server address: {dns}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def validate_dhcp_pools(pools):
    """Validate every dynamically discovered DHCP pool."""

    if not isinstance(pools, list):
        raise TypeError("DHCP pools must be provided as a list")

    results = []
    seen_names = set()

    for pool in pools:
        result = validate_dhcp_pool(pool)

        name = pool.get("name") if isinstance(pool, dict) else None

        if isinstance(name, str) and name.strip():
            normalized_name = name.strip().casefold()

            if normalized_name in seen_names:
                result["errors"].append(
                    "Duplicate DHCP pool name"
                )

            seen_names.add(normalized_name)

        result["valid"] = len(result["errors"]) == 0

        results.append({
            "pool": pool,
            **result,
        })

    return results
