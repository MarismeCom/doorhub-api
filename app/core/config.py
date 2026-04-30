from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql://admin:password@localhost:5432/doorhub"
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ZK_DEVICE_IPS: str = "192.168.1.201"
    ZK_DEVICE_PORT: int = 4370
    ZK_DEVICE_TIMEOUT: int = 5
    ZK_DEVICE_ENCODING: str = "gbk"
    ZK_DEVICE_OMIT_PING: bool = False
    RATE_LIMIT_PER_MINUTE: int = 100
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_RELOAD: bool = False
    APP_TIMEZONE: str = "Asia/Shanghai"
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_VERIFICATION_TOKEN: str = ""
    FEISHU_ENCRYPT_KEY: str = ""
    FEISHU_ENABLE_LONG_CONNECTION: bool = False
    FEISHU_EVENT_SUBSCRIPTIONS: str = "approval.approval.updated_v4,application.bot.menu_v6"
    FEISHU_LOG_LEVEL: str = "INFO"
    FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY: str = "door_open"
    FEISHU_BOT_MENU_DOOR_OPEN_DEVICE_IP: str = ""
    FEISHU_BOT_MENU_DOOR_OPEN_SECONDS: int = 3
    FEISHU_BOT_MENU_NOTIFY_OPERATOR: bool = False
    FEISHU_BOT_MENU_DEVICE_EVENT_MAP: str = ""
    FEISHU_BOT_MENU_ALLOWED_OPEN_IDS: str = ""
    FEISHU_BOT_MENU_ALLOWED_USER_IDS: str = ""
    ATTENDANCE_PLAN_START: str = "09:00"
    ATTENDANCE_PLAN_END: str = "18:00"
    ATTENDANCE_WORKDAY_PROVIDER: str = "ailcc"
    ATTENDANCE_WORKDAY_API_URL: str = ""
    ATTENDANCE_AILCC_API_BASE_URL: str = "https://holiday.ailcc.com"
    ATTENDANCE_AILCC_API_TOKEN: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
