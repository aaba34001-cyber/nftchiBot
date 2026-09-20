from decimal import Decimal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    PLATFORM_ADMIN_USERNAME: str = "man_admin"
    ADMIN_IDS: list[int] = []
    DATABASE_URL: str = "sqlite+aiosqlite:///./nft_bot.db"
    COMMISSION_RATE: Decimal = Decimal("0.01")
    AD_INTERVAL_MINUTES: int = 10
    LIMITS_ENABLED: bool = False
    AUTO_APPROVE: bool = False
    DELETE_OLD_LISTINGS: bool = False
    SHOW_PENDING: bool = True
    EXPIRATION_DAYS: int = 3
    BASE_MAX_ACTIVE: int = 3
    BASE_DAILY_LIMIT: int = 3
    REFERRAL_BONUS: int = 1
    TIMEZONE: str = "Asia/Tashkent"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


config = Settings()
