import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_ID: int
    DATABASE_URL: str
    PORT: int = 10000

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()