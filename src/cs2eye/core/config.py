from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    app_name: str = "CS2Eye API"
    app_env: str = "local"
    debug: bool = True
    database_url: str = (
        "postgresql+asyncpg://"
        "admin:admin@localhost:5433/cs2eye"
    )
    bo3_api_base_url: str = (
        "https://api.bo3.gg/api/v2"
    )
    bo3_site_base_url: str = "https://bo3.gg"
    bo3_request_timeout_seconds: float = 20.0
    bo3_user_agent: str = (
        "CS2Eye/0.1 (+local analytics project)"
    )
    demo_storage_root: str = "/app/storage"
    demo_max_file_size_bytes: int = 2_147_483_648
    demo_archive_max_depth: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
