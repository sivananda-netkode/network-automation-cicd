"""Live demonstration script for Jira Service Management incident lifecycle.

Demonstrates:
1. Dynamic discovery and creation of a customer request ticket in JSM.
2. Duplicate prevention (re-triggering alert posts an operational update comment instead of a duplicate ticket).
3. Querying ticket details and transition to Resolved state.
"""

import json
import logging
import sys

from integrations.jira.client import JiraClient
from integrations.jira.config import load_jira_config
from integrations.jira.ticket_manager import JiraTicketManager, NetworkIncident

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("jira_demo")


def run_demo():
    print("=" * 70)
    print("  JIRA SERVICE MANAGEMENT - LIVE INCIDENT LIFECYCLE DEMO")
    print("=" * 70)

    # 1. Initialize Client & Ticket Manager
    print("\n[Step 1] Loading Configuration & Initializing Jira Client...")
    config = load_jira_config()
    client = JiraClient(config)
    tm = JiraTicketManager(client=client)

    print(f"  Connected to Jira Cloud: {config.base_url}")
    print(f"  Target Project Key     : {config.project_key}")
    print(f"  Authenticated User     : {config.email}")

    # 2. Define Network Incident
    incident = NetworkIncident(
        device_name="R1",
        alert_name="BGP_NEIGHBOR_DOWN",
        alert_severity="High",
        alert_description="BGP session 192.168.12.2 (AS 65002) transitioned from Established to Idle. Prefix count dropped to 0.",
        device_ip="192.168.12.1",
        device_role="Core Router",
        site="Site-A",
        device_status="Degraded",
        telemetry={
            "peer_ip": "192.168.12.2",
            "peer_as": 65002,
            "bgp_state": "Idle",
            "flaps_last_hour": 3,
            "packet_loss": "100%",
        },
    )

    fingerprint = incident.get_fingerprint()
    print("\n[Step 2] Prepared Network Incident:")
    print(f"  Device Name : {incident.device_name}")
    print(f"  Alert Name  : {incident.alert_name}")
    print(f"  Severity    : {incident.alert_severity}")
    print(f"  Fingerprint : {fingerprint}")

    # 3. Process Network Alert -> Should CREATE Ticket
    print("\n[Step 3] Dispatching Network Alert (First Occurrence)...")
    res1 = tm.process_network_alert(incident)
    issue_key = res1.get("issue_key")

    print(f"  Action Taken : {res1.get('action')}")
    print(f"  Issue Key    : {issue_key}")
    print(f"  Status       : {res1.get('status')}")
    print(f"  Summary      : {res1.get('summary')}")
    print(f"  Browse URL   : {config.base_url}/browse/{issue_key}")
    if res1.get("web_url"):
        print(f"  Portal URL   : {res1.get('web_url')}")

    if not issue_key or res1.get("action") != "CREATED":
        print(f"FAILED: Unexpected result on creation: {res1}")
        sys.exit(1)

    # 4. Process Identical Alert -> Should PREVENT DUPLICATE and Add Comment
    print("\n[Step 4] Re-dispatching Same Alert (Duplicate Prevention Test)...")
    res2 = tm.process_network_alert(incident)

    print(f"  Action Taken : {res2.get('action')}")
    print(f"  Issue Key    : {res2.get('issue_key')}")
    print(f"  Message      : {res2.get('message')}")

    if res2.get("action") != "UPDATED_EXISTING" or res2.get("issue_key") != issue_key:
        print(f"FAILED: Duplicate prevention did not route to existing issue {issue_key}: {res2}")
        sys.exit(1)
    print("  --> Duplicate successfully blocked! Operational update comment appended.")

    # 5. Inspect Ticket Details
    print("\n[Step 5] Inspecting Ticket in Jira...")
    ticket_info = tm.get_ticket(issue_key)
    print(f"  Key          : {ticket_info.get('key')}")
    print(f"  Summary      : {ticket_info.get('summary')}")
    print(f"  Status       : {ticket_info.get('status')}")
    print(f"  Resolved?    : {ticket_info.get('is_resolved')}")

    # 6. Check Available Transitions & Resolve Ticket
    print("\n[Step 6] Resolving Test Incident in Jira...")
    available_transitions = tm.issue_manager.get_available_transitions(issue_key)
    print(f"  Available Transitions: {json.dumps(available_transitions, indent=2)}")

    res_trans = tm.resolve_ticket(
        issue_key,
        resolution_comment="Automated verification complete: BGP neighbor 192.168.12.2 restored to Established. Test closed.",
    )
    print(f"  Transition Result: {res_trans}")

    # 7. Final Verification
    final_info = tm.get_ticket(issue_key)
    print("\n[Step 7] Final Ticket State:")
    print(f"  Key       : {final_info.get('key')}")
    print(f"  Status    : {final_info.get('status')}")
    print(f"  Resolved? : {final_info.get('is_resolved')}")

    print("\n" + "=" * 70)
    print("  LIVE JIRA INCIDENT LIFECYCLE TEST COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()

