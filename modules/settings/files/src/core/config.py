"""환경설정 — .env 파일을 읽어 코드에 전달하는 통로 (settings 모듈)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
