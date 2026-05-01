from __future__ import annotations

import asyncio
import logging

from .settings import Settings
from .telegram_app import AvtoNetTelegramBot


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    bot = AvtoNetTelegramBot(settings)
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
