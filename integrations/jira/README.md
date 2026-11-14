# Jira Service Management (JSM) Integration for Network Automation

Standalone, production-grade Jira Service Management integration for network incident lifecycle management, dynamic schema discovery, duplicate alert prevention, and automated resolution.

---

## 1. Key Features

- **Zero Hardcoding**: Dynamically discovers Project ID, Service Desk ID, Request Type ID, required/optional field keys, and option IDs (Urgency/Impact) at runtime.
- **JSM Customer Request API**: Submits incidents via Jira Service Management REST API (`/rest/servicedeskapi/request`) with standard Jira REST API (`/rest/api/3/*`) for transitions and search.
- **Duplicate Alert Prevention**:
  - Computes a deterministic correlation fingerprint for every alert: `network-incident:<DEVICE>:<ALERT>`.
  - Searches Jira in real-time using JQL: `project = "<PROJECT>" AND statusCategory != Done AND description ~ "\"<FINGERPRINT>\""`.
  - When an alert recurs on an active incident, appends an operational telemetry update comment instead of creating a duplicate ticket.
  - Zero external database or Redis required — uses Jira as the single source of truth.
- **Credential Protection**: Redacts sensitive API tokens in string representations (`__repr__`, `__str__`), and never logs authentication headers or payload secrets.
- **High Test Coverage**: 23 unit tests with 100% mocked HTTP isolation covering auth, discovery, ticket lifecycle, and duplicate prevention.

---

## 2. Directory Structure

```
integrations/jira/
├── __init__.py           # Package exports (JiraClient, JiraTicketManager, NetworkIncident, etc.)
├── config.py             # Configuration loader, validation, and token redaction
├── client.py             # Low-level REST client with Basic Auth and custom exceptions
├── discovery.py          # Dynamic metadata discovery with caching
├── issue_manager.py      # Issue retrieval, comments, updates, and workflow transitions
├── ticket_manager.py     # NetworkIncident dataclass, ticket creation, duplicate prevention
├── demo_incident.py      # Live end-to-end incident lifecycle test runner
├── README.md             # This documentation
└── tests/
    ├── __init__.py
    ├── test_client.py         # 10 unit tests for client and auth
    ├── test_discovery.py      # 6 unit tests for dynamic discovery
    └── test_ticket_manager.py # 7 unit tests for ticket management & deduplication
```

---

## 3. Configuration & Environment Variables

Add the following environment variables to your `.env` file:

```bash
# Jira Service Management Configuration
JIRA_BASE_URL=https://<your-domain>.atlassian.net
JIRA_EMAIL=your.email@domain.com
JIRA_API_TOKEN=your_atlassian_api_token
JIRA_PROJECT_KEY=OPS
JIRA_REQUEST_TYPE_NAME="Report a system problem"  # Optional: defaults to auto-discovery
JIRA_REQUEST_TIMEOUT=15                            # Optional: default 15s
```

---

## 4. Quick Start & Python Usage

### Creating an Incident Alert with Duplicate Prevention

```python
from integrations.jira import JiraTicketManager, NetworkIncident

# Automatically loads configuration from .env and discovers JSM schema
ticket_mgr = JiraTicketManager()

# Define the network incident alert
alert = NetworkIncident(
    device_name="R1",
    alert_name="BGP_NEIGHBOR_DOWN",
    alert_severity="High",
    alert_description="BGP session 192.168.12.2 (AS 65002) transitioned to Idle.",
    device_ip="192.168.12.1",
    device_role="Core Router",
    site="Site-A",
    device_status="Degraded",
    telemetry={
        "peer_ip": "192.168.12.2",
        "peer_as": 65002,
        "bgp_state": "Idle",
        "packet_loss": "100%",
    },
)

# Process alert: creates fresh ticket if none exists, or comments on existing active ticket
result = ticket_mgr.process_network_alert(alert)

if result["action"] == "CREATED":
    print(f"Created Jira Ticket: {result['issue_key']}")
elif result["action"] == "UPDATED_EXISTING":
    print(f"Prevented duplicate. Appended update to {result['issue_key']}")
```

### Resolving an Incident

```python
# Transition incident to Completed/Resolved with an operational comment
res = ticket_mgr.resolve_ticket(
    issue_key="OPS-1",
    resolution_comment="BGP session restored. Adjacency verified.",
)
print(f"Resolved {res['issue_key']} via transition {res['transition_id']}")
```

---

## 5. Running the Test Suite

```bash
# Run Jira unit tests (mocked, no network needed)
./venv/bin/pytest -v integrations/jira/tests/

# Run the complete test suite (95 CI/CD & Observability + 23 Jira = 118 tests)
./venv/bin/pytest -v tests/ integrations/jira/tests/

# Run code validation
./venv/bin/python -m pyflakes src tests integrations
./venv/bin/python -m compileall -q src tests integrations
```

---

## 6. Running the Webhook Gateway (Prometheus Alertmanager)

To run the live Alertmanager Webhook Gateway for 24/7 continuous alerting:

```bash
# Start the Webhook Gateway on port 5050
./venv/bin/python -m integrations.jira.webhook_gateway
```

The gateway listens at:
- `GET http://localhost:5050/healthz` (Health check)
- `POST http://localhost:5050/api/v1/alerts` (Alertmanager webhook receiver)

### Automated Lifecycle on Interface Down:
1. When Prometheus detects `ifOperStatus == 2` on an interface for >30s, it fires `NetworkInterfaceDown`.
2. Alertmanager sends the webhook to the gateway.
3. The gateway creates an incident ticket (e.g. `OPS-X`) in Jira Cloud under project `OPS`.
4. If repeated scrapes or flaps occur, the gateway recognizes the correlation fingerprint and adds an operational telemetry comment instead of creating duplicate tickets.
5. When the interface is restored (`no shutdown` / link up), Alertmanager sends a `resolved` payload, and the gateway automatically transitions the ticket to `Completed`.

---

## 7. Running the Live Incident Demo

To test against your live Jira Cloud instance:

```bash
# Standalone ticket lifecycle demo
./venv/bin/python -m integrations.jira.demo_incident

# End-to-end Alertmanager webhook verification
./venv/bin/python -m integrations.jira.verify_live_alert
```

