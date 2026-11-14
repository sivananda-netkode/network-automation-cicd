import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class JiraConfigError(Exception):
    """Raised when Jira configuration is missing or invalid."""
    pass


class JiraConfig:
    """Encapsulates Jira Service Management connection settings securely."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        timeout: float = 15.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email.strip()
        self.api_token = api_token.strip()
        self.project_key = project_key.strip().upper()
        self.timeout = timeout
        self.max_retries = max_retries

    def validate(self) -> None:
        """Validate required Jira configuration fields without revealing secrets."""
        missing = []
        if not self.base_url:
            missing.append("JIRA_BASE_URL")
        if not self.email:
            missing.append("JIRA_EMAIL")
        if not self.api_token:
            missing.append("JIRA_API_TOKEN")
        if not self.project_key:
            missing.append("JIRA_PROJECT_KEY")

        if missing:
            raise JiraConfigError(
                f"Missing required Jira configuration variables: {', '.join(missing)}"
            )

        if not (self.base_url.startswith("http://") or self.base_url.startswith("https://")):
            raise JiraConfigError(
                "JIRA_BASE_URL must begin with 'https://' or 'http://'"
            )

    def __repr__(self) -> str:
        """Safe representation ensuring API tokens are never leaked."""
        return (
            f"JiraConfig(base_url='{self.base_url}', "
            f"email='{self.email}', "
            f"project_key='{self.project_key}', "
            f"api_token='***REDACTED***', "
            f"timeout={self.timeout})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def load_jira_config(env_path: Optional[Path] = None) -> JiraConfig:
    """Load Jira configuration from the environment or .env file."""
    target_env = env_path or (PROJECT_ROOT / ".env")
    if target_env.exists():
        load_dotenv(target_env)

    base_url = os.getenv("JIRA_BASE_URL", "")
    email = os.getenv("JIRA_EMAIL", "")
    api_token = os.getenv("JIRA_API_TOKEN", "")
    project_key = os.getenv("JIRA_PROJECT_KEY", "")

    try:
        timeout = float(os.getenv("JIRA_TIMEOUT", "15.0"))
    except ValueError:
        timeout = 15.0

    try:
        max_retries = int(os.getenv("JIRA_MAX_RETRIES", "3"))
    except ValueError:
        max_retries = 3

    config = JiraConfig(
        base_url=base_url,
        email=email,
        api_token=api_token,
        project_key=project_key,
        timeout=timeout,
        max_retries=max_retries,
    )
    config.validate()
    return config
