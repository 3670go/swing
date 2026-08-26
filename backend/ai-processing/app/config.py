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

    database_url: SecretStr
    supabase_url: AnyHttpUrl
    supabase_secret_key: SecretStr
    supabase_storage_bucket: str = "swing-media"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.6-flash"
    gpt_action_api_key: SecretStr | None = None
    gpt_action_file_hosts: tuple[str, ...] = ("files.oaiusercontent.com",)
    model_retry_delay_seconds: float = Field(default=1.5, ge=0, le=10)
    cors_origins: tuple[str, ...] = ("http://localhost:4173", "http://127.0.0.1:4173")
    analysis_frame_count: int = 6
    max_video_bytes: int | None = None
    allowed_video_content_types: tuple[str, ...] = (
        "video/mp4",
        "video/quicktime",
        "video/webm",
    )
    allowed_photo_content_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
    )

    @field_validator("supabase_storage_bucket")
    @classmethod
    def validate_bucket_name(cls, value: str) -> str:
        """Reject bucket names that cannot be used as a stable Storage identifier."""
        normalized = value.strip()
        allowed_characters = "abcdefghijklmnopqrstuvwxyz0123456789-"
        if not normalized or any(character not in allowed_characters for character in normalized):
            raise ValueError(
                "SUPABASE_STORAGE_BUCKET must use lowercase letters, digits, or hyphens"
            )
        return normalized

    @field_validator("max_video_bytes")
    @classmethod
    def validate_max_video_bytes(cls, value: int | None) -> int | None:
        """Require a positive upload limit when one has been approved."""
        if value is not None and value <= 0:
            raise ValueError("MAX_VIDEO_BYTES must be positive")
        return value

    @field_validator("analysis_frame_count")
    @classmethod
    def validate_analysis_frame_count(cls, value: int) -> int:
        """Keep one model call bounded to a small, deterministic frame set."""
        if not 3 <= value <= 8:
            raise ValueError("ANALYSIS_FRAME_COUNT must be between 3 and 8")
        return value

    @property
    def database_dsn(self) -> str:
        """Return the database DSN without exposing it through repr output."""
        return self.database_url.get_secret_value()

    @property
    def secret_key(self) -> str:
        """Return the server-only Supabase secret key for adapter construction."""
        return self.supabase_secret_key.get_secret_value()

    @property
    def model_api_key(self) -> str | None:
        """Return the optional Gemini credential without exposing it in repr output."""
        if self.gemini_api_key is None:
            return None
        return self.gemini_api_key.get_secret_value()

    @property
    def action_api_key(self) -> str | None:
        """Return the server-only bearer token used by the Custom GPT Action."""
        if self.gpt_action_api_key is None:
            return None
        return self.gpt_action_api_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache validated runtime settings."""
    return Settings()  # type: ignore[call-arg]
