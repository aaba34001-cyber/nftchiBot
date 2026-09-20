from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    BOT_TOKEN: str
    PLATFORM_ADMIN_USERNAME: str = "man_adminn"
    ADMIN_IDS: List[int] = []
    DATABASE_URL: str = "sqlite+aiosqlite:///./nft_bot.db"
    AD_INTERVAL_MINUTES: int = 10
    AUTO_APPROVE: bool = False
    SHOW_PENDING: bool = False
    EXPIRATION_DAYS: int = 3

config = Settings()
