import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"true", "1", "yes", "on"}


# Prometheus Server Connection Settings
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
PROMETHEUS_TIMEOUT = get_env_float("PROMETHEUS_TIMEOUT", 10.0)
PROMETHEUS_STALE_THRESHOLD_SECONDS = get_env_float("PROMETHEUS_STALE_THRESHOLD_SECONDS", 120.0)

# Threshold Settings
CPU_WARNING_THRESHOLD = get_env_float("CPU_WARNING_THRESHOLD", 75.0)
CPU_CRITICAL_THRESHOLD = get_env_float("CPU_CRITICAL_THRESHOLD", 90.0)

MEMORY_WARNING_THRESHOLD = get_env_float("MEMORY_WARNING_THRESHOLD", 80.0)
MEMORY_CRITICAL_THRESHOLD = get_env_float("MEMORY_CRITICAL_THRESHOLD", 90.0)

BANDWIDTH_WARNING_THRESHOLD = get_env_float("BANDWIDTH_WARNING_THRESHOLD", 80.0)
BANDWIDTH_CRITICAL_THRESHOLD = get_env_float("BANDWIDTH_CRITICAL_THRESHOLD", 90.0)

LATENCY_WARNING_MS = get_env_float("LATENCY_WARNING_MS", 500.0)
LATENCY_CRITICAL_MS = get_env_float("LATENCY_CRITICAL_MS", 2000.0)

# Target File Location for Prometheus File-Based Service Discovery
DEFAULT_TARGETS_PATH = PROJECT_ROOT / "monitoring" / "prometheus" / "targets" / "devices.json"
TARGETS_FILE_PATH = Path(os.getenv("PROMETHEUS_TARGETS_FILE", str(DEFAULT_TARGETS_PATH)))

# Integration Toggle
ENABLE_OBSERVABILITY_CHECK = get_env_bool("ENABLE_OBSERVABILITY_CHECK", True)

