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
    rag_api_url: str = "http://localhost:18500"

    # Email delivery (Feature #1)
    resend_api_key: str = ""          # set to a real key in production
    email_from: str = "RevOps IA <noreply@revops.local>"
    backend_public_url: str = "http://localhost:18000"  # used for tracking pixel URLs

    # AI lead scoring (Feature #3)
    openai_api_key: str = ""          # set to a real key in production; empty = heuristic
    lead_score_ttl_seconds: int = 86400  # 24 h Redis TTL for lead scores

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
