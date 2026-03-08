"""Configuration settings using pydantic-settings."""
import re
from typing import Optional
from urllib.parse import urlparse

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


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

    @field_validator("GRADES_NOTIFICATION_TIME", "HOMEWORK_NOTIFICATION_TIME")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not re.match(r"^\d{1,2}:\d{2}$", v):
            raise ValueError(f"Invalid time format '{v}', expected HH:MM")
        h, m = v.split(":")
        if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
            raise ValueError(f"Invalid time '{v}': hour 0-23, minute 0-59")
        return v

    @field_validator("TIMEZONE")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        import pytz
        try:
            pytz.timezone(v)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Unknown timezone '{v}'")
        return v

    # Browser Auth (Playwright/Patchright)
    MESH_AUTH_HEADLESS: bool = Field(
        default=True,
        description="Run browser auth in headless mode (False for debugging)"
    )
    MESH_AUTH_STEALTH: bool = Field(
        default=True,
        description="Apply anti-detection scripts to browser"
    )

    # Proxy for МЭШ authentication (optional)
    MESH_PROXY_URL: Optional[str] = Field(
        default=None,
        description="Proxy URL for МЭШ auth (http://host:port, socks5://host:port, http://user:pass@host:port)"
    )

    # SSH tunnel (auto-start SOCKS5 proxy via SSH)
    MESH_SSH_PROXY: bool = Field(
        default=False,
        description="Auto-start SSH SOCKS5 tunnel on bot startup"
    )
    MESH_SSH_HOST: Optional[str] = Field(
        default=None,
        description="SSH server address"
    )
    MESH_SSH_PORT: int = Field(
        default=22,
        description="SSH server port"
    )
    MESH_SSH_USER: Optional[str] = Field(
        default=None,
        description="SSH username"
    )
    MESH_SSH_KEY: Optional[str] = Field(
        default=None,
        description="Path to SSH private key"
    )
    MESH_SSH_PATH: Optional[str] = Field(
        default=None,
        description="Path to SSH executable (if system ssh hangs, use Git's ssh)"
    )

    def get_proxy_settings(self) -> Optional[dict]:
        """Parse MESH_PROXY_URL into formats for Playwright and curl_cffi.

        Returns None if no proxy configured, otherwise:
        {
            "url": "socks5://user:pass@host:port",
            "playwright": {"server": "socks5://host:port", "username": ..., "password": ...},
            "curl_cffi": "socks5://user:pass@host:port",
        }
        """
        if not self.MESH_PROXY_URL:
            return None

        parsed = urlparse(self.MESH_PROXY_URL)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or ""
        port = parsed.port

        server = f"{scheme}://{host}"
        if port:
            server += f":{port}"

        pw_proxy = {"server": server}
        if parsed.username:
            pw_proxy["username"] = parsed.username
        if parsed.password:
            pw_proxy["password"] = parsed.password

        return {
            "url": self.MESH_PROXY_URL,
            "playwright": pw_proxy,
            "curl_cffi": self.MESH_PROXY_URL,
        }

    # LLM (тестирование по языкам — LM Studio)
    LLM_BASE_URL: str = Field(
        default="http://localhost:1234/v1",
        description="LM Studio API base URL"
    )
    LLM_BRIDGE_URL: Optional[str] = Field(
        default=None,
        description="Optional remote HTTPS bridge URL for local LLM host"
    )
    LLM_API_KEY: Optional[str] = Field(
        default=None,
        description="API key for OpenAI-compatible endpoint (bridge or cloud provider)"
    )
    LLM_REQUEST_TIMEOUT: int = Field(
        default=120,
        description="Timeout for a single LLM request in seconds"
    )
    LLM_FALLBACK_ENABLED: bool = Field(
        default=True,
        description="Generate template-based quiz when LLM is unavailable"
    )
    QUIZ_TEMPLATE_FALLBACK_ENABLED: bool = Field(
        default=True,
        description="Backward-compatible alias for template fallback toggle in tests"
    )
    LLM_MODEL: str = Field(
        default="qwen2.5-7b-instruct",
        description="LLM model name"
    )

    # Quiz settings (темы и уровни для тестирования по языкам)
    TOPICS: dict = Field(default={
        "English": {
            "A1": [
                "Basic Greetings and Introductions",
                "Colors, Numbers, and Classroom Objects",
                "Family Members and Pets",
                "Food and Drinks",
                "Daily Routines (am/pm, days of week)",
            ],
            "A2": [
                "Present Simple and Present Continuous",
                "Past Simple",
                "Vocabulary: School and Daily Life",
                "Vocabulary: Family, Hobbies, and Travel",
                "Reading Comprehension: Short Texts",
            ],
            "B1": [
                "Present Perfect vs Past Simple",
                "Conditionals (First and Second)",
                "Passive Voice",
                "Vocabulary: Environment and Technology",
                "Reading Comprehension: Articles",
            ],
            "B2": [
                "Advanced Tenses (Perfect Continuous)",
                "Reported Speech",
                "Conditionals (Third, Mixed)",
                "Vocabulary: Academic and Abstract Topics",
                "Reading Comprehension: Complex Texts",
            ],
            "C1": [
                "Subjunctive and Formal Registers",
                "Idiomatic Expressions",
                "Advanced Writing Structures",
                "Nuanced Vocabulary: Synonyms and Collocations",
                "Critical Reading and Inference",
            ],
        },
        "Spanish": {
            "A1": [
                "Basic Vocabulary: Colors, Numbers, Days of the Week",
                "Family and School Vocabulary",
                "Present Tense: Regular Verbs (-ar, -er, -ir)",
                "Greetings and Basic Phrases",
                "Food and Animals Vocabulary",
            ],
            "A1-A2": [
                "Irregular Present Tense (ser, estar, ir, tener)",
                "Basic Past Tense (regular verbs)",
                "Describing People and Places",
                "Shopping and Directions",
                "Weather and Seasons",
            ],
            "A2": [
                "Past Tense: Irregular Verbs",
                "Imperfecto vs Indefinido",
                "Reflexive Verbs",
                "Vocabulary: Travel and Transport",
                "Reading Comprehension: Short Stories",
            ],
            "B1": [
                "Subjuntivo: Present (quiero que, es importante que)",
                "Conditional Tense",
                "Por vs Para",
                "Vocabulary: Work and Professions",
                "Reading: News Articles",
            ],
        },
    })
    LEVEL_DESCRIPTIONS: dict = Field(default={
        "A1": "complete beginner (basic vocabulary, simple present tense, very short sentences)",
        "A1-A2": "elementary learner (basic grammar, simple past tense, can describe familiar topics)",
        "A2": "elementary-intermediate learner (knows basic tenses, everyday vocabulary, simple conversations)",
        "B1": "intermediate learner (can discuss familiar topics, understands main ideas, uses various tenses)",
        "B2": "upper-intermediate learner (can discuss abstract topics, understands complex texts, uses advanced grammar)",
        "C1": "advanced learner (near-native comprehension, nuanced vocabulary, complex grammar structures)",
    })
    QUESTION_COUNTS: list = Field(default=[5, 10, 15, 20])

    # Access Control
    ADMIN_ID: Optional[int] = Field(
        default=None,
        description="Primary admin Telegram ID"
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
