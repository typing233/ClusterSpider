import sqlite3
import uuid
import logging
from datetime import datetime
from dataclasses import dataclass

from clusterspider.config import settings
from clusterspider.auth.passwords import hash_password, verify_password

logger = logging.getLogger(__name__)

USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    encrypted_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS scan_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    target TEXT NOT NULL,
    target_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    module_names TEXT,
    modules_total INTEGER DEFAULT 0,
    modules_completed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    result_summary TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_scan_history_user ON scan_history(user_id, created_at);
"""


@dataclass
class User:
    id: str
    username: str
    email: str
    password_hash: str
    is_active: bool = True
    is_admin: bool = False
    created_at: str = ""
    last_login: str | None = None


@dataclass
class UserCreate:
    username: str
    email: str
    password: str


class UserRepository:
    def __init__(self, db_path: str | None = None):
        path = db_path or settings.sqlite_path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(USER_SCHEMA)
        self.conn.commit()

    def create_user(self, data: UserCreate) -> User:
        user_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        pw_hash = hash_password(data.password)

        self.conn.execute(
            "INSERT INTO users (id, username, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, data.username, data.email.lower(), pw_hash, now),
        )
        self.conn.commit()
        return User(id=user_id, username=data.username, email=data.email.lower(),
                    password_hash=pw_hash, created_at=now)

    def get_by_username(self, username: str) -> User | None:
        row = self.conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            return self._row_to_user(row)
        return None

    def get_by_email(self, email: str) -> User | None:
        row = self.conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        if row:
            return self._row_to_user(row)
        return None

    def get_by_id(self, user_id: str) -> User | None:
        row = self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            return self._row_to_user(row)
        return None

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.get_by_username(username)
        if not user:
            user = self.get_by_email(username)
        if user and verify_password(password, user.password_hash):
            self.conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), user.id),
            )
            self.conn.commit()
            return user
        return None

    def store_api_key(self, user_id: str, service_name: str, encrypted_key: str) -> str:
        key_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT INTO api_keys (id, user_id, service_name, encrypted_key, created_at) VALUES (?, ?, ?, ?, ?)",
            (key_id, user_id, service_name, encrypted_key, now),
        )
        self.conn.commit()
        return key_id

    def get_api_keys(self, user_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, service_name, created_at FROM api_keys WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_api_key(self, key_id: str, user_id: str) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM api_keys WHERE id = ? AND user_id = ?",
            (key_id, user_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def create_scan_record(
        self, user_id: str, task_id: str, target: str, target_type: str, module_names: list[str] | None = None
    ) -> str:
        scan_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        import json
        modules_json = json.dumps(module_names) if module_names else None
        self.conn.execute(
            "INSERT INTO scan_history (id, user_id, task_id, target, target_type, status, module_names, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)",
            (scan_id, user_id, task_id, target, target_type, modules_json, now),
        )
        self.conn.commit()
        return scan_id

    def update_scan_status(self, task_id: str, status: str, modules_total: int = 0,
                           modules_completed: int = 0, result_summary: str | None = None):
        import json
        fields = ["status = ?"]
        params: list = [status]
        if modules_total:
            fields.append("modules_total = ?")
            params.append(modules_total)
        if modules_completed:
            fields.append("modules_completed = ?")
            params.append(modules_completed)
        if result_summary:
            fields.append("result_summary = ?")
            params.append(result_summary)
        if status in ("COMPLETED", "FAILED"):
            fields.append("finished_at = ?")
            params.append(datetime.utcnow().isoformat())
        params.append(task_id)
        self.conn.execute(
            f"UPDATE scan_history SET {', '.join(fields)} WHERE task_id = ?",
            params,
        )
        self.conn.commit()

    def get_scan_history(self, user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scan_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_scan_by_task_id(self, task_id: str, user_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM scan_history WHERE task_id = ? AND user_id = ?",
            (task_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def _row_to_user(self, row) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            is_active=bool(row["is_active"]),
            is_admin=bool(row["is_admin"]),
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    def close(self):
        self.conn.close()
