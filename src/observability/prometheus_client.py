import time
from typing import Any, Dict, List, Optional
import requests

from src.observability.config import (
    PROMETHEUS_STALE_THRESHOLD_SECONDS,
    PROMETHEUS_TIMEOUT,
    PROMETHEUS_URL,
)


class PrometheusAPIError(Exception):
    """Raised when the Prometheus HTTP API returns an error response."""
    pass


class PrometheusConnectionError(Exception):
    """Raised when unable to establish connection to the Prometheus server."""
    pass


class PrometheusClient:
    """Robust client for querying the Prometheus HTTP API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        stale_threshold_seconds: Optional[float] = None,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = (base_url or PROMETHEUS_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else PROMETHEUS_TIMEOUT
        self.stale_threshold_seconds = (
            stale_threshold_seconds
            if stale_threshold_seconds is not None
            else PROMETHEUS_STALE_THRESHOLD_SECONDS
        )
        self.session = session or requests.Session()

    def check_health(self) -> Dict[str, Any]:
        """Check if Prometheus is reachable and healthy."""
        url = f"{self.base_url}/-/healthy"
        try:
            response = self.session.get(url, timeout=self.timeout)
            is_healthy = response.status_code == 200
            return {
                "reachable": True,
                "healthy": is_healthy,
                "status_code": response.status_code,
                "message": response.text.strip(),
            }
        except requests.exceptions.Timeout as err:
            return {
                "reachable": False,
                "healthy": False,
                "status_code": None,
                "message": f"Connection timed out after {self.timeout}s: {err}",
            }
        except requests.exceptions.RequestException as err:
            return {
                "reachable": False,
                "healthy": False,
                "status_code": None,
                "message": f"Connection failed: {err}",
            }

    def query(
        self,
        query_str: str,
        query_time: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute an instant PromQL query with staleness detection.

        Distinguishes between query failure, missing metrics (empty results),
        and valid metrics with zero or non-zero values.
        """
        now = time.time()
        url = f"{self.base_url}/api/v1/query"
        params: Dict[str, Any] = {"query": query_str}
        if query_time is not None:
            params["time"] = query_time

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
        except requests.exceptions.Timeout as err:
            return {
                "success": False,
                "query": query_str,
                "status": "timeout",
                "error": f"Prometheus query timed out after {self.timeout}s: {err}",
                "timestamp": now,
                "results": [],
            }
        except requests.exceptions.RequestException as err:
            return {
                "success": False,
                "query": query_str,
                "status": "unreachable",
                "error": f"Failed to connect to Prometheus: {err}",
                "timestamp": now,
                "results": [],
            }

        try:
            payload = response.json()
        except ValueError as err:
            return {
                "success": False,
                "query": query_str,
                "status": "invalid_response",
                "error": f"Non-JSON response from Prometheus (HTTP {response.status_code}): {err}",
                "timestamp": now,
                "results": [],
            }

        if response.status_code != 200 or payload.get("status") != "success":
            error_msg = payload.get("error", f"HTTP {response.status_code}")
            error_type = payload.get("errorType", "APIError")
            return {
                "success": False,
                "query": query_str,
                "status": "error",
                "error": f"{error_type}: {error_msg}",
                "timestamp": now,
                "results": [],
            }

        data = payload.get("data", {})
        raw_results = data.get("result", [])
        parsed_results: List[Dict[str, Any]] = []

        for item in raw_results:
            metric_labels = item.get("metric", {})
            value_pair = item.get("value") or [None, None]
            metric_ts, raw_val = value_pair[0], value_pair[1]

            numeric_val: Optional[float] = None
            if raw_val is not None:
                try:
                    numeric_val = float(raw_val)
                except (ValueError, TypeError):
                    numeric_val = None

            is_stale = False
            age_seconds: Optional[float] = None
            if metric_ts is not None:
                age_seconds = round(now - float(metric_ts), 2)
                if age_seconds > self.stale_threshold_seconds:
                    is_stale = True

            parsed_results.append({
                "metric": metric_labels,
                "value": numeric_val,
                "raw_value": raw_val,
                "timestamp": float(metric_ts) if metric_ts is not None else None,
                "age_seconds": age_seconds,
                "is_stale": is_stale,
            })

        return {
            "success": True,
            "query": query_str,
            "status": "success",
            "error": None,
            "timestamp": now,
            "results": parsed_results,
        }

