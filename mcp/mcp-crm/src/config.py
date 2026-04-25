from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    BACKEND_URL: str
    INTERNAL_API_KEY: str
    PORT: int = 9001
    LOG_LEVEL: str = "INFO"
    HTTP_TIMEOUT: float = 10.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
