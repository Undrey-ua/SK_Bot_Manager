from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field(..., alias="DATABASE_URL")

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_key: str = Field(..., alias="SUPABASE_KEY")
    supabase_storage_bucket: str = Field(
        default="visit-photos",
        alias="SUPABASE_STORAGE_BUCKET",
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    dashboard_password: str = Field(default="", alias="DASHBOARD_PASSWORD")
    dashboard_admin_password: str = Field(default="", alias="DASHBOARD_ADMIN_PASSWORD")
    dashboard_admin_telegram_id: int | None = Field(
        default=None,
        alias="DASHBOARD_ADMIN_TELEGRAM_ID",
    )
    dashboard_secret_key: str = Field(default="", alias="DASHBOARD_SECRET_KEY")
    web_port: int = Field(default=8000, alias="WEB_PORT")

    @field_validator("dashboard_admin_telegram_id", mode="before")
    @classmethod
    def parse_admin_telegram_id(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, value: str) -> str:
        url = value.strip().rstrip("/")
        if "[" in url or "]" in url:
            raise ValueError(
                "SUPABASE_URL містить плейсхолдер [ref]. "
                "Вкажіть реальний URL з Supabase → Settings → API, "
                "наприклад https://abcdefgh.supabase.co"
            )
        if not url.startswith("https://") or not url.endswith(".supabase.co"):
            raise ValueError(
                "SUPABASE_URL має бути https://<project-ref>.supabase.co"
            )
        return url

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        placeholders = ("[ref]", "[password]", "[YOUR-PASSWORD]", "[YOUR_PASSWORD]")
        if any(p in value for p in placeholders):
            raise ValueError(
                "DATABASE_URL містить плейсхолдери [ref] або [password]. "
                "Скопіюйте реальний connection string з Supabase → Connect."
            )
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL має починатися з postgresql+asyncpg://"
            )
        return value

    @field_validator("supabase_key")
    @classmethod
    def validate_supabase_key(cls, value: str) -> str:
        key = value.strip()
        placeholders = (
            "your_service_role",
            "your_anon",
            "anon_key",
            "service_role_or",
            "eyJhbGciOiJIUzI1NiIs",  # приклад у .env.example
        )
        if any(p in key for p in placeholders):
            raise ValueError(
                "SUPABASE_KEY — плейсхолдер. Створіть Secret key: "
                "Supabase → Settings → API Keys → Secret keys → Create / Reveal."
            )
        if key.startswith("sb_publishable"):
            raise ValueError(
                "SUPABASE_KEY: publishable key не підходить для Storage. "
                "Потрібен Secret key (sb_secret_...)."
            )
        is_secret = key.startswith("sb_secret_")
        is_legacy_jwt = key.startswith("eyJ") and key.count(".") >= 2
        if not is_secret and not is_legacy_jwt:
            raise ValueError(
                "SUPABASE_KEY має бути Secret key (sb_secret_...) або legacy service_role (eyJ...)."
            )
        if len(key) < 20:
            raise ValueError("SUPABASE_KEY занадто короткий.")
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
