from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Server-only runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: AnyHttpUrl
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.6-flash"
    internal_api_token: SecretStr | None = None
    model_retry_delay_seconds: float = Field(default=1.5, ge=0, le=10)
    analysis_frame_count: int = 6

    @field_validator("analysis_frame_count")
    @classmethod
    def validate_analysis_frame_count(cls, value: int) -> int:
        """Keep one model call bounded to a small, deterministic frame set."""
        if not 3 <= value <= 8:
            raise ValueError("ANALYSIS_FRAME_COUNT must be between 3 and 8")
        return value

    @property
    def model_api_key(self) -> str | None:
        """Return the optional Gemini credential without exposing it in repr output."""
        if self.gemini_api_key is None:
            return None
        return self.gemini_api_key.get_secret_value()

    @property
    def internal_api_token_value(self) -> str | None:
        """Return the Java-to-Python bearer token without exposing it in repr output."""
        if self.internal_api_token is None:
            return None
        return self.internal_api_token.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache validated runtime settings."""
    return Settings()  # type: ignore[call-arg]
