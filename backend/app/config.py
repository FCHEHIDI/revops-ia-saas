from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    internal_secret: str
    orchestrator_url: str
    environment: str = "development"

    internal_api_key: str = ""
    redis_url: str | None = None
    mcp_inter_service_secret: str = "dev-internal-key-change-me"

    @property
    def SECRET_KEY(self) -> str:  # noqa: N802
        return self.jwt_secret

    @property
    def ENVIRONMENT(self) -> str:  # noqa: N802
        return self.environment


settings = Settings()  # type: ignore[call-arg]

if hasattr(settings, 'environment') and settings.environment == "production":
    if not settings.internal_api_key:
        import warnings
        warnings.warn("INTERNAL_API_KEY is empty in production! Security risk.")
