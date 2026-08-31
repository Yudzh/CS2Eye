from pydantic import Field
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
    demo_delete_after_successful_parse: bool = False
    demo_parse_concurrency: int = 4
    max_ranking_snapshot_age_days: int = 14
    prediction_history_strong_conflict_threshold: float = Field(default=10.0, ge=0)
    ollama_host: str = Field(default="http://127.0.0.1:11434", min_length=1)
    match_llm_provider: str = Field(default="ollama", min_length=1)
    match_llm_model: str = Field(default="qwen3:8b", min_length=1)
    match_llm_prompt_version: str = Field(default="match_analysis_prompt.v5", min_length=1)
    match_llm_enabled: bool = False
    match_llm_timeout_seconds: float = Field(default=60.0, gt=0)
    match_llm_think: bool = False
    telegram_bot_token: str = ""
    cs2eye_api_base_url: str = "http://127.0.0.1:8000"
    cs2eye_api_timeout_seconds: float = Field(default=15.0, gt=0)
    cs2eye_api_generation_timeout_seconds: float = Field(default=330.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
