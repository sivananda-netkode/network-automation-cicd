"""Live end-to-end verification script for the Prometheus Alertmanager Jira Webhook Gateway.

Tests:
1. Webhook gateway /healthz response.
2. Firing alert simulation -> creates ticket in Jira Cloud.
3. Duplicate firing alert simulation -> appends comment, blocks duplicate.
4. Resolved alert simulation -> auto-resolves ticket in Jira Cloud.
"""

from datetime import datetime, timezone
import json
import logging
import threading
import time

import requests

from integrations.jira.client import JiraClient
from integrations.jira.config import load_jira_config
from integrations.jira.ticket_manager import JiraTicketManager
from integrations.jira.webhook_gateway import create_gateway_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("verify_live_alert")


def run_live_verification():
    print("=" * 75)
    print("  PROMETHEUS ALERTMANAGER -> JIRA SERVICE MANAGEMENT LIVE TEST")
    print("=" * 75)

    # 1. Initialize Jira Manager & Webhook Gateway
    print("\n[Step 1] Initializing Jira Ticket Manager & Starting Gateway Server...")
    config = load_jira_config()
    client = JiraClient(config)
    tm = JiraTicketManager(client=client)

    server = create_gateway_server(host="127.0.0.1", port=5050)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    base_url = "http://127.0.0.1:5050"
    print(f"  Gateway Server listening at {base_url}")

    # 2. Check Gateway Health Endpoint
    print("\n[Step 2] Testing Gateway /healthz Endpoint...")
    resp = requests.get(f"{base_url}/healthz", timeout=5)
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    print(f"  Response: {resp.json()}")

    # 3. Simulate Firing Alert for R1 GigabitEthernet0/1
    print("\n[Step 3] Simulating Prometheus Alertmanager Webhook: [FIRING] R1 GigabitEthernet0/1 Down...")
    firing_payload = {
        "receiver": "jira-webhook-gateway",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "NetworkInterfaceDown",
                    "device": "R1",
                    "instance": "192.168.1.1:9116",
                    "ifDescr": "GigabitEthernet0/1",
                    "ifIndex": "1",
                    "severity": "High",
                    "monitoring_source": "Prometheus / SNMP",
                },
                "annotations": {
                    "summary": "Interface GigabitEthernet0/1 is DOWN on R1",
                    "description": "Interface GigabitEthernet0/1 (ifIndex: 1) on device R1 (192.168.1.1) transitioned to operational DOWN (status=2).",
                },
                "startsAt": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }

    resp = requests.post(f"{base_url}/api/v1/alerts", json=firing_payload, timeout=15)
    assert resp.status_code == 200, f"Alert submission failed: {resp.text}"
    body = resp.json()
    print(f"  Gateway Response: {json.dumps(body, indent=2)}")

    res0 = body["results"][0]
    action = res0.get("result", {}).get("action")
    issue_key = res0.get("result", {}).get("issue_key")
    print(f"  Action Taken : {action}")
    print(f"  Ticket Key   : {issue_key}")
    print(f"  Browse URL   : {config.base_url}/browse/{issue_key}")

    assert action in ("CREATED", "UPDATED_EXISTING"), f"Unexpected action: {action}"
    assert issue_key, "Missing issue key from gateway response"

    # 4. Simulate Duplicate Firing Alert
    print("\n[Step 4] Simulating Duplicate Alert (Flap / Repeated Scrape)...")
    resp_dup = requests.post(f"{base_url}/api/v1/alerts", json=firing_payload, timeout=15)
    body_dup = resp_dup.json()
    dup_res0 = body_dup["results"][0]
    dup_action = dup_res0.get("result", {}).get("action")
    dup_key = dup_res0.get("result", {}).get("issue_key")
    print(f"  Action Taken : {dup_action}")
    print(f"  Ticket Key   : {dup_key}")
    print(f"  Message      : {dup_res0.get('result', {}).get('message')}")
    assert dup_action == "UPDATED_EXISTING", f"Expected duplicate block, got {dup_action}"
    assert dup_key == issue_key, f"Expected same issue key {issue_key}, got {dup_key}"
    print("  --> Duplicate successfully blocked! Telemetry update comment added.")

    # 5. Simulate Resolved Alert
    print("\n[Step 5] Simulating Prometheus Alertmanager Webhook: [RESOLVED] R1 GigabitEthernet0/1 Up...")
    resolved_payload = {
        "receiver": "jira-webhook-gateway",
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {
                    "alertname": "NetworkInterfaceDown",
                    "device": "R1",
                    "instance": "192.168.1.1:9116",
                    "ifDescr": "GigabitEthernet0/1",
                    "ifIndex": "1",
                },
                "endsAt": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }

    resp_res = requests.post(f"{base_url}/api/v1/alerts", json=resolved_payload, timeout=15)
    assert resp_res.status_code == 200, f"Resolved alert submission failed: {resp_res.text}"
    body_res = resp_res.json()
    print(f"  Gateway Response: {json.dumps(body_res, indent=2)}")

    res_action = body_res["results"][0].get("action")
    print(f"  Action Taken : {res_action}")
    assert res_action == "AUTO_RESOLVED", f"Expected AUTO_RESOLVED, got {res_action}"

    # 6. Verify Ticket State in Jira Cloud
    print("\n[Step 6] Inspecting Final Ticket State in Jira Cloud...")
    final_ticket = tm.get_ticket(issue_key)
    print(f"  Ticket Key : {final_ticket.get('key')}")
    print(f"  Status     : {final_ticket.get('status')}")
    print(f"  Resolved?  : {final_ticket.get('is_resolved')}")

    assert final_ticket.get("is_resolved") is True, f"Ticket {issue_key} was not resolved!"

    # Clean shutdown
    server.shutdown()
    print("\n" + "=" * 75)
    print("  ALL REAL-TIME INCIDENT WORKFLOW VERIFICATIONS PASSED!")
    print("=" * 75)


if __name__ == "__main__":
    run_live_verification()
