from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")

    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="documind_ai", alias="DB_NAME")
    db_user: str = Field(default="documind_app", alias="DB_USER")
    db_password: str = Field(default="change_me", alias="DB_PASSWORD")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    jwt_secret: str = Field(default="change_this_to_a_long_random_secret", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expires_minutes: int = Field(default=30, alias="JWT_EXPIRES_MINUTES")

    password_min_length: int = Field(default=8, alias="PASSWORD_MIN_LENGTH")
    max_login_attempts: int = Field(default=5, alias="MAX_LOGIN_ATTEMPTS")
    account_lock_minutes: int = Field(default=15, alias="ACCOUNT_LOCK_MINUTES")

    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
