from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from jarvis.models import Analysis, Draft, Event, Listing, utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(marketplace, external_id)
);
CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    search_run_id INTEGER REFERENCES search_runs(id),
    price INTEGER NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    score REAL NOT NULL,
    reference_median INTEGER,
    discount_ratio REAL,
    reference_count INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_url TEXT NOT NULL,
    text TEXT NOT NULL,
    approved_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def create_search_run(self, query: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO search_runs(query, created_at) VALUES (?, ?)", (query, utc_now())
            )
            return int(cursor.lastrowid)

    def save_listing(self, listing: Listing, search_run_id: int | None = None) -> int:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO listings(
                    marketplace, external_id, title, url, description, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(marketplace, external_id) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    description = excluded.description,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    listing.marketplace,
                    listing.external_id,
                    listing.title,
                    listing.url,
                    listing.description,
                    listing.observed_at,
                    listing.observed_at,
                ),
            )
            row = connection.execute(
                "SELECT id FROM listings WHERE marketplace = ? AND external_id = ?",
                (listing.marketplace, listing.external_id),
            ).fetchone()
            listing_id = int(row["id"])
            connection.execute(
                """
                INSERT INTO price_observations(listing_id, search_run_id, price, observed_at)
                VALUES (?, ?, ?, ?)
                """,
                (listing_id, search_run_id, listing.price, listing.observed_at),
            )
            return listing_id

    def save_analysis(self, listing_id: int, analysis: Analysis) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO analyses(
                    listing_id, score, reference_median, discount_ratio, reference_count,
                    confidence, reasons_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing_id,
                    analysis.score,
                    analysis.reference_median,
                    analysis.discount_ratio,
                    analysis.reference_count,
                    analysis.confidence,
                    json.dumps(analysis.reasons, ensure_ascii=False),
                    utc_now(),
                ),
            )

    def previous_observed_prices(self, exclude_search_run_id: int, limit: int = 500) -> list[int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT price
                FROM price_observations
                WHERE search_run_id IS NULL OR search_run_id != ?
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (exclude_search_run_id, limit),
            ).fetchall()
        return [int(row["price"]) for row in rows]

    def save_draft(self, draft: Draft) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO drafts(listing_url, text, approved_at, created_at) VALUES (?, ?, ?, ?)",
                (draft.listing_url, draft.text, draft.approved_at, draft.created_at),
            )
            return int(cursor.lastrowid)

    def save_event(self, event: Event) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO event_logs(category, message, details_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.category,
                    event.message,
                    json.dumps(event.details, ensure_ascii=False),
                    event.created_at,
                ),
            )
