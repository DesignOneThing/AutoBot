from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .models import Listing, Search


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True) if Path(path).parent != Path(".") else None
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.migrate()

    def migrate(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    good_price_enabled INTEGER NOT NULL DEFAULT 1,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    last_checked_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
                );

                CREATE TABLE IF NOT EXISTS seen_listings (
                    search_id INTEGER NOT NULL,
                    listing_id TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    title TEXT,
                    price_eur INTEGER,
                    url TEXT,
                    PRIMARY KEY(search_id, listing_id),
                    FOREIGN KEY(search_id) REFERENCES searches(id)
                );
                """
            )

    def add_chat(self, chat_id: int) -> None:
        with self._conn:
            self._conn.execute("INSERT OR IGNORE INTO chats(chat_id) VALUES (?)", (chat_id,))

    def add_search(
        self,
        chat_id: int,
        name: str,
        url: str,
        interval_seconds: int,
        good_price_enabled: bool,
    ) -> int:
        self.add_chat(chat_id)
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO searches(chat_id, name, url, interval_seconds, good_price_enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, name, url, interval_seconds, int(good_price_enabled)),
            )
        return int(cursor.lastrowid)

    def list_searches(self, chat_id: int | None = None) -> list[Search]:
        query = "SELECT * FROM searches WHERE is_active = 1"
        params: tuple[object, ...] = ()
        if chat_id is not None:
            query += " AND chat_id = ?"
            params = (chat_id,)
        query += " ORDER BY id"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_search(row) for row in rows]

    def get_search(self, search_id: int, chat_id: int | None = None) -> Search | None:
        query = "SELECT * FROM searches WHERE id = ? AND is_active = 1"
        params: tuple[object, ...] = (search_id,)
        if chat_id is not None:
            query += " AND chat_id = ?"
            params = (search_id, chat_id)
        row = self._conn.execute(query, params).fetchone()
        return self._row_to_search(row) if row else None

    def remove_search(self, search_id: int, chat_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE searches SET is_active = 0 WHERE id = ? AND chat_id = ?",
                (search_id, chat_id),
            )
        return cursor.rowcount > 0

    def seen_count(self, search_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM seen_listings WHERE search_id = ?",
            (search_id,),
        ).fetchone()
        return int(row["n"])

    def filter_new(self, search_id: int, listings: Iterable[Listing]) -> list[Listing]:
        new: list[Listing] = []
        with self._conn:
            for listing in listings:
                row = self._conn.execute(
                    "SELECT 1 FROM seen_listings WHERE search_id = ? AND listing_id = ?",
                    (search_id, listing.id),
                ).fetchone()
                if row is None:
                    new.append(listing)
                else:
                    self._conn.execute(
                        """
                        UPDATE seen_listings
                        SET last_seen_at = CURRENT_TIMESTAMP, title = ?, price_eur = ?, url = ?
                        WHERE search_id = ? AND listing_id = ?
                        """,
                        (listing.title, listing.price_eur, listing.url, search_id, listing.id),
                    )
        return new

    def mark_seen(self, search_id: int, listings: Iterable[Listing]) -> None:
        with self._conn:
            for listing in listings:
                self._conn.execute(
                    """
                    INSERT INTO seen_listings(search_id, listing_id, title, price_eur, url)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(search_id, listing_id) DO UPDATE SET
                        last_seen_at = CURRENT_TIMESTAMP,
                        title = excluded.title,
                        price_eur = excluded.price_eur,
                        url = excluded.url
                    """,
                    (search_id, listing.id, listing.title, listing.price_eur, listing.url),
                )
            self._conn.execute(
                "UPDATE searches SET last_checked_at = CURRENT_TIMESTAMP WHERE id = ?",
                (search_id,),
            )

    @staticmethod
    def _row_to_search(row: sqlite3.Row) -> Search:
        return Search(
            id=int(row["id"]),
            chat_id=int(row["chat_id"]),
            name=str(row["name"]),
            url=str(row["url"]),
            interval_seconds=int(row["interval_seconds"]),
            good_price_enabled=bool(row["good_price_enabled"]),
            is_active=bool(row["is_active"]),
        )
