"""Reader settings, read from the project .env."""

from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class ReaderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    root: Path = ROOT
    llm_mode: Literal["baseline", "compatible"] = "baseline"
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=90, ge=1, le=180)
    llm_max_tokens: int = Field(default=4500, ge=256, le=65536)
    llm_thinking: Literal["provider_default", "enabled", "disabled"] = "provider_default"
    reader_requests_per_day: int | None = Field(default=None, ge=0)
    reader_tokens_per_day: int | None = Field(default=None, ge=0)
    # IANA name such as Asia/Shanghai; empty uses the system timezone. Sets when the daily budget resets.
    reader_timezone: str = ""
    reader_batch_size: int = Field(default=4, ge=1, le=6)
    reader_follow_analyze_limit: int = Field(default=6, ge=1, le=24)
    reader_model_concurrency: int = Field(default=1, ge=1, le=4)
    reader_web_api_key: SecretStr = SecretStr("")
    reader_openalex_api_key: SecretStr = SecretStr("")
    reader_x_bearer_token: SecretStr = SecretStr("")
    # Accounts. token: every reader signs in with a token (each token is one account with its own
    # data); off: a single local reader, as before accounts existed (personal installs only).
    reader_auth: Literal["token", "off"] = "token"
    # Let visitors create their own token on the sign-in page.
    reader_signup: bool = True
    reader_signups_per_hour: int = Field(default=10, ge=0, le=1000)  # per client address
    # Limits for ordinary accounts (admins are not limited). Empty requests limit: unlimited.
    reader_user_follow_limit: int = Field(default=3, ge=0, le=12)
    reader_user_requests_per_day: int | None = Field(default=10, ge=0)
    # Session cookie Secure flag: auto follows the request scheme (X-Forwarded-Proto included).
    reader_cookie_secure: Literal["auto", "always", "never"] = "auto"
    # Extra origins allowed to send changes, comma separated (the site's own origin always is).
    reader_allowed_origins: str = ""
    # Public digest: when set, every completed update also writes the static site here
    # (relative paths are under the project). Empty: publish only with the CLI command.
    reader_publish_dir: str = ""
    # Address the published site is served from, e.g. https://you.github.io/daily/ (RSS links).
    reader_public_url: str = ""

    def publish_path(self, value=None):
        value = value or self.reader_publish_dir
        if not value:
            return None
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.root / path

    @field_validator("reader_timezone")
    @classmethod
    def known_timezone(cls, value):
        if value:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError(f"未知时区：{value}（示例：Asia/Shanghai）") from None
        return value
