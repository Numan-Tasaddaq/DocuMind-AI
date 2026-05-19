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

    frontend_auth_callback_url: str = Field(
        default="http://127.0.0.1:5500/frontend/index.html",
        alias="FRONTEND_AUTH_CALLBACK_URL",
    )
    oauth_state_ttl_seconds: int = Field(default=600, alias="OAUTH_STATE_TTL_SECONDS")

    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/auth/oauth/google/callback",
        alias="GOOGLE_REDIRECT_URI",
    )

    github_client_id: str = Field(default="", alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", alias="GITHUB_CLIENT_SECRET")
    github_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/auth/oauth/github/callback",
        alias="GITHUB_REDIRECT_URI",
    )

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
