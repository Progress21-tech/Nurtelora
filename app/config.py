from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./nurtelora.db"
    phone_hash_secret: str = "development-only-change-me"
    natlas_base_url: str = ""
    natlas_api_key: str = ""
    natlas_model: str = "NCAIR1/N-ATLaS"
    natlas_timeout_seconds: float = 60
    natlas_max_retries: int = 2
    natlas_enabled: bool = False
    natlas_languages: str = ""
    whatsapp_enabled: bool = False
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    meta_graph_api_version: str = ""
    whatsapp_webhook_path: str = "/webhooks/whatsapp"
    max_audio_bytes: int = 16 * 1024 * 1024

    @property
    def configured_languages(self) -> set[str]:
        return {item.strip() for item in self.natlas_languages.split(",") if item.strip() in {"en", "ha", "ig", "yo"}}


@lru_cache
def get_settings() -> Settings:
    return Settings()
