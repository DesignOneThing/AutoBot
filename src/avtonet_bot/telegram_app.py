from __future__ import annotations

import asyncio
import html
import logging
import time
from collections import defaultdict

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from .db import Database
from .models import Listing, Search
from .price import PriceInsight, analyze_price
from .scraper import AvtoNetScraper
from .settings import Settings

logger = logging.getLogger(__name__)


class AvtoNetTelegramBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_path)
        self.scraper = AvtoNetScraper(
            timeout_seconds=settings.request_timeout_seconds,
            max_pages=settings.max_pages_per_search,
            proxy_url=settings.scraper_proxy_url,
        )
        self.application = Application.builder().token(settings.telegram_bot_token).build()
        self._last_scan_at: dict[int, float] = defaultdict(float)
        self._register_handlers()

    async def run(self) -> None:
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        background_task = asyncio.create_task(self._background_loop())
        logger.info("Bot started")
        try:
            await asyncio.Event().wait()
        finally:
            background_task.cancel()
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("add_search", self.add_search))
        self.application.add_handler(CommandHandler("list_searches", self.list_searches))
        self.application.add_handler(CommandHandler("remove_search", self.remove_search))
        self.application.add_handler(CommandHandler("scan", self.scan))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        self.db.add_chat(chat_id)
        await update.effective_message.reply_text(_help_text(), disable_web_page_preview=True)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(_help_text(), disable_web_page_preview=True)

    async def add_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        if self.settings.admin_chat_id and chat_id != self.settings.admin_chat_id:
            await update.effective_message.reply_text("Этот бот ограничен админским chat_id.")
            return

        args = context.args
        if len(args) < 2:
            await update.effective_message.reply_text(
                "Формат: /add_search <имя> <url> [минуты] [deal=on|off]"
            )
            return

        url_index = _find_url_arg_index(args)
        if url_index is None:
            await update.effective_message.reply_text("Нужна ссылка поиска с avto.net.")
            return

        name = " ".join(args[:url_index]).strip() or "avto.net"
        url = args[url_index].strip("<>")
        if "avto.net" not in url.lower():
            await update.effective_message.reply_text("Нужна ссылка поиска с avto.net.")
            return

        options = args[url_index + 1 :]
        minutes = _parse_int(options[0], 5) if options and not options[0].startswith("deal=") else 5
        deal_enabled = self.settings.good_price_enabled
        for arg in options:
            if arg.lower() in {"deal=off", "deals=off", "price=off"}:
                deal_enabled = False
            if arg.lower() in {"deal=on", "deals=on", "price=on"}:
                deal_enabled = True

        search_id = self.db.add_search(
            chat_id=chat_id,
            name=name,
            url=url,
            interval_seconds=max(60, minutes * 60),
            good_price_enabled=deal_enabled,
        )

        message = await update.effective_message.reply_text("Добавил поиск. Делаю первичное сканирование...")
        try:
            search = self.db.get_search(search_id, chat_id)
            assert search is not None
            result = await self.scraper.scrape(search.url)
            self.db.mark_seen(search.id, result.listings)
            await message.edit_text(
                f"Готово. Поиск #{search.id} «{search.name}»: "
                f"запомнил {len(result.listings)} текущих объявлений, новые буду присылать."
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Initial scan failed")
            await message.edit_text(f"Поиск сохранен, но первичное сканирование упало: {exc}")

    async def list_searches(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        searches = self.db.list_searches(chat_id)
        if not searches:
            await update.effective_message.reply_text("Активных поисков пока нет.")
            return
        lines = [
            f"#{search.id} {search.name} | каждые {search.interval_seconds // 60} мин | "
            f"цена: {'on' if search.good_price_enabled else 'off'}\n{search.url}"
            for search in searches
        ]
        await update.effective_message.reply_text("\n\n".join(lines), disable_web_page_preview=True)

    async def remove_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        if not context.args:
            await update.effective_message.reply_text("Формат: /remove_search <id>")
            return
        search_id = _parse_int(context.args[0], 0)
        removed = self.db.remove_search(search_id, chat_id)
        await update.effective_message.reply_text("Удалил поиск." if removed else "Не нашел такой активный поиск.")

    async def scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return

        searches: list[Search]
        if context.args:
            search = self.db.get_search(_parse_int(context.args[0], 0), chat_id)
            searches = [search] if search else []
        else:
            searches = self.db.list_searches(chat_id)

        if not searches:
            await update.effective_message.reply_text("Активных поисков для скана нет.")
            return

        await update.effective_message.reply_text("Сканирую...")
        total_new = 0
        for search in searches:
            total_new += await self._scan_search(search, force_notify=True)
        await update.effective_message.reply_text(f"Готово. Новых объявлений: {total_new}.")

    async def _background_loop(self) -> None:
        while True:
            try:
                searches = self.db.list_searches()
                now = time.monotonic()
                for search in searches:
                    if now - self._last_scan_at[search.id] >= search.interval_seconds:
                        self._last_scan_at[search.id] = now
                        await self._scan_search(search, force_notify=False)
                await asyncio.sleep(self.settings.scan_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Background scan loop failed")
                await asyncio.sleep(30)

    async def _scan_search(self, search: Search, force_notify: bool) -> int:
        logger.info("Scanning search %s %s", search.id, search.name)
        result = await self.scraper.scrape(search.url)
        if self.db.seen_count(search.id) == 0 and not force_notify:
            self.db.mark_seen(search.id, result.listings)
            return 0

        new_listings = self.db.filter_new(search.id, result.listings)
        self.db.mark_seen(search.id, result.listings)

        for listing in new_listings:
            insight = (
                analyze_price(listing, result.listings, self.settings.good_price_ratio)
                if search.good_price_enabled
                else PriceInsight(False, None, 0)
            )
            await self.application.bot.send_message(
                chat_id=search.chat_id,
                text=_format_listing(search, listing, insight),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
        return len(new_listings)

    @staticmethod
    def _chat_id(update: Update) -> int | None:
        return update.effective_chat.id if update.effective_chat else None


def _format_listing(search: Search, listing: Listing, insight: PriceInsight) -> str:
    lines = [f"🚗 <b>{html.escape(search.name)}</b>", f"<b>{html.escape(listing.title)}</b>"]
    if listing.price_eur is not None:
        lines.append(f"Цена: {listing.price_eur:,} €".replace(",", " "))
    if listing.year is not None:
        lines.append(f"Год: {listing.year}")
    if listing.mileage_km is not None:
        lines.append(f"Пробег: {listing.mileage_km:,} км".replace(",", " "))
    if insight.is_good_price and insight.median_price_eur:
        lines.append(
            "✅ Хорошая цена: ниже медианы похожих "
            f"({insight.median_price_eur:,} €, {insight.comparable_count} сравн.)".replace(",", " ")
        )
    lines.append(f'<a href="{html.escape(listing.url)}">Открыть объявление</a>')
    return "\n".join(lines)


def _help_text() -> str:
    return (
        "Команды:\n"
        "/add_search <имя> <url> [минуты] [deal=on|off]\n"
        "/list_searches\n"
        "/remove_search <id>\n"
        "/scan [id]\n\n"
        "Как пользоваться: настрой фильтры на avto.net, скопируй URL страницы результатов "
        "и добавь его через /add_search."
    )


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def _find_url_arg_index(args: list[str]) -> int | None:
    for index, arg in enumerate(args):
        cleaned = arg.strip("<>").lower()
        if "avto.net" in cleaned and (cleaned.startswith("http://") or cleaned.startswith("https://")):
            return index
    return None
