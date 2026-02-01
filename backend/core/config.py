from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Interview Scheduling Autopilot"
    base_url: str = "http://127.0.0.1:8000"
    secret_key: str = "dev-secret-change-me"
    timezone: str = "Europe/Moscow"

    database_url: str = "sqlite+aiosqlite:///./backend/data/app.db"

    seed_on_startup: bool = True
    mock_calendar: bool = True
    mock_email: bool = True
    mock_slack: bool = True
    mock_llm: bool = True

    reminder_lead_minutes: int = 60
    feedback_request_delay_minutes: int = 1
    consolidation_delay_minutes: int = 15

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "autopilot@example.com"

    slack_webhook_url: str | None = None

    llm_provider: str = "mock"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    watsonx_api_key: str | None = None
    watsonx_project_id: str | None = None
    watsonx_url: str | None = None
    watsonx_model_id: str | None = None


settings = Settings()

