"""Application configuration via pydantic-settings, reading from .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    default_model: str = "gpt-4o"
    output_dir: str = "output_files"
    max_content_loop_iterations: int = 3
    max_compile_loop_iterations: int = 5
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
