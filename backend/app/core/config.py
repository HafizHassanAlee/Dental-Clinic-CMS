import os
from functools import lru_cache
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR.parent

_ENV_FILES = [
    str(ROOT_DIR / ".env"),
    str(BASE_DIR / ".env"),
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Rumi Dental Care"
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production-64-char-hex-secret"
    CSRF_SECRET: str = "change-me-in-production-64-char-csrf-secret"

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/rumi_dental"
    TEST_DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/rumi_dental_test"

    FRONTEND_URL: str = "http://127.0.0.1:5173"
    BACKEND_URL: str = "http://127.0.0.1:8000"
    ALLOWED_ORIGINS: str = "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173"

    UPLOAD_STORAGE_PATH: str = "./private_uploads"
    MAX_UPLOAD_SIZE_MB: int = 15

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    COOKIE_SECURE: bool = False
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    DEFAULT_CURRENCY: str = "PKR"
    CLINIC_TIMEZONE: str = "Asia/Karachi"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "muhammadhafizhassan228@gmail.com"
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "muhammadhafizhassan228@gmail.com"
    CLINIC_WHATSAPP_NUMBER: str = "+923102468080"
    SMS_PROVIDER_URL: str = ""
    SMS_API_KEY: str = ""

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def private_upload_dir(self) -> Path:
        p = Path(self.UPLOAD_STORAGE_PATH)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
