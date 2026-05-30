from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

import duckdb


class AppDatabase:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db_path = data_dir / "sjhl.duckdb"
        self._lock = threading.RLock()
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(str(self.db_path))
            self._init_schema()
        return self._conn

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None):
        with self._lock:
            return self.conn.execute(sql, params or [])

    def query(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self.conn.execute(sql, params or [])
            columns = [column[0] for column in cursor.description or []]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_fingerprints (
              id VARCHAR PRIMARY KEY,
              algorithm VARCHAR NOT NULL,
              hash VARCHAR NOT NULL,
              size BIGINT NOT NULL,
              key VARCHAR NOT NULL,
              source_type VARCHAR DEFAULT '',
              profile_id VARCHAR DEFAULT '',
              remote_path VARCHAR DEFAULT '',
              file_name VARCHAR DEFAULT '',
              item_id VARCHAR DEFAULT '',
              web_url VARCHAR DEFAULT '',
              scanned_at VARCHAR DEFAULT '',
              created_at VARCHAR NOT NULL,
              updated_at VARCHAR NOT NULL,
              metadata JSON DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS transfer_jobs (
              id VARCHAR PRIMARY KEY,
              type VARCHAR NOT NULL,
              status VARCHAR NOT NULL,
              requested_profile_id VARCHAR DEFAULT '',
              profile_id VARCHAR DEFAULT '',
              profile_name VARCHAR DEFAULT '',
              file_path VARCHAR DEFAULT '',
              source_url VARCHAR DEFAULT '',
              source_headers JSON DEFAULT '{}',
              source_provider VARCHAR DEFAULT '',
              source_pick_code VARCHAR DEFAULT '',
              source_cookie VARCHAR DEFAULT '',
              source_access_token VARCHAR DEFAULT '',
              source_refresh_token VARCHAR DEFAULT '',
              source_user_agent VARCHAR DEFAULT '',
              file_name VARCHAR DEFAULT '',
              remote_dir VARCHAR DEFAULT '',
              remote_path VARCHAR DEFAULT '',
              size BIGINT DEFAULT 0,
              sha1 VARCHAR DEFAULT '',
              sha256 VARCHAR DEFAULT '',
              conflict_behavior VARCHAR DEFAULT 'fail',
              dedupe_scope VARCHAR DEFAULT 'global',
              uploaded BIGINT DEFAULT 0,
              total BIGINT DEFAULT 0,
              percent INTEGER DEFAULT 0,
              attempts INTEGER DEFAULT 0,
              max_attempts INTEGER DEFAULT 3,
              next_attempt_at VARCHAR DEFAULT '',
              last_error VARCHAR DEFAULT '',
              logs JSON DEFAULT '[]',
              result JSON DEFAULT '{}',
              created_at VARCHAR NOT NULL,
              updated_at VARCHAR NOT NULL,
              started_at VARCHAR DEFAULT '',
              finished_at VARCHAR DEFAULT ''
            );
            """
        )
        self._conn.execute("DROP INDEX IF EXISTS transfer_jobs_status_idx")
        self._conn.execute("DROP INDEX IF EXISTS media_fingerprints_location_uq")
        self._conn.execute("DROP INDEX IF EXISTS media_fingerprints_lookup_idx")
        self._conn.execute("ALTER TABLE transfer_jobs ADD COLUMN IF NOT EXISTS source_refresh_token VARCHAR DEFAULT ''")
        self._conn.execute("ALTER TABLE transfer_jobs ADD COLUMN IF NOT EXISTS download_speed BIGINT DEFAULT 0")
        self._conn.execute("ALTER TABLE transfer_jobs ADD COLUMN IF NOT EXISTS downloaded BIGINT DEFAULT 0")
        self._conn.execute("ALTER TABLE transfer_jobs ADD COLUMN IF NOT EXISTS staged_path VARCHAR DEFAULT ''")


def new_id() -> str:
    return str(uuid.uuid4())


def json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def json_loads(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback
