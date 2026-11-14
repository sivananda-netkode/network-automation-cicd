from unittest.mock import MagicMock

from src.observability.metrics_collector import MetricsCollector


def test_collect_availability_healthy():
    mock_client = MagicMock()
    mock_client.query.return_value = {
        "success": True,
        "results": [{"metric": {"instance": "192.168.1.1"}, "value": 1.0, "is_stale": False}],
    }
    collector = MetricsCollector(client=mock_client)
    res = collector._get_availability('instance=~"192.168.1.1"')
    assert res["status"] == "HEALTHY"
    assert res["is_up"] is True


def test_collect_availability_device_down():
    mock_client = MagicMock()
    mock_client.query.return_value = {
        "success": True,
        "results": [{"metric": {"instance": "192.168.1.1"}, "value": 0.0, "is_stale": False}],
    }
    collector = MetricsCollector(client=mock_client)
    res = collector._get_availability('instance=~"192.168.1.1"')
    assert res["status"] == "CRITICAL"
    assert res["is_up"] is False


def test_collect_uptime_recent_reboot():
    mock_client = MagicMock()
    # 120 seconds uptime
    mock_client.query.return_value = {
        "success": True,
        "results": [{"metric": {}, "value": 120.0, "is_stale": False}],
    }
    collector = MetricsCollector(client=mock_client)
    res = collector._get_uptime('instance=~"192.168.1.1"')
    assert res["status"] == "WARNING"
    assert "Rebooted" in res["details"]


def test_collect_cpu_unsupported_mib():
    mock_client = MagicMock()
    # Empty result indicates MIB not supported on this device
    mock_client.query.return_value = {
        "success": True,
        "results": [],
    }
    collector = MetricsCollector(client=mock_client)
    res = collector._get_cpu_utilization('instance=~"192.168.4.2"')
    assert res["status"] == "UNSUPPORTED"
    assert "not exposed" in res["details"]


def test_collect_cpu_thresholds():
    mock_client = MagicMock()
    mock_client.query.return_value = {
        "success": True,
        "results": [{"value": 92.0, "is_stale": False}],
    }
    collector = MetricsCollector(client=mock_client)
    res = collector._get_cpu_utilization('instance=~"192.168.1.1"')
    assert res["status"] == "CRITICAL"


def test_collect_memory_unsupported_mib():
    mock_client = MagicMock()
    mock_client.query.return_value = {
        "success": True,
        "results": [],
    }
    collector = MetricsCollector(client=mock_client)
    res = collector._get_memory_utilization('instance=~"192.168.4.2"')
    assert res["status"] == "UNSUPPORTED"


def test_collect_ospf_full():
    mock_client = MagicMock()
    mock_client.query.return_value = {
        "success": True,
        "results": [
            {"metric": {"ospfNbrIpAddr": "192.168.1.2"}, "value": 8.0}
        ],
    }
    collector = MetricsCollector(client=mock_client)
    res = collector._get_ospf_status('instance=~"192.168.1.1"', role="Router")
    assert res["status"] == "HEALTHY"
    assert res["all_full"] is True


def test_collect_ospf_switch_not_configured():
    mock_client = MagicMock()
    mock_client.query.return_value = {"success": True, "results": []}
    collector = MetricsCollector(client=mock_client)
    res = collector._get_ospf_status('instance=~"192.168.4.2"', role="Switch")
    assert res["status"] == "NOT_CONFIGURED"


def test_collect_interface_errors_detected():
    mock_client = MagicMock()

    def query_router(q):
        if "ifInErrors" in q:
            return {"success": True, "results": [{"value": 5.0}]}
        elif "ifOutErrors" in q:
            return {"success": True, "results": [{"value": 0.0}]}
        return {"success": True, "results": []}

    mock_client.query.side_effect = query_router
    collector = MetricsCollector(client=mock_client)
    res = collector._get_interface_metrics('instance=~"192.168.1.1"')
    assert res["errors"]["status"] == "WARNING"
    assert "5.0 errors/sec" in res["errors"]["details"]

