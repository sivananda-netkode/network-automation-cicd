import time
from unittest.mock import MagicMock
import requests

from src.observability.prometheus_client import PrometheusClient


def test_prometheus_health_check_healthy():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "Prometheus Server is Healthy."
    mock_session.get.return_value = mock_resp

    client = PrometheusClient(base_url="http://mock-prometheus:9090", session=mock_session)
    res = client.check_health()
    assert res["reachable"] is True
    assert res["healthy"] is True


def test_prometheus_health_check_unreachable():
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.ConnectionError("Connection refused")

    client = PrometheusClient(base_url="http://mock-prometheus:9090", session=mock_session)
    res = client.check_health()
    assert res["reachable"] is False
    assert res["healthy"] is False
    assert "Connection failed" in res["message"]


def test_prometheus_health_check_timeout():
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.Timeout("timed out")

    client = PrometheusClient(base_url="http://mock-prometheus:9090", session=mock_session)
    res = client.check_health()
    assert res["reachable"] is False
    assert res["healthy"] is False
    assert "timed out" in res["message"]


def test_prometheus_query_success_numeric_and_staleness():
    now = time.time()
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"instance": "192.168.1.1", "device": "R1"},
                    "value": [now - 10, "42.5"],
                }
            ],
        },
    }
    mock_session.get.return_value = mock_resp

    client = PrometheusClient(base_url="http://mock-prom:9090", session=mock_session, stale_threshold_seconds=60)
    res = client.query("cpmCPUTotal5min")
    assert res["success"] is True
    assert res["status"] == "success"
    assert len(res["results"]) == 1

    first = res["results"][0]
    assert first["value"] == 42.5
    assert first["raw_value"] == "42.5"
    assert first["is_stale"] is False


def test_prometheus_query_detects_stale_metrics():
    now = time.time()
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"instance": "192.168.1.1"},
                    "value": [now - 300, "1.0"],  # 300 seconds old
                }
            ],
        },
    }
    mock_session.get.return_value = mock_resp

    client = PrometheusClient(base_url="http://mock-prom:9090", session=mock_session, stale_threshold_seconds=60)
    res = client.query("up")
    assert res["success"] is True
    assert res["results"][0]["is_stale"] is True


def test_prometheus_query_distinguishes_zero_from_missing():
    now = time.time()
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"instance": "192.168.1.1"},
                    "value": [now, "0"],
                }
            ],
        },
    }
    mock_session.get.return_value = mock_resp

    client = PrometheusClient(session=mock_session)
    res = client.query("rate(ifInErrors[5m])")
    assert res["success"] is True
    assert len(res["results"]) == 1
    # 0 is a valid numeric value, not None or missing
    assert res["results"][0]["value"] == 0.0


def test_prometheus_query_empty_results_missing_metric():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [],
        },
    }
    mock_session.get.return_value = mock_resp

    client = PrometheusClient(session=mock_session)
    res = client.query("unsupported_metric_name")
    assert res["success"] is True
    assert res["results"] == []


def test_prometheus_query_api_error_response():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "status": "error",
        "errorType": "bad_data",
        "error": "parse error: unexpected end of input",
    }
    mock_session.get.return_value = mock_resp

    client = PrometheusClient(session=mock_session)
    res = client.query("invalid query {")
    assert res["success"] is False
    assert res["status"] == "error"
    assert "bad_data" in res["error"]

