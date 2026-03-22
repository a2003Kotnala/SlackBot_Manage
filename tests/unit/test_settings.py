from app.config import (
    DEFAULT_DATABASE_URL,
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_GEMINI_MODEL,
    Settings,
)


def test_settings_ignore_placeholder_credentials(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-your-bot-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "your-signing-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "your-openai-key")

    settings = Settings(_env_file=None)

    assert settings.resolved_database_url == DEFAULT_DATABASE_URL
    assert settings.is_postgresql
    assert not settings.slack_configured
    assert not settings.llm_configured
    assert not settings.openai_configured


def test_settings_support_openai_compatible_llm_aliases(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "groq_live_key")
    monkeypatch.setenv("LLM_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")

    settings = Settings(_env_file=None)

    assert settings.llm_configured
    assert settings.openai_configured
    assert settings.resolved_llm_base_url == "https://api.groq.com/openai/v1"
    assert settings.resolved_llm_model == "llama-3.1-8b-instant"
    assert settings.llm_timeout_seconds == 12


def test_settings_infer_openai_compatible_provider_from_openai_aliases(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai_live_key")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai-compatible"


def test_settings_support_gemini_aliases_and_defaults(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_live_key")

    settings = Settings(_env_file=None)

    assert settings.llm_configured
    assert settings.llm_provider == "gemini"
    assert settings.resolved_llm_base_url == DEFAULT_GEMINI_BASE_URL
    assert settings.resolved_llm_model == DEFAULT_GEMINI_MODEL
