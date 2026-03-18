from typing import Optional

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_DATABASE_URL = "postgresql://user:pass@localhost/zmanage"


class Settings(BaseSettings):
    database_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_DB_URL", "DATABASE_URL"),
    )
    slack_bot_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SLACK_BOT_TOKEN", "SLACK_TOKEN"),
    )
    slack_signing_secret: Optional[str] = None
    openai_api_key: Optional[str] = None
    app_env: str = "development"
    slack_app_token: Optional[str] = None  # For socket mode if needed

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @computed_field
    @property
    def resolved_database_url(self) -> str:
        return self.database_url or DEFAULT_DATABASE_URL


settings = Settings()
