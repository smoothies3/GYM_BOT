from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    DATABASE_URL: str

    PAYMENT_PROVIDER_TOKEN: str = ""
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""

    # Stored as plain string in .env: "123456789" or "111,222,333"
    ADMIN_IDS: str = ""

    @field_validator("BOT_TOKEN", mode="before")
    @classmethod
    def strip_token(cls, v: Any) -> str:
        return str(v).strip()

    def get_admin_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip().isdigit()]


settings = Settings()
