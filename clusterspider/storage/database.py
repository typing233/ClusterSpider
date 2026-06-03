import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

from clusterspider.core.module_base import ModuleResult
from clusterspider.core.task import Task

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    target_type TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    modules_total INTEGER DEFAULT 0,
    modules_completed INTEGER DEFAULT 0,
    modules_failed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    module_name TEXT NOT NULL,
    target TEXT NOT NULL,
    target_type TEXT NOT NULL,
    success INTEGER NOT NULL,
    data TEXT,
    error TEXT,
    timestamp TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    result_id INTEGER,
    entity_type TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (result_id) REFERENCES results(id)
);

CREATE INDEX IF NOT EXISTS idx_results_task ON results(task_id);
CREATE INDEX IF NOT EXISTS idx_entities_task ON entities(task_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_value ON entities(value);
"""


class Database:
    def __init__(self, db_path: str = "clusterspider.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info(f"Database initialized at {self.db_path.absolute()}")

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def save_task(self, task: Task):
        self.conn.execute(
            """INSERT OR REPLACE INTO tasks
               (id, target, target_type, state, created_at, started_at, finished_at,
                modules_total, modules_completed, modules_failed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.target, task.target_type.value, task.state.value,
             task.created_at, task.started_at, task.finished_at,
             task.modules_total, task.modules_completed, task.modules_failed),
        )

        for result in task.results:
            cursor = self.conn.execute(
                """INSERT INTO results (task_id, module_name, target, target_type, success, data, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (task.id, result.module_name, result.target, result.target_type,
                 1 if result.success else 0, json.dumps(result.data, ensure_ascii=False),
                 result.error, result.timestamp),
            )
            result_id = cursor.lastrowid

            for entity in result.entities:
                self.conn.execute(
                    """INSERT INTO entities (task_id, result_id, entity_type, value, source)
                       VALUES (?, ?, ?, ?, ?)""",
                    (task.id, result_id, entity["type"], entity["value"], entity.get("source")),
                )

        self.conn.commit()
        logger.info(f"Task {task.id} saved to database")

    def get_task(self, task_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        task_dict = dict(row)
        results = self.conn.execute(
            "SELECT * FROM results WHERE task_id = ?", (task_id,)
        ).fetchall()
        task_dict["results"] = []
        for r in results:
            rd = dict(r)
            rd["data"] = json.loads(rd["data"]) if rd["data"] else {}
            rd["success"] = bool(rd["success"])
            entities = self.conn.execute(
                "SELECT * FROM entities WHERE result_id = ?", (rd["id"],)
            ).fetchall()
            rd["entities"] = [dict(e) for e in entities]
            task_dict["results"].append(rd)
        return task_dict

    def query_entities(self, entity_type: str | None = None, value: str | None = None) -> list[dict]:
        query = "SELECT * FROM entities WHERE 1=1"
        params = []
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        if value:
            query += " AND value LIKE ?"
            params.append(f"%{value}%")
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
