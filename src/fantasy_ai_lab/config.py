import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///fantasy_ai.db"
    PORT: int = 8000
    ENV: str = "development"
    DEFAULT_SEED: int = 123
    GITHUB_TOKEN: str | None = None
    GITHUB_REPOSITORY: str = "ImNacho0/fantasy-ai-lab"
    GITHUB_WORKFLOW: str = "simulate.yml"
    GITHUB_REF: str = "main"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
