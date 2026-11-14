
from src.network.compare_configs import compare_config_lines
from src.network.config_parser import identify_context
from src.network.deploy_configs import get_device_configs
from src.network.live_compare import get_device_state


SESSION_COMMANDS = {
    "enable",
    "configure terminal",
    "conf t",
    "end",
    "exit",
    "write memory",
    "write",
    "copy running-config startup-config",
}


DESTRUCTIVE_COMMAND_PREFIXES = (
    "write erase",
    "erase startup-config",
    "erase nvram:",
    "reload",
    "format ",
    "delete ",
    "configure replace",
)


def generate_missing_config(results):
    """Generate a dry-run configuration preview from comparison results."""

    # Block destructive commands before generating the plan.
    for item in results:
        command = item["command"].strip().casefold()

        if any(
            command == prefix.strip()
            or command.startswith(prefix)
            for prefix in DESTRUCTIVE_COMMAND_PREFIXES
        ):
            return None, (
                f"Destructive command detected: {command}. "
                "Deployment plan blocked."
            )

    # Block plans containing configuration conflicts.
    if any(item["status"] == "CONFLICT" for item in results):
        return None, "CONFLICT detected. Deployment plan blocked."

    plan = []
    current_context = None
    context_children = []

    def flush_context():
        nonlocal current_context, context_children

        if current_context is None:
            return

        missing_children = [
            item["command"]
            for item in context_children
            if (
                item["status"] == "MISSING"
                and item["command"].casefold() not in SESSION_COMMANDS
            )
        ]

        parent_missing = current_context["status"] == "MISSING"

        if parent_missing or missing_children:
            plan.append(current_context["command"])

            plan.extend(
                f" {command}"
                for command in missing_children
            )

            plan.append("exit")

        current_context = None
        context_children = []

    for item in results:
        command = item["command"]

        if command.casefold() in SESSION_COMMANDS:
            continue

        if identify_context(command):
            flush_context()
            current_context = item
            continue

        if current_context is not None:
            context_children.append(item)

        elif item["status"] == "MISSING":
            plan.append(command)

    flush_context()

    if not plan:
        return [], "No missing configuration found."

    return plan, "Missing configuration identified."


def print_deployment_plan(device_name, commands, message):
    """Print a deployment preview without applying configuration."""

    print(f"\n===== {device_name}: DEPLOYMENT PLAN =====")
    print(message)

    if commands is None:
        print("PLAN BLOCKED. Manual review required.")
        return

    if not commands:
        print("No commands to deploy.")
        return

    print("\n[PREVIEW ONLY - NOT DEPLOYED]")

    for command in commands:
        print(command)


def main():
    """Generate deployment previews for all eligible NetBox devices."""

    devices = get_device_configs()

    if not devices:
        raise SystemExit("No device configurations found in NetBox.")

    failed_devices = []

    for device in devices:
        print(f"\nReading {device['name']} ({device['ip']})...")

        try:
            device_state = get_device_state(device)

            results = compare_config_lines(
                device["config"],
                device_state["running_config"],
                device_state["vlan_output"],
            )

            commands, message = generate_missing_config(results)

            print_deployment_plan(
                device["name"],
                commands,
                message,
            )

        except Exception as error:
            failed_devices.append(device["name"])

            print(
                f"FAILED: {device['name']}: "
                f"{type(error).__name__}: {error}"
            )

    print("\nDEPLOYMENT PLAN GENERATION COMPLETE.")
    print("No configuration commands were sent to devices.")

    if failed_devices:
        raise SystemExit(
            f"Failed to process {len(failed_devices)} device(s): "
            f"{', '.join(failed_devices)}"
        )


if __name__ == "__main__":
    main()
