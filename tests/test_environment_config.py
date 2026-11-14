from unittest.mock import patch
import pytest

from src.network.environment_config import (
    get_environment_config,
    validate_device_for_environment,
)


def test_get_environment_config_staging():
    cfg = get_environment_config("staging")
    assert cfg.name == "staging"
    assert cfg.site_slug == "hyderabad-netkode"
    assert cfg.site_name == "Hyderabad Netkode"
    assert cfg.allowed_devices == {"R1", "SW1"}


def test_get_environment_config_production():
    cfg = get_environment_config("production")
    assert cfg.name == "production"
    assert cfg.site_slug == "vizag-netkode"
    assert cfg.site_name == "Vizag Netkode"
    assert cfg.allowed_devices == {"R4", "switch3"}


def test_get_environment_config_default_is_staging():
    cfg = get_environment_config()
    assert cfg.name == "staging"
    assert cfg.site_slug == "hyderabad-netkode"


def test_get_environment_config_invalid_raises_value_error():
    with pytest.raises(ValueError, match="Invalid environment 'qa'"):
        get_environment_config("qa")


def test_credentials_resolution_staging():
    cfg = get_environment_config("staging")
    with patch.dict("os.environ", {"DEVICE_USERNAME": "stage_user", "DEVICE_PASSWORD": "stage_pass"}, clear=True):
        username, password = cfg.get_credentials()
        assert username == "stage_user"
        assert password == "stage_pass"


def test_credentials_resolution_production_dedicated():
    cfg = get_environment_config("production")
    with patch.dict(
        "os.environ",
        {
            "PROD_DEVICE_USERNAME": "prod_admin",
            "PROD_DEVICE_PASSWORD": "prod_secret_password",
            "DEVICE_USERNAME": "stage_user",
            "DEVICE_PASSWORD": "stage_pass",
        },
        clear=True,
    ):
        username, password = cfg.get_credentials()
        assert username == "prod_admin"
        assert password == "prod_secret_password"


def test_credentials_resolution_production_fallback():
    cfg = get_environment_config("production")
    with patch.dict(
        "os.environ",
        {
            "DEVICE_USERNAME": "fallback_user",
            "DEVICE_PASSWORD": "fallback_pass",
        },
        clear=True,
    ):
        username, password = cfg.get_credentials()
        assert username == "fallback_user"
        assert password == "fallback_pass"


def test_credentials_resolution_missing_raises_runtime_error():
    cfg = get_environment_config("production")
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="Missing SSH credentials"):
            cfg.get_credentials()


def test_validate_device_for_environment_valid_devices():
    # Valid devices should not raise any exception
    validate_device_for_environment("R1", "staging")
    validate_device_for_environment("SW1", "staging")
    validate_device_for_environment("r1", "staging")  # case-insensitive

    validate_device_for_environment("R4", "production")
    validate_device_for_environment("switch3", "production")
    validate_device_for_environment("SWITCH3", "production")  # case-insensitive


def test_validate_device_for_environment_cross_pollution_staging_to_production():
    with pytest.raises(ValueError, match="CRITICAL CROSS-ENVIRONMENT VIOLATION"):
        validate_device_for_environment("R1", "production")

    with pytest.raises(ValueError, match="CRITICAL CROSS-ENVIRONMENT VIOLATION"):
        validate_device_for_environment("sw1", "production")


def test_validate_device_for_environment_cross_pollution_production_to_staging():
    with pytest.raises(ValueError, match="CRITICAL CROSS-ENVIRONMENT VIOLATION"):
        validate_device_for_environment("R4", "staging")

    with pytest.raises(ValueError, match="CRITICAL CROSS-ENVIRONMENT VIOLATION"):
        validate_device_for_environment("switch3", "staging")


def test_validate_device_for_environment_unknown_device():
    with pytest.raises(ValueError, match="not recognized as an eligible device"):
        validate_device_for_environment("UnknownRouter99", "staging")

    with pytest.raises(ValueError, match="not recognized as an eligible device"):
        validate_device_for_environment("CoreSwitch01", "production")

