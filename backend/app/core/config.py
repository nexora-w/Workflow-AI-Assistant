"""Application configuration via environment variables."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central config; loads from env and .env."""

    app_name: str = "Handbook Project API"
    debug: bool = False

    # Database (env: DATABASE_URL)
    database_url: str | None = None

    # Auth
    secret_key: str = "your-secret-key-please-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # OpenAI
    openai_api_key: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_database_url(self) -> str:
        """Build DATABASE_URL from env, with Railway and local fallbacks."""
        url = self.database_url or os.getenv("DATABASE_URL")
        if url:
            if url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql://", 1)
            return url

        mysql_host = os.getenv("MYSQLHOST")
        if mysql_host:
            mysql_user = os.getenv("MYSQLUSER", "root")
            mysql_password = os.getenv("MYSQLPASSWORD", "")
            mysql_port = os.getenv("MYSQLPORT", "3306")
            mysql_database = os.getenv("MYSQLDATABASE", "railway")
            return (
                f"mysql+pymysql://{mysql_user}:{mysql_password}"
                f"@{mysql_host}:{mysql_port}/{mysql_database}"
            )

        return "mysql+pymysql://root:password@localhost:3306/handbook_db"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
