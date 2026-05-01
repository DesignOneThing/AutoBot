from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    admin_chat_id: int | None
    database_path: str = "avtonet_bot.sqlite3"
    scan_interval_seconds: int = 300
    request_timeout_seconds: int = 30
    max_pages_per_search: int = 3
    good_price_enabled: bool = True
    good_price_ratio: float = 0.88
    scraper_proxy_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

        admin_chat_id_raw = os.getenv("ADMIN_CHAT_ID", "").strip()
        admin_chat_id = int(admin_chat_id_raw) if admin_chat_id_raw else None

        return cls(
            telegram_bot_token=token,
            admin_chat_id=admin_chat_id,
            database_path=os.getenv("DATABASE_PATH", "avtonet_bot.sqlite3"),
            scan_interval_seconds=int(os.getenv("SCAN_INTERVAL_SECONDS", "300")),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            max_pages_per_search=int(os.getenv("MAX_PAGES_PER_SEARCH", "3")),
            good_price_enabled=_bool_env("GOOD_PRICE_ENABLED", True),
            good_price_ratio=float(os.getenv("GOOD_PRICE_RATIO", "0.88")),
            scraper_proxy_url=os.getenv("SCRAPER_PROXY_URL", "").strip() or None,
        )
