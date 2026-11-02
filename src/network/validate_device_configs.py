
from src.network.build_device_models import build_all_device_models
from src.network.validators.vlan import validate_vlans
from src.network.validators.dhcp import validate_dhcp_pools


def validate_device_models(device_models):
    """Validate all discovered VLANs and DHCP pools."""

    all_results = []

    for item in device_models:
        device_name = item["device"]
        model = item["model"]

        for error in model["parse_errors"]:
            all_results.append({
                "device": device_name,
                "type": "PARSE",
                "object": "Configuration parsing",
                "valid": False,
                "errors": [error],
            })

        # Validate all VLANs discovered on this device.
        for result in validate_vlans(model["vlans"]):
            all_results.append({
                "device": device_name,
                "type": "VLAN",
                "object": result["vlan"],
                "valid": result["valid"],
                "errors": result["errors"],
            })

        # Validate all DHCP pools discovered on this device.
        for result in validate_dhcp_pools(model["dhcp_pools"]):
            all_results.append({
                "device": device_name,
                "type": "DHCP",
                "object": result["pool"],
                "valid": result["valid"],
                "errors": result["errors"],
            })

    return all_results


def print_validation_results(results):
    """Display validation results."""

    print("\n===== DYNAMIC CONFIGURATION VALIDATION =====")

    for result in results:
        status = "VALID" if result["valid"] else "INVALID"

        print(
            f"[{status}] Device: {result['device']} | "
            f"Type: {result['type']} | "
            f"Object: {result['object']}"
        )

        for error in result["errors"]:
            print(f"  ERROR: {error}")


def main():
    device_models = build_all_device_models()
    results = validate_device_models(device_models)

    print_validation_results(results)

    vlan_results = [
        result for result in results
        if result["type"] == "VLAN"
    ]

    dhcp_results = [
        result for result in results
        if result["type"] == "DHCP"
    ]

    total = len(results)
    valid = sum(result["valid"] for result in results)
    invalid = total - valid

    print("\n===== VALIDATION SUMMARY =====")
    print(f"Total VLANs: {len(vlan_results)}")
    print(f"Valid VLANs: {sum(r['valid'] for r in vlan_results)}")
    print(f"Total DHCP pools: {len(dhcp_results)}")
    print(f"Valid DHCP pools: {sum(r['valid'] for r in dhcp_results)}")
    print(f"Total objects: {total}")
    print(f"Valid objects: {valid}")
    print(f"Invalid objects: {invalid}")

    if invalid:
        raise SystemExit("Configuration validation failed.")

    print("\nAll discovered configuration objects passed validation.")


if __name__ == "__main__":
    main()
