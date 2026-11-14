"""Deployment Audit Logger.

Provides structured, append-only JSONL logging for network configuration deployments.
Tracks commit hash, approver/actor, environment, device targets, pre-deployment
backup references, and execution status for full governance and traceability.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_AUDIT_LOG = PROJECT_ROOT / "deployments" / "audit_log.jsonl"


def get_git_commit_sha() -> str:
    """Retrieve current Git commit SHA from environment or git command."""
    sha = os.getenv("GITHUB_SHA")
    if sha:
        return sha[:10]

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    return "unknown"


def get_deployment_actor() -> str:
    """Retrieve actor who approved or initiated the deployment."""
    actor = os.getenv("GITHUB_ACTOR")
    if actor:
        return actor
    try:
        return getpass.getuser()
    except Exception:
        return "system"


@dataclass
class DeviceAuditEntry:
    """Audit entry for an individual device within a deployment run."""
    device_name: str
    ip: str
    site: Optional[str]
    backup_file: Optional[str]
    commands_count: int
    status: str  # "SUCCESS", "FAILED", "SKIPPED", "NO_CHANGES"
    error_message: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class DeploymentRecord:
    """Immutable audit record for a complete deployment run."""
    environment: str  # "staging" or "production"
    deployment_id: str = field(
        default_factory=lambda: f"dep-{uuid.uuid4().hex[:8]}"
    )
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    commit_sha: str = field(default_factory=get_git_commit_sha)
    actor: str = field(default_factory=get_deployment_actor)
    status: str = "PENDING"  # "SUCCESS", "FAILED", "PARTIAL_FAILURE", "ABORTED", "ROLLED_BACK"
    devices: List[DeviceAuditEntry] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to a JSON-serializable dictionary."""
        return {
            "deployment_id": self.deployment_id,
            "timestamp": self.timestamp,
            "environment": self.environment,
            "commit_sha": self.commit_sha,
            "actor": self.actor,
            "status": self.status,
            "summary": self.summary,
            "devices": [asdict(dev) for dev in self.devices],
        }


def record_deployment(
    record: DeploymentRecord,
    log_path: Optional[Path] = None,
) -> Path:
    """Append a deployment record to the audit log JSONL file.

    Args:
        record: The completed DeploymentRecord.
        log_path: Optional custom path to audit log. Defaults to DEFAULT_AUDIT_LOG.

    Returns:
        The Path to the audit log file where the record was written.
    """
    target_path = log_path or DEFAULT_AUDIT_LOG
    target_path.parent.mkdir(parents=True, exist_ok=True)

    data = record.to_dict()
    line = json.dumps(data) + "\n"

    with open(target_path, "a", encoding="utf-8") as f:
        f.write(line)

    return target_path


def read_audit_history(
    limit: int = 10,
    environment: Optional[str] = None,
    log_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Read recent deployment records from the audit log.

    Args:
        limit: Maximum number of recent entries to return.
        environment: Optional filter by environment ('staging' or 'production').
        log_path: Optional custom path to audit log.

    Returns:
        List of deployment records in reverse chronological order (newest first).
    """
    target_path = log_path or DEFAULT_AUDIT_LOG
    if not target_path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    with open(target_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if environment:
                    if entry.get("environment", "").lower() != environment.lower():
                        continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    # Return newest first
    return list(reversed(entries))[:limit]


if __name__ == "__main__":
    env_filter = sys.argv[1] if len(sys.argv) > 1 else None
    history = read_audit_history(limit=5, environment=env_filter)

    title = f"Recent Deployments ({env_filter or 'All Environments'})"
    print(f"\n===== {title} =====")

    if not history:
        print("No deployment records found.")
    else:
        for item in history:
            print(
                f"[{item['timestamp'][:19]}] ID: {item['deployment_id']} | "
                f"Env: {item['environment']} | Status: {item['status']} | "
                f"Commit: {item['commit_sha']} | Actor: {item['actor']}"
            )
            for dev in item.get("devices", []):
                print(
                    f"   - {dev['device_name']} ({dev['ip']}): "
                    f"{dev['status']} ({dev['commands_count']} cmds) | "
                    f"Backup: {dev.get('backup_file') or 'None'}"
                )

