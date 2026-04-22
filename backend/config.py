from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://tauke:tauke_pass@localhost:5432/taukeai"
    glm_api_key: str = ""
    glm_base_url: str = "https://api.ilmu.ai/anthropic"
    glm_model: str = "ilmu-glm-5.1"
    openweather_api_key: str = ""
    image_upload_dir: str = "./uploads"
    secret_key: str = "change_this_in_production"


settings = Settings()
