from pydantic import BaseSettings

class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 30
    internal_secret: str
    orchestrator_url: str

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
