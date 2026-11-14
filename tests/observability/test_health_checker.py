from unittest.mock import MagicMock

from src.observability.health_checker import HealthChecker


def test_evaluate_device_health_healthy():
    checker = HealthChecker()
    telemetry = {
        "device": "R1",
        "ip": "192.168.1.1",
        "role": "Router",
        "metrics": {
            "availability": {"status": "HEALTHY", "value": 1.0, "is_stale": False},
            "uptime": {"status": "HEALTHY", "value": 86400, "is_stale": False},
            "cpu_utilization": {"status": "HEALTHY", "value": 25.0, "is_stale": False},
            "memory_utilization": {"status": "HEALTHY", "value": 40.0, "is_stale": False},
        },
    }
    report = checker.evaluate_device_health(telemetry)
    assert report["health_status"] == "HEALTHY"
    assert len(report["critical_issues"]) == 0
    assert len(report["warnings"]) == 0


def test_evaluate_device_health_with_unsupported_mibs_remains_healthy():
    checker = HealthChecker()
    telemetry = {
        "device": "SW1",
        "ip": "192.168.4.2",
        "role": "Switch",
        "metrics": {
            "availability": {"status": "HEALTHY", "value": 1.0, "is_stale": False},
            "uptime": {"status": "HEALTHY", "value": 86400, "is_stale": False},
            # SW1 does not support Cisco Process CPU MIB
            "cpu_utilization": {"status": "UNSUPPORTED", "value": None, "details": "MIB not exposed"},
            "memory_utilization": {"status": "HEALTHY", "value": 45.0, "is_stale": False},
        },
    }
    report = checker.evaluate_device_health(telemetry)
    assert report["health_status"] == "HEALTHY"
    assert "cpu_utilization" in report["unsupported_metrics"]


def test_evaluate_device_health_device_down_critical():
    checker = HealthChecker()
    telemetry = {
        "device": "R1",
        "ip": "192.168.1.1",
        "role": "Router",
        "metrics": {
            "availability": {"status": "CRITICAL", "value": 0.0, "is_stale": False},
        },
    }
    report = checker.evaluate_device_health(telemetry)
    assert report["health_status"] == "CRITICAL"
    assert any("DOWN" in issue for issue in report["critical_issues"])


def test_generate_report_prometheus_unreachable():
    mock_client = MagicMock()
    mock_client.check_health.return_value = {
        "reachable": False,
        "healthy": False,
        "message": "Connection refused to Prometheus",
    }
    checker = HealthChecker(client=mock_client)
    targets = [{"name": "R1", "ip": "192.168.1.1", "role": "Router"}]

    report = checker.generate_deployment_health_report(targets)
    assert report["prometheus_status"] == "UNREACHABLE"
    assert report["overall_health"] == "UNKNOWN"
    assert "Connection refused" in report["error"]


def test_generate_report_multi_device_aggregation():
    mock_client = MagicMock()
    mock_client.check_health.return_value = {"reachable": True, "healthy": True}

    mock_collector = MagicMock()
    mock_collector.collect_device_metrics.side_effect = [
        # Device 1: Healthy
        {
            "device": "R1",
            "ip": "192.168.1.1",
            "role": "Router",
            "metrics": {
                "availability": {"status": "HEALTHY", "value": 1.0},
                "cpu_utilization": {"status": "HEALTHY", "value": 20.0},
            },
        },
        # Device 2: Warning on High CPU
        {
            "device": "SW1",
            "ip": "192.168.4.2",
            "role": "Switch",
            "metrics": {
                "availability": {"status": "HEALTHY", "value": 1.0},
                "cpu_utilization": {"status": "WARNING", "value": 82.0, "details": "CPU load: 82%"},
            },
        },
    ]

    checker = HealthChecker(client=mock_client, collector=mock_collector)
    targets = [
        {"name": "R1", "ip": "192.168.1.1", "role": "Router", "deployment": "SUCCESS"},
        {"name": "SW1", "ip": "192.168.4.2", "role": "Switch", "deployment": "SUCCESS"},
    ]

    report = checker.generate_deployment_health_report(targets)
    assert report["prometheus_status"] == "REACHABLE"
    assert report["overall_health"] == "WARNING"
    assert report["summary"]["healthy"] == 1
    assert report["summary"]["warning"] == 1
    assert report["summary"]["critical"] == 0

