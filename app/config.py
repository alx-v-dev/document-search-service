from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Document Search Service"
    postgres_dsn: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/document_search"
    )
    elasticsearch_url: str = "http://localhost:9200"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
