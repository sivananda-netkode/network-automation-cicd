"""Environment Configuration & Credential Manager.

Manages environment profiles (staging vs. production), site mapping to NetBox,
dynamic credential resolution, and anti-cross-pollution device validation.
"""

from dataclasses import dataclass, field
import os
from typing import Optional, Set, Tuple
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class EnvironmentConfig:
    """Immutable environment profile definition."""
    name: str
    site_slug: str
    site_name: str
    username_env_var: str
    password_env_var: str
    allowed_devices: Set[str] = field(default_factory=set)

    def get_credentials(self) -> Tuple[str, str]:
        """Resolve username and password for this environment from environment variables."""
        username = os.getenv(self.username_env_var)
        password = os.getenv(self.password_env_var)

        # Fallback to default DEVICE_USERNAME/DEVICE_PASSWORD if production-specific vars are not set
        if not username:
            username = os.getenv("DEVICE_USERNAME")
        if not password:
            password = os.getenv("DEVICE_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                f"Missing SSH credentials for '{self.name}' environment. "
                f"Please set {self.username_env_var} and {self.password_env_var} (or DEVICE_USERNAME / DEVICE_PASSWORD)."
            )

        return username, password


# Static profile definitions
_PROFILES = {
    "staging": EnvironmentConfig(
        name="staging",
        site_slug="hyderabad-netkode",
        site_name="Hyderabad Netkode",
        username_env_var="DEVICE_USERNAME",
        password_env_var="DEVICE_PASSWORD",
        allowed_devices={"R1", "SW1"},
    ),
    "production": EnvironmentConfig(
        name="production",
        site_slug="vizag-netkode",
        site_name="Vizag Netkode",
        username_env_var="PROD_DEVICE_USERNAME",
        password_env_var="PROD_DEVICE_PASSWORD",
        allowed_devices={"R4", "switch3"},
    ),
}


def get_environment_config(environment: Optional[str] = None) -> EnvironmentConfig:
    """Retrieve the EnvironmentConfig profile for the specified environment.

    Defaults to 'staging' if not provided or empty.
    """
    env_clean = (environment or "staging").strip().lower()
    if env_clean not in _PROFILES:
        valid_envs = ", ".join(f"'{k}'" for k in _PROFILES.keys())
        raise ValueError(
            f"Invalid environment '{environment}'. Supported environments are: {valid_envs}"
        )
    return _PROFILES[env_clean]


def validate_device_for_environment(device_name: str, environment: str) -> None:
    """Strict anti-cross-pollution guard.

    Ensures that staging devices (e.g. R1, SW1) cannot be targeted during a
    production run, and production devices (e.g. R4, switch3) cannot be targeted
    during a staging run.
    """
    config = get_environment_config(environment)
    clean_name = device_name.strip()

    # Check if the device belongs to another environment (cross-pollution attempt)
    for other_env, other_config in _PROFILES.items():
        if other_env != config.name:
            if clean_name.lower() in {d.lower() for d in other_config.allowed_devices}:
                raise ValueError(
                    f"CRITICAL CROSS-ENVIRONMENT VIOLATION: Device '{device_name}' belongs to "
                    f"'{other_config.name}' ({other_config.site_name}) and CANNOT be deployed under '{config.name}'!"
                )

    # Check if device is recognized in target environment
    known_devices = {d.lower() for d in config.allowed_devices}
    if known_devices and clean_name.lower() not in known_devices:
        raise ValueError(
            f"Device '{device_name}' is not recognized as an eligible device for '{config.name}' environment. "
            f"Allowed devices for {config.name}: {sorted(config.allowed_devices)}"
        )

