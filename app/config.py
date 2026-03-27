from pydantic import (
    AliasChoices,
    Field,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg2://postgres:postgres@localhost:5432/followthru"
)
DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
PLACEHOLDER_MARKERS = (
    "your-",
    "your_",
    "replace-",
    "replace_",
    "placeholder",
    "changeme",
)


def _normalize_optional_setting(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return None
    return normalized


def _normalize_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class Settings(BaseSettings):
    app_name: str = "FollowThru"
    app_version: str = "1.0.0"
    app_env: str = "development"
    log_level: str = "INFO"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "SUPABASE_DB_URL"),
    )
    slack_bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SLACK_BOT_TOKEN", "SLACK_TOKEN"),
    )
    slack_signing_secret: str | None = None
    slack_app_token: str | None = None
    llm_provider: str = "openai-compatible"
    llm_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_BASE_URL", "OPENAI_BASE_URL", "GEMINI_BASE_URL"
        ),
    )
    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"
        ),
    )
    llm_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_MODEL", "GEMINI_MODEL", "OPENAI_MODEL"),
    )
    llm_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("LLM_TIMEOUT_SECONDS", "OPENAI_TIMEOUT_SECONDS"),
    )
    slack_publish_drafts: bool = True
    primary_slack_command: str = "/followthru"
    legacy_slack_command: str = "/zmanage"
    followthru_chat_history_limit: int = 12

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def infer_llm_provider(cls, data):
        if not isinstance(data, dict):
            return data

        if data.get("llm_provider") or data.get("LLM_PROVIDER"):
            return data

        if any(
            data.get(key)
            for key in ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_BASE_URL")
        ):
            data["llm_provider"] = "gemini"
            return data

        if any(
            data.get(key)
            for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL")
        ):
            data["llm_provider"] = "openai-compatible"
        return data

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str | None:
        return _normalize_optional_value(value)

    @field_validator(
        "slack_bot_token",
        "slack_signing_secret",
        "slack_app_token",
        #"llm_api_key",
        mode="before",
    )
    @classmethod
    def normalize_secret_settings(cls, value: str | None) -> str | None:
        return _normalize_optional_setting(value)

    @computed_field
    @property
    def resolved_database_url(self) -> str:
        return self.database_url or DEFAULT_DATABASE_URL

    @computed_field
    @property
    def is_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite")

    @computed_field
    @property
    def is_postgresql(self) -> bool:
        return self.resolved_database_url.startswith("postgresql")

    @computed_field
    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_bot_token and self.slack_signing_secret)

    @computed_field
    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @computed_field
    @property
    def resolved_llm_base_url(self) -> str:
        if self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        if self.llm_provider.lower() == "gemini":
            return DEFAULT_GEMINI_BASE_URL
        return DEFAULT_OPENAI_COMPATIBLE_BASE_URL

    @computed_field
    @property
    def resolved_llm_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        if self.llm_provider.lower() == "gemini":
            return DEFAULT_GEMINI_MODEL
        return DEFAULT_OPENAI_MODEL

    @computed_field
    @property
    def openai_configured(self) -> bool:
        return self.llm_configured

    @property
    def openai_api_key(self) -> str | None:
        return self.llm_api_key

    @property
    def openai_model(self) -> str:
        return self.resolved_llm_model

    @property
    def openai_timeout_seconds(self) -> float:
        return self.llm_timeout_seconds

    @field_serializer(
        "slack_bot_token",
        "slack_signing_secret",
        "slack_app_token",
    )
    def serialize_sensitive_values(self, value: str | None):
        return value


settings = Settings()