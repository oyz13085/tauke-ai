from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://tauke:tauke_pass@localhost:5432/taukeai"
    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    openweather_api_key: str = ""
    image_upload_dir: str = "./uploads"
    secret_key: str = "change_this_in_production"

    class Config:
        env_file = ".env"


settings = Settings()
