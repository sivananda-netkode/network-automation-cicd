import json
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_grafana_datasource_provisioning_valid():
    ds_file = PROJECT_ROOT / "monitoring" / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
    assert ds_file.exists()

    with open(ds_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data.get("apiVersion") == 1
    datasources = data.get("datasources", [])
    assert len(datasources) >= 1
    prom = datasources[0]
    assert prom["name"] == "Prometheus"
    assert prom["type"] == "prometheus"
    assert prom["url"] == "http://prometheus:9090"
    assert prom["isDefault"] is True


def test_grafana_dashboard_provisioning_valid():
    prov_file = PROJECT_ROOT / "monitoring" / "grafana" / "provisioning" / "dashboards" / "dashboards.yml"
    assert prov_file.exists()

    with open(prov_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    providers = data.get("providers", [])
    assert len(providers) >= 1
    assert providers[0]["name"] == "Network Observability"


def test_grafana_dashboard_json_sections_and_variables():
    dash_file = PROJECT_ROOT / "monitoring" / "grafana" / "dashboards" / "network_observability.json"
    assert dash_file.exists()

    with open(dash_file, encoding="utf-8") as f:
        dash = json.load(f)

    assert dash["uid"] == "network-observability"
    assert dash["title"] == "Network Observability & Health"

    # Verify dynamic variables exist
    var_names = [v["name"] for v in dash.get("templating", {}).get("list", [])]
    assert "device" in var_names
    assert "role" in var_names

    # Verify panel titles cover the monitoring requirements
    panel_titles = [p.get("title", "") for p in dash.get("panels", [])]
    titles_str = " ".join(panel_titles).lower()

    assert "overall network health" in titles_str
    assert "availability" in titles_str
    assert "uptime" in titles_str
    assert "cpu" in titles_str
    assert "memory" in titles_str
    assert "interface operational status" in titles_str
    assert "interface traffic" in titles_str
    assert "bandwidth" in titles_str
    assert "errors" in titles_str
    assert "ospf" in titles_str
    assert "latency" in titles_str

