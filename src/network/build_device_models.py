
from src.network.deploy_configs import get_device_configs
from src.network.config_parser import parse_config
from src.network.config_model import build_config_model


def build_all_device_models():
    """Build configuration models from NetBox device data."""

    devices = get_device_configs()

    if not devices:
        raise RuntimeError(
            "No device configurations found in NetBox."
        )

    device_models = []

    for device in devices:
        print(f"\nProcessing device: {device['name']}")

        parsed_config = parse_config(device["config"])

        model = build_config_model(parsed_config)

        device_models.append({
            "device": device["name"],
            "ip": device["ip"],
            "model": model,
        })

    return device_models


def print_device_models(device_models):
    """Display the dynamically discovered configuration."""

    for item in device_models:
        model = item["model"]

        print("\n" + "=" * 50)
        print(f"DEVICE: {item['device']}")
        print(f"IP: {item['ip']}")
        print("=" * 50)

        print(f"\nVLANs discovered: {len(model['vlans'])}")

        for vlan in model["vlans"]:
            print(
                f"VLAN ID: {vlan['id']}, "
                f"Name: {vlan['name']}"
            )

        print(
            f"\nDHCP pools discovered: "
            f"{len(model['dhcp_pools'])}"
        )

        for pool in model["dhcp_pools"]:
            print(f"Pool: {pool['name']}")
            print(f"Network: {pool['network']}")
            print(
                f"Default routers: "
                f"{pool['default_routers']}"
            )
            print(f"DNS servers: {pool['dns_servers']}")

        print(
            "\nDHCP excluded-address commands: "
            f"{len(model['dhcp_excluded_addresses'])}"
        )

        print(
            "Other configuration sections: "
            f"{len(model['other_sections'])}"
        )

        if model["parse_errors"]:
            print("\nParsing errors:")

            for error in model["parse_errors"]:
                print(f"- {error}")


def main():
    device_models = build_all_device_models()
    print_device_models(device_models)

    print("\nNETBOX CONFIGURATION MODEL GENERATION COMPLETE.")
    print("Read-only operation. No device configuration changed.")


if __name__ == "__main__":
    main()
