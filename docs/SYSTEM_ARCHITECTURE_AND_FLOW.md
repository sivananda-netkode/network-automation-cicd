# Network CI/CD & Observability: System Architecture & End-to-End Flow

This document details the architectural blueprint and operational data flow of the Network Automation CI/CD and Observability platform.

---

## 1. High-Level Architecture Flowchart

```mermaid
flowchart TD
    subgraph SOT["1. Source of Truth (NetBox)"]
        NB_DCIM["NetBox DCIM REST API\n/api/dcim/devices/"]
        NB_CONF["Device Config Context\nlocal_context_data.cli_config"]
    end

    subgraph DISCOVERY["2. Dynamic Discovery"]
        GET_DEV["src/netbox/get_devices.py\nExtracts Active IPs & Roles"]
        GEN_TARGETS["src/observability/discovery.py\nGenerates Dynamic Labels"]
        FILE_SD["monitoring/prometheus/targets/devices.json\nPrometheus File SD"]
    end

    subgraph CICD["3. CI/CD Deployment Engine"]
        VALIDATE["Pre-Flight Validation\nsrc/network/validate_device_configs.py"]
        DIFF["Live State Diff & Plan\nsrc/network/compare_configs.py"]
        BACKUP["Pre-Deployment Backup\nsrc/network/backup_configs.py"]
        DEPLOY["Netmiko SSH Push\ndeploy_device()"]
        VERIFY["Post-Deploy Verification\nverify_device()"]
    end

    subgraph OBS_CHECK["4. Post-Deployment Health Check"]
        HOOK["deployment_engine.py hook\nENABLE_OBSERVABILITY_CHECK"]
        PIPE["src/observability/pipeline.py\nOrchestrates Evaluation"]
        COLLECTOR["src/observability/metrics_collector.py\nQueries 10 Parameters"]
        HEALTH["src/observability/health_checker.py\nThresholds & Status Matrix"]
        REPORT["Deployment Health Report\nHEALTHY / WARNING / CRITICAL"]
    end

    subgraph TELEMETRY["5. Observability Infrastructure (Docker Stack)"]
        SNMP_EXP["network-snmp-exporter:9116\nSNMPv3 MIB Translation"]
        PROM["network-prometheus:9090\nTime-Series TSDB & PromQL API"]
        GRAFANA["network-grafana:3000\nDynamic Dashboards ($role, $device)"]
        DEVICES[("Network Devices\nR1 (Router) & SW1 (Switch)")]
    end

    %% Connections
    NB_DCIM --> GET_DEV
    NB_CONF --> VALIDATE
    GET_DEV --> GEN_TARGETS
    GEN_TARGETS --> FILE_SD
    FILE_SD -.->|Auto-Watched| PROM

    GET_DEV --> CICD
    VALIDATE --> DIFF --> BACKUP --> DEPLOY --> VERIFY
    VERIFY --> HOOK
    HOOK --> PIPE
    PIPE --> HEALTH
    HEALTH --> COLLECTOR
    COLLECTOR -->|PromQL HTTP API| PROM
    HEALTH --> REPORT

    PROM -->|Scrape via SNMPv3| SNMP_EXP
    SNMP_EXP -->|SNMP GET/WALK| DEVICES
    PROM -->|Datasource Proxy| GRAFANA
```

---

## 2. The Dual-Loop System Design

The platform operates on two independent, non-interfering loops:

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ LOOP A: CONTINUOUS 24/7 OBSERVABILITY                                  │
 │                                                                        │
 │ NetBox ──► discovery.py ──► devices.json ──► Prometheus ──► Grafana   │
 │                                                   │                    │
 │                                                   ▼                    │
 │                                            Network Devices             │
 │                                            (SNMPv3 Scrapes)            │
 └────────────────────────────────────────────────────────────────────────┘

 ┌────────────────────────────────────────────────────────────────────────┐
 │ LOOP B: EVENT-DRIVEN CI/CD DEPLOYMENT PIPELINE                         │
 │                                                                        │
 │ NetBox ──► Validation ──► Backup ──► Deploy ──► Verify ──► Health Check│
 │                                                               │        │
 │                                                               ▼        │
 │                                                         Prometheus API │
 │                                                         (Read-Only)    │
 └────────────────────────────────────────────────────────────────────────┘
```

### Loop A: Continuous 24/7 Monitoring (Background Service)
1. **Always Running**: Operates inside Docker containers independently of whether deployments are occurring.
2. **Prometheus File-Based Service Discovery (`file_sd_configs`)**:
   - Prometheus watches `/etc/prometheus/targets/*.json`.
   - When new devices are added in NetBox and `discovery.py` runs, Prometheus reloads targets dynamically **with zero downtime or restart**.
3. **Out-of-Band Telemetry**:
   - The SNMP Exporter queries devices over SNMPv3 (SHA auth, AES priv).
   - Collects uptime, CPU, memory, interface status, traffic counters, bandwidth metrics, packet errors, OSPF states, and scrape latency.
4. **Grafana Visualization**:
   - Auto-provisioned datasource connects to Prometheus.
   - Dynamic template variables (`$role`, `$device`) query Prometheus label values directly, allowing operators to monitor all devices side-by-side or isolate a single device.

### Loop B: On-Demand CI/CD Deployment Pipeline
1. **Triggered on Demand**: Run by network engineers or automated deployment triggers.
2. **Deterministic Stages**:
   - **Validation**: Checks intended VLANs, DHCP pools, and syntax rules before touching devices.
   - **Live Diff**: Extracts live device running-config over Netmiko SSH and computes missing configuration.
   - **Safety Approval**: Requires typed operator confirmation (`DEPLOY` or `DEPLOY FULL`).
   - **Pre-Deployment Backup**: Saves timestamped running-config files with restricted permissions (`0600`) to `backups/`.
   - **Deployment**: Applies configuration changes via Netmiko.
   - **Device Verification**: Verifies that intended commands are active in running-config.
3. **Post-Deployment Telemetry Verification**:
   - Once device-level verification passes, CI/CD queries Prometheus via its HTTP API.
   - Compiles live telemetry across all 10 monitoring parameters and generates the **Deployment Health Report**.

---

## 3. Strict Safety & Fault-Tolerance Guarantees

| Requirement | Architectural Mechanism |
| :--- | :--- |
| **No Hardcoded Values** | Device IPs, names, roles, and credentials are discovered from NetBox and `.env`. PromQL queries use dynamic regex selectors (`instance=~"$ip(:\\d+)?"`). |
| **Independent Failure Isolation** | If Prometheus or an exporter is down, the deployment result is **not cancelled or rolled back**. CI/CD outputs an observability warning and preserves deployment status. |
| **Graceful Capability Handling** | Different Cisco hardware models support different MIBs (e.g., R1 supports Cisco CPU/Memory MIBs; SW1 does not). Unsupported metrics are reported as `[UNSUPPORTED]` without false healthy or failure. |
| **Zero Impact on Existing CI/CD** | All existing CI/CD modules remain untouched. All 66 original tests execute with 100% backward compatibility. |
| **Secret Protection** | Passwords and tokens exist only in `.env` (ignored by git). `.env.example` provides template placeholders only. |

