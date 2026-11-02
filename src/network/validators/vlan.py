
def validate_vlan(vlan):
    """Validate one dynamically discovered VLAN."""

    if not isinstance(vlan, dict):
        return {
            "valid": False,
            "errors": ["VLAN must be a dictionary"],
        }

    errors = []

    vlan_id = vlan.get("id")
    vlan_name = vlan.get("name")

    # Validate VLAN ID.
    if not isinstance(vlan_id, int) or isinstance(vlan_id, bool):
        errors.append("VLAN ID must be an integer")

    elif not 1 <= vlan_id <= 4094:
        errors.append("VLAN ID must be between 1 and 4094")

    # Validate VLAN name.
    if not isinstance(vlan_name, str) or not vlan_name.strip():
        errors.append("VLAN name is missing or invalid")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def validate_vlans(vlans):
    """Validate all discovered VLANs and detect duplicate IDs."""

    if not isinstance(vlans, list):
        raise TypeError("VLANs must be provided as a list")

    results = []
    seen_ids = set()

    for vlan in vlans:

        result = validate_vlan(vlan)

        vlan_id = vlan.get("id") if isinstance(vlan, dict) else None

        if isinstance(vlan_id, int) and not isinstance(vlan_id, bool):

            if vlan_id in seen_ids:
                result["errors"].append("Duplicate VLAN ID")

            seen_ids.add(vlan_id)

        result["valid"] = len(result["errors"]) == 0

        results.append({
            "vlan": vlan,
            **result,
        })

    return results
