"""Reader settings, read from the project .env."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    reader_web_api_key: SecretStr = SecretStr("")
    reader_openalex_api_key: SecretStr = SecretStr("")
    reader_x_bearer_token: SecretStr = SecretStr("")
