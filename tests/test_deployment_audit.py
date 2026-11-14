import json
from pathlib import Path
from unittest.mock import patch

from src.network.deployment_audit import (
    DeploymentRecord,
    DeviceAuditEntry,
    get_deployment_actor,
    get_git_commit_sha,
    read_audit_history,
    record_deployment,
)


def test_record_deployment_writes_jsonl(tmp_path: Path):
    log_file = tmp_path / "test_audit.jsonl"

    record = DeploymentRecord(
        environment="production",
        deployment_id="dep-test-1234",
        commit_sha="abc1234",
        actor="devops-engineer",
        status="SUCCESS",
        summary="Deployed 2 production devices",
        devices=[
            DeviceAuditEntry(
                device_name="R4",
                ip="192.168.6.1",
                site="Vizag Netkode",
                backup_file="backups/production/R4_20261113.cfg",
                commands_count=15,
                status="SUCCESS",
            ),
            DeviceAuditEntry(
                device_name="switch3",
                ip="192.168.9.2",
                site="Vizag Netkode",
                backup_file="backups/production/switch3_20261113.cfg",
                commands_count=18,
                status="SUCCESS",
            ),
        ],
    )

    written_path = record_deployment(record, log_path=log_file)
    assert written_path == log_file
    assert log_file.exists()

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["deployment_id"] == "dep-test-1234"
    assert data["environment"] == "production"
    assert data["status"] == "SUCCESS"
    assert len(data["devices"]) == 2
    assert data["devices"][0]["device_name"] == "R4"
    assert data["devices"][1]["device_name"] == "switch3"


def test_read_audit_history_filtering_and_order(tmp_path: Path):
    log_file = tmp_path / "audit.jsonl"

    rec_staging = DeploymentRecord(
        environment="staging",
        deployment_id="dep-stage-01",
        status="SUCCESS",
    )
    rec_prod = DeploymentRecord(
        environment="production",
        deployment_id="dep-prod-01",
        status="SUCCESS",
    )

    record_deployment(rec_staging, log_path=log_file)
    record_deployment(rec_prod, log_path=log_file)

    # Read all (newest first)
    all_entries = read_audit_history(log_path=log_file)
    assert len(all_entries) == 2
    assert all_entries[0]["deployment_id"] == "dep-prod-01"
    assert all_entries[1]["deployment_id"] == "dep-stage-01"

    # Filter by production
    prod_entries = read_audit_history(environment="production", log_path=log_file)
    assert len(prod_entries) == 1
    assert prod_entries[0]["deployment_id"] == "dep-prod-01"

    # Filter by staging
    stage_entries = read_audit_history(environment="staging", log_path=log_file)
    assert len(stage_entries) == 1
    assert stage_entries[0]["deployment_id"] == "dep-stage-01"


def test_actor_and_commit_resolution():
    with patch.dict("os.environ", {"GITHUB_ACTOR": "approver-user", "GITHUB_SHA": "abcdef1234567890"}):
        assert get_deployment_actor() == "approver-user"
        assert get_git_commit_sha() == "abcdef1234"

