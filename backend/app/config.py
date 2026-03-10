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

    @property
    def SECRET_KEY(self) -> str:  # noqa: N802
        return self.jwt_secret

    @property
    def ENVIRONMENT(self) -> str:  # noqa: N802
        return self.environment


settings = Settings()  # type: ignore[call-arg]
