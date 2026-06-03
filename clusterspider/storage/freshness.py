import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

from clusterspider.config import settings

logger = logging.getLogger(__name__)

FRESHNESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    last_collected_at TEXT NOT NULL,
    UNIQUE(source, entity_type, entity_value)
);
CREATE INDEX IF NOT EXISTS idx_collection_log_lookup
    ON collection_log(source, entity_type, entity_value);
"""


class FreshnessTracker:
    def __init__(self, db_path: str | None = None):
        path = db_path or settings.sqlite_path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(FRESHNESS_SCHEMA)
        self.conn.commit()

    def is_fresh(self, source: str, entity_type: str, entity_value: str) -> bool:
        row = self.conn.execute(
            "SELECT last_collected_at FROM collection_log "
            "WHERE source = ? AND entity_type = ? AND entity_value = ?",
            (source, entity_type, entity_value.lower()),
        ).fetchone()

        if not row:
            return False

        last = datetime.fromisoformat(row["last_collected_at"])
        threshold = datetime.utcnow() - timedelta(hours=settings.freshness_window_hours)
        return last > threshold

    def mark_collected(self, source: str, entity_type: str, entity_value: str):
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT INTO collection_log (source, entity_type, entity_value, last_collected_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(source, entity_type, entity_value) "
            "DO UPDATE SET last_collected_at = excluded.last_collected_at",
            (source, entity_type, entity_value.lower(), now),
        )
        self.conn.commit()

    def get_last_collected(self, source: str, entity_type: str, entity_value: str) -> datetime | None:
        row = self.conn.execute(
            "SELECT last_collected_at FROM collection_log "
            "WHERE source = ? AND entity_type = ? AND entity_value = ?",
            (source, entity_type, entity_value.lower()),
        ).fetchone()
        if row:
            return datetime.fromisoformat(row["last_collected_at"])
        return None

    def close(self):
        self.conn.close()
