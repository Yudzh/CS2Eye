from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = 'cs2eye-api'
    app_env: str = 'local'
    debug: bool = True
    database_url: str = "postgresql+asyncpg://admin:admin@localhost:5433/cs2eye"

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

settings = Settings()