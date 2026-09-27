"""Application configuration using Pydantic Settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory for the backend (where .env typically resides)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    APP_NAME: str = "Cold-Chain Monitoring Platform"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # PostgreSQL connection string (SQLAlchemy with psycopg v3)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/coldchain_db"

    # Redis configuration
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Authentication settings
    JWT_SECRET_KEY: str = "CHANGE_ME_TO_A_RANDOM_SECRET_IN_DOT_ENV"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # MQTT Ingestion settings
    MQTT_BROKER_HOST: str = "broker.emqx.io"
    MQTT_BROKER_PORT: int = 1883
    MQTT_USERNAME: str | None = None
    MQTT_PASSWORD: str | None = None
    MQTT_TLS: bool = False
    MQTT_TOPIC_PREFIX: str = "coldchain/trackers"
    MQTT_CLIENT_ID: str | None = None

    # SMTP Alert Email Configuration
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "alerts@swasemi.com"
    SMTP_TLS: bool = False
    ALERT_EMAIL_TO: str = "ops-team@apexpharma.com"
    EMAIL_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=(str(ENV_PATH), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
