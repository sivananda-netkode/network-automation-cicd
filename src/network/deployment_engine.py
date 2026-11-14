import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from netmiko import ConnectHandler

from src.network.backup_configs import backup_device
from src.network.compare_configs import compare_config_lines
from src.network.deploy_configs import get_device_configs
from src.network.deployment_audit import (
    DeploymentRecord,
    DeviceAuditEntry,
    record_deployment,
)
from src.network.environment_config import get_environment_config
from src.network.generate_missing import generate_missing_config
from src.network.live_compare import get_device_state

load_dotenv(PROJECT_ROOT / ".env")


def get_configuration_commands(commands: List[str]) -> List[str]:
    """Remove session commands but preserve configuration context exits."""
    excluded_commands = {
        "enable",
        "configure terminal",
        "conf t",
        "end",
        "write memory",
        "write",
        "copy running-config startup-config",
    }

    return [
        command.strip()
        for command in commands
        if command.strip()
        and command.strip().casefold() not in excluded_commands
    ]


def prepare_deployment_plans(
    mode: str = "incremental",
    environment: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build deployment plans using NetBox desired state and live device state.

    Args:
        mode: 'incremental' (deploy only missing configuration) or 'full'.
        environment: Optional target environment profile ('staging' or 'production').

    Returns:
        List of plan dictionaries for each device.
    """
    if mode not in {"incremental", "full"}:
        raise ValueError("Invalid deployment mode. Supported: 'incremental', 'full'")

    devices = get_device_configs(environment=environment)

    if not devices:
        raise RuntimeError(
            f"No eligible NetBox devices found for environment: {environment or 'all'}"
        )

    plans: List[Dict[str, Any]] = []

    for device in devices:
        print(f"\nPreparing {device['name']} ({device['ip']})...")

        if os.getenv("CI_SIMULATE", "false").lower() in {"true", "1", "yes"}:
            commands = get_configuration_commands(device["config"].splitlines())
            plans.append({
                **device,
                "commands": commands,
                "message": f"CI Simulation: {len(commands)} staged configuration commands ready.",
                "status": "READY",
            })
            continue

        try:
            state = get_device_state(device, environment=environment)

            if mode == "full":
                commands = get_configuration_commands(
                    device["config"].splitlines()
                )

                if not commands:
                    raise RuntimeError(
                        f"No configuration found in NetBox for {device['name']}."
                    )

                message = "Full NetBox configuration selected."

            else:
                comparison = compare_config_lines(
                    device["config"],
                    state["running_config"],
                    state["vlan_output"],
                    state["interface_output"],
                )

                commands, message = generate_missing_config(comparison)

            plans.append({
                **device,
                "commands": commands,
                "message": message,
                "status": "BLOCKED" if commands is None else "READY",
            })

        except Exception as error:
            plans.append({
                **device,
                "commands": None,
                "message": f"{type(error).__name__}: {error}",
                "status": "FAILED",
            })

    return plans


def display_plans(plans: List[Dict[str, Any]]) -> None:
    """Display the complete deployment plan before requesting approval."""
    print("\n========== FINAL DEPLOYMENT PLAN ==========")

    for plan in plans:
        site_str = f" | Site: {plan.get('site')}" if plan.get('site') else ""
        print(f"\nDevice: {plan['name']} ({plan['ip']}){site_str}")
        print(f"Status: {plan['status']}")
        print(f"Result: {plan['message']}")

        if plan["commands"]:
            print("Commands to deploy:")
            for command in plan["commands"]:
                print(f"  {command}")

    print("\n===========================================")


def create_pre_deployment_backups(
    plans: List[Dict[str, Any]],
    environment: Optional[str] = None,
) -> bool:
    """Back up every device that requires configuration changes.

    Saves the returned backup file path in plan['backup_file'].
    """
    targets = [
        plan for plan in plans
        if plan["status"] == "READY" and plan.get("commands")
    ]

    for plan in targets:
        print(f"\nTaking pre-deployment backup for {plan['name']}...")

        if os.getenv("CI_SIMULATE", "false").lower() in {"true", "1", "yes"}:
            backup_dir = PROJECT_ROOT / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_file = str(backup_dir / f"backup_{plan['name']}_ci_simulated.cfg")
            Path(backup_file).write_text(f"! Simulated backup for {plan['name']}\nhostname {plan['name']}\n")
            plan["backup_file"] = backup_file
            print(f"[CI SIMULATION] Backup confirmed: {backup_file}")
            continue

        backup_file = backup_device(
            {"name": plan["name"], "ip": plan["ip"]},
            environment=environment,
        )

        if not backup_file:
            raise RuntimeError(
                f"Pre-deployment backup failed for {plan['name']}. "
                "Deployment stopped for safety."
            )

        plan["backup_file"] = backup_file
        print(f"Backup confirmed: {backup_file}")

    return True


def deploy_device(
    plan: Dict[str, Any],
    environment: Optional[str] = None,
) -> float:
    """Apply one device's configuration using Netmiko.

    Enforces pre-deployment device identity verification (hostname prompt check)
    and validates error patterns in command output.

    Returns:
        Execution duration in seconds.
    """
    target_env = environment or plan.get("environment")

    if target_env:
        env_cfg = get_environment_config(target_env)
        username, password = env_cfg.get_credentials()
    else:
        username = os.getenv("DEVICE_USERNAME")
        password = os.getenv("DEVICE_PASSWORD")

    if not username or not password:
        raise RuntimeError("Device SSH credentials are missing from environment.")

    commands = get_configuration_commands(plan["commands"])

    if not commands:
        return 0.0

    connection_params = {
        "device_type": "cisco_ios",
        "host": plan["ip"],
        "username": username,
        "password": password,
        "conn_timeout": 10,
        "auth_timeout": 10,
        "banner_timeout": 10,
    }

    start_time = time.time()
    print(f"\nConnecting to {plan['name']} ({plan['ip']})...")

    if os.getenv("CI_SIMULATE", "false").lower() in {"true", "1", "yes"}:
        print(f"[CI SIMULATION] Simulating Netmiko session to {plan['name']} ({plan['ip']})...")
        print(f"[CI SIMULATION] Device identity verified: prompt '{plan['name']}#' matches '{plan['name']}'.")
        print(f"[CI SIMULATION] Applying {len(commands)} configuration commands to {plan['name']}...")
        print(f"[CI SIMULATION] Configuration accepted by {plan['name']}.")
        print(f"[CI SIMULATION] Save command completed successfully on {plan['name']}.")
        return 0.15

    with ConnectHandler(**connection_params) as connection:
        # Requirement 9: Verify device identity before configuration deployment
        prompt = connection.find_prompt()
        clean_prompt = prompt.strip("#> ").lower()
        dev_name = plan["name"].lower()

        norm_prompt = clean_prompt.replace("switch", "sw")
        norm_dev = dev_name.replace("switch", "sw")

        is_match = (
            dev_name in clean_prompt
            or clean_prompt in dev_name
            or norm_dev == norm_prompt
        )

        if not is_match:
            raise RuntimeError(
                f"CRITICAL HOSTNAME MISMATCH: Connected prompt '{prompt}' does not "
                f"match expected device '{plan['name']}'! Deployment aborted for safety."
            )

        print(f"Device identity verified: prompt '{prompt}' matches '{plan['name']}'.")

        output = connection.send_config_set(
            commands,
            read_timeout=60,
        )

        error_patterns = (
            "% Invalid input",
            "% Incomplete command",
            "% Ambiguous command",
            "%Error",
        )

        if any(pattern in output for pattern in error_patterns):
            raise RuntimeError(
                f"Device returned a configuration error:\n{output}\n"
                "Review the device output and NetBox configuration."
            )

        print(f"Configuration accepted by {plan['name']}.")

        save_output = connection.send_command_timing(
            "write memory",
            read_timeout=60,
        )

        if any(pattern in save_output for pattern in error_patterns):
            raise RuntimeError(
                f"Failed to save configuration on {plan['name']}:\n{save_output}"
            )

        print(f"Save command completed successfully on {plan['name']}.")

    return time.time() - start_time


def verify_device(
    plan: Dict[str, Any],
    environment: Optional[str] = None,
) -> bool:
    """Verify intended configuration against the live device post-deployment."""
    if os.getenv("CI_SIMULATE", "false").lower() in {"true", "1", "yes"}:
        print(f"[CI SIMULATION] Post-deployment configuration verification passed for {plan['name']}.")
        return True

    state = get_device_state(plan, environment=environment)

    results = compare_config_lines(
        plan["config"],
        state["running_config"],
        state["vlan_output"],
        state["interface_output"],
    )

    problems = [
        item for item in results
        if item["status"] in {"MISSING", "CONFLICT"}
    ]

    if problems:
        raise RuntimeError(
            f"Verification found {len(problems)} missing "
            "or conflicting configuration entries."
        )

    return True


def run_deployment(
    environment: Optional[str] = None,
    mode: str = "incremental",
    auto_approve: bool = False,
) -> bool:
    """Execute complete deployment lifecycle with pre-backup, identity checks, and auditing.

    Returns:
        True if all targets succeeded, False otherwise.
    """
    env_name = (environment or "staging").lower()
    print(f"\n===== NETWORK CONFIGURATION DEPLOYMENT [{env_name.upper()}] =====")
    print(f"Mode: {mode.upper()}")

    plans = prepare_deployment_plans(mode=mode, environment=env_name)
    display_plans(plans)

    blocked = [plan for plan in plans if plan["status"] != "READY"]
    if blocked:
        print(f"\nDeployment cancelled: {len(blocked)} device(s) are blocked or failed planning.")
        return False

    targets = [plan for plan in plans if plan.get("commands")]

    if not targets:
        print("\nNo configuration changes required on any device. Everything is in sync.")
        # Record clean audit entry
        record = DeploymentRecord(
            environment=env_name,
            status="SUCCESS",
            summary="No changes required; network desired state already in sync.",
        )
        record_deployment(record)
        return True

    print(f"\nDevices requiring deployment: {len(targets)}")

    if not auto_approve:
        approval_text = "DEPLOY FULL" if mode == "full" else "DEPLOY"
        try:
            approval = input(f"\nType {approval_text} to approve deployment: ").strip()
            if approval != approval_text:
                print("\nDeployment cancelled by user. No configuration was applied.")
                return False
        except EOFError:
            print("\nNon-interactive session detected without --auto-approve. Aborting deployment.")
            return False

    # Take pre-deployment backups
    create_pre_deployment_backups(plans, environment=env_name)

    results: List[Dict[str, Any]] = []
    audit_devices: List[DeviceAuditEntry] = []
    overall_status = "SUCCESS"

    for plan in targets:
        result = {
            "name": plan["name"],
            "deployment": "FAILED",
            "verification": "NOT RUN",
        }
        duration = 0.0
        err_msg = None

        try:
            duration = deploy_device(plan, environment=env_name)
            result["deployment"] = "SUCCESS"

            verify_device(plan, environment=env_name)
            result["verification"] = "SUCCESS"

        except Exception as error:
            err_msg = str(error)
            overall_status = "FAILED"
            print(f"\nFAILED: {plan['name']}: {type(error).__name__}: {error}")

        results.append(result)

        audit_devices.append(DeviceAuditEntry(
            device_name=plan["name"],
            ip=plan["ip"],
            site=plan.get("site"),
            backup_file=plan.get("backup_file"),
            commands_count=len(plan.get("commands") or []),
            status="SUCCESS" if result["deployment"] == "SUCCESS" and result["verification"] == "SUCCESS" else "FAILED",
            error_message=err_msg,
            duration_seconds=round(duration, 2),
        ))

    # Record deployment audit log
    audit_record = DeploymentRecord(
        environment=env_name,
        status=overall_status,
        summary=f"Deployment completed: {sum(r['deployment'] == 'SUCCESS' for r in results)}/{len(results)} devices succeeded.",
        devices=audit_devices,
    )
    record_deployment(audit_record)

    print("\n========== DEPLOYMENT REPORT ==========")
    for result in results:
        print(
            f"{result['name']} | "
            f"Deployment: {result['deployment']} | "
            f"Verification: {result['verification']}"
        )

    successful = sum(
        result["deployment"] == "SUCCESS" and result["verification"] == "SUCCESS"
        for result in results
    )

    print(f"\nTotal deployment targets: {len(results)}")
    print(f"Fully successful: {successful}")
    print(f"Failed or unverified: {len(results) - successful}")

    # Observability integration
    if os.getenv("ENABLE_OBSERVABILITY_CHECK", "true").lower() in {"true", "1", "yes"}:
        try:
            from src.observability.pipeline import run_post_deployment_health_check
            run_post_deployment_health_check(results=results, targets=targets)
        except Exception as obs_err:
            print(f"\n[OBSERVABILITY WARNING] Health check integration failed: {obs_err}")

    return overall_status == "SUCCESS"


def main():
    parser = argparse.ArgumentParser(description="Network Configuration Deployment Engine")
    parser.add_argument(
        "environment",
        nargs="?",
        default=os.getenv("TARGET_ENVIRONMENT", "staging"),
        help="Target environment ('staging' or 'production')",
    )
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default=os.getenv("DEPLOY_MODE", "incremental"),
        help="Deployment mode: 'incremental' (default) or 'full'",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        default=os.getenv("DEPLOY_AUTO_APPROVE", "false").lower() in {"true", "1", "yes"},
        help="Automatically approve deployment without interactive prompt (for CI/CD pipelines)",
    )

    args = parser.parse_args()
    success = run_deployment(
        environment=args.environment,
        mode=args.mode,
        auto_approve=args.auto_approve,
    )

    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
