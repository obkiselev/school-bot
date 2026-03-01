"""Configuration settings using pydantic-settings."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram Bot
    BOT_TOKEN: str = Field(..., description="Telegram Bot API token")

    # Database
    DATABASE_PATH: str = Field(
        default="data/school_bot.db",
        description="Path to SQLite database file"
    )

    # Encryption
    ENCRYPTION_KEY: str = Field(..., description="Fernet encryption key for credentials")

    # МЭШ API (URL управляются библиотекой OctoDiary)
    MESH_TIMEOUT: int = Field(default=30, description="API request timeout in seconds")
    MESH_MAX_RETRIES: int = Field(default=3, description="Maximum API retry attempts")

    # Notifications
    GRADES_NOTIFICATION_TIME: str = Field(
        default="18:00",
        description="Default time for grades notifications (HH:MM)"
    )
    HOMEWORK_NOTIFICATION_TIME: str = Field(
        default="19:00",
        description="Default time for homework notifications (HH:MM)"
    )
    TIMEZONE: str = Field(
        default="Europe/Moscow",
        description="Timezone for notifications"
    )

    # Browser Auth (Playwright/Patchright)
    MESH_AUTH_HEADLESS: bool = Field(
        default=True,
        description="Run browser auth in headless mode (False for debugging)"
    )
    MESH_AUTH_STEALTH: bool = Field(
        default=True,
        description="Apply anti-detection scripts to browser"
    )

    # Rate Limiting
    API_MAX_CALLS: int = Field(
        default=30,
        description="Maximum API calls per period"
    )
    API_PERIOD_SECONDS: int = Field(
        default=60,
        description="Rate limit period in seconds"
    )

    # Logging
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    LOG_FILE: str = Field(
        default="data/logs/bot.log",
        description="Path to log file"
    )

    class Config:
        """Pydantic config."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()
