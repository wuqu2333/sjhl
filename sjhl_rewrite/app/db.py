from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

import duckdb

from .utils import json_dumps, json_loads, now_iso


def new_id() -> str:
    return str(uuid.uuid4())


class Database:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db_path = data_dir / "sjhl_rewrite.duckdb"
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

    def one(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sp_profiles (
              id VARCHAR PRIMARY KEY,
              name VARCHAR NOT NULL,
              tenant_id VARCHAR NOT NULL,
              client_id VARCHAR NOT NULL,
              client_secret VARCHAR DEFAULT '',
              drive_id VARCHAR NOT NULL,
              root_path VARCHAR DEFAULT '',
              graph_base_url VARCHAR DEFAULT '',
              auth_base_url VARCHAR DEFAULT '',
              enabled BOOLEAN DEFAULT TRUE,
              created_at VARCHAR NOT NULL,
              updated_at VARCHAR NOT NULL,
              metadata JSON DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS pan115_accounts (
              id VARCHAR PRIMARY KEY,
              name VARCHAR NOT NULL,
              cookie VARCHAR DEFAULT '',
              access_token VARCHAR DEFAULT '',
              refresh_token VARCHAR DEFAULT '',
              user_agent VARCHAR DEFAULT '',
              created_at VARCHAR NOT NULL,
              updated_at VARCHAR NOT NULL,
              metadata JSON DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS transfer_jobs (
              id VARCHAR PRIMARY KEY,
              type VARCHAR NOT NULL,
              status VARCHAR NOT NULL,
              phase VARCHAR DEFAULT '',
              profile_id VARCHAR DEFAULT '',
              account_id VARCHAR DEFAULT '',
              source_provider VARCHAR DEFAULT '',
              source_pick_code VARCHAR DEFAULT '',
              source_url VARCHAR DEFAULT '',
              source_headers JSON DEFAULT '{}',
              file_path VARCHAR DEFAULT '',
              file_name VARCHAR NOT NULL,
              remote_dir VARCHAR DEFAULT '',
              remote_path VARCHAR DEFAULT '',
              size BIGINT DEFAULT 0,
              sha1 VARCHAR DEFAULT '',
              sha256 VARCHAR DEFAULT '',
              uploaded BIGINT DEFAULT 0,
              total BIGINT DEFAULT 0,
              percent INTEGER DEFAULT 0,
              speed_bps DOUBLE DEFAULT 0,
              attempts INTEGER DEFAULT 0,
              max_attempts INTEGER DEFAULT 3,
              last_error VARCHAR DEFAULT '',
              logs JSON DEFAULT '[]',
              result JSON DEFAULT '{}',
              created_at VARCHAR NOT NULL,
              updated_at VARCHAR NOT NULL,
              started_at VARCHAR DEFAULT '',
              finished_at VARCHAR DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS fingerprints (
              id VARCHAR PRIMARY KEY,
              key VARCHAR NOT NULL,
              file_name VARCHAR NOT NULL,
              size BIGINT DEFAULT 0,
              sha1 VARCHAR DEFAULT '',
              sha256 VARCHAR DEFAULT '',
              profile_id VARCHAR DEFAULT '',
              remote_path VARCHAR DEFAULT '',
              source_type VARCHAR DEFAULT '',
              created_at VARCHAR NOT NULL,
              updated_at VARCHAR NOT NULL,
              metadata JSON DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS settings (
              key VARCHAR PRIMARY KEY,
              value JSON NOT NULL,
              updated_at VARCHAR NOT NULL
            );
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS transfer_jobs_status_idx ON transfer_jobs(status)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS fingerprints_key_idx ON fingerprints(key)")


class Store:
    def __init__(self, db: Database):
        self.db = db

    def get_settings(self) -> dict[str, Any]:
        rows = self.db.query("SELECT key, value FROM settings")
        settings = {row["key"]: json_loads(row["value"], None) for row in rows}
        settings.setdefault("transferConcurrency", 4)
        settings.setdefault("downloadDir", "")
        settings.setdefault("minFreeSpaceGb", 2)
        settings.setdefault("dailyUploadLimitEnabled", False)
        settings.setdefault("dailyUploadLimitBytes", 0)
        return settings

    def set_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        for key, value in patch.items():
            self.db.execute(
                "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                [key, json_dumps(value), now],
            )
        return self.get_settings()

    def list_profiles(self, with_secret: bool = False) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM sp_profiles ORDER BY created_at DESC")
        if not with_secret:
            for row in rows:
                if row.get("client_secret"):
                    row["client_secret"] = "***"
        return rows

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM sp_profiles WHERE id = ?", [profile_id])

    def upsert_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        profile_id = data.get("id") or new_id()
        existing = self.get_profile(profile_id)
        row = {
            "id": profile_id,
            "name": data.get("name") or "SP",
            "tenant_id": data.get("tenant_id") or data.get("tenantId") or "",
            "client_id": data.get("client_id") or data.get("clientId") or "",
            "client_secret": data.get("client_secret") or data.get("clientSecret") or (existing or {}).get("client_secret", ""),
            "drive_id": data.get("drive_id") or data.get("driveId") or "",
            "root_path": data.get("root_path") or data.get("rootPath") or "",
            "graph_base_url": data.get("graph_base_url") or data.get("graphBaseUrl") or "",
            "auth_base_url": data.get("auth_base_url") or data.get("authBaseUrl") or "",
            "enabled": bool(data.get("enabled", True)),
            "created_at": (existing or {}).get("created_at", now),
            "updated_at": now,
            "metadata": json_dumps(data.get("metadata") or {}),
        }
        self.db.execute(
            """
            INSERT OR REPLACE INTO sp_profiles (
              id, name, tenant_id, client_id, client_secret, drive_id, root_path,
              graph_base_url, auth_base_url, enabled, created_at, updated_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            list(row.values()),
        )
        return self.get_profile(profile_id) or row

    def delete_profile(self, profile_id: str) -> None:
        self.db.execute("DELETE FROM sp_profiles WHERE id = ?", [profile_id])

    def list_accounts(self, with_secret: bool = False) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM pan115_accounts ORDER BY created_at DESC")
        if not with_secret:
            for row in rows:
                for key in ("cookie", "access_token", "refresh_token"):
                    if row.get(key):
                        row[key] = "***"
        return rows

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM pan115_accounts WHERE id = ?", [account_id])

    def upsert_account(self, data: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        account_id = data.get("id") or new_id()
        existing = self.get_account(account_id)
        access_token = data.get("access_token") if "access_token" in data else data.get("accessToken")
        refresh_token = data.get("refresh_token") if "refresh_token" in data else data.get("refreshToken")
        row = {
            "id": account_id,
            "name": data.get("name") or "115账号",
            "cookie": data.get("cookie") if data.get("cookie") not in (None, "***") else (existing or {}).get("cookie", ""),
            "access_token": access_token if access_token not in (None, "***") else (existing or {}).get("access_token", ""),
            "refresh_token": refresh_token if refresh_token not in (None, "***") else (existing or {}).get("refresh_token", ""),
            "user_agent": data.get("user_agent") or data.get("userAgent") or (existing or {}).get("user_agent", ""),
            "created_at": (existing or {}).get("created_at", now),
            "updated_at": now,
            "metadata": json_dumps(data.get("metadata") or {}),
        }
        self.db.execute(
            """
            INSERT OR REPLACE INTO pan115_accounts (
              id, name, cookie, access_token, refresh_token, user_agent, created_at, updated_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            list(row.values()),
        )
        return self.get_account(account_id) or row

    def update_account_tokens(self, account_id: str, access_token: str, refresh_token: str) -> None:
        self.db.execute(
            "UPDATE pan115_accounts SET access_token = ?, refresh_token = ?, updated_at = ? WHERE id = ?",
            [access_token, refresh_token, now_iso(), account_id],
        )

    def delete_account(self, account_id: str) -> None:
        self.db.execute("DELETE FROM pan115_accounts WHERE id = ?", [account_id])

    def create_job(self, data: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        job_id = data.get("id") or new_id()
        row = {
            "id": job_id,
            "type": data.get("type") or "115",
            "status": data.get("status") or "queued",
            "phase": "",
            "profile_id": data.get("profile_id") or data.get("profileId") or "",
            "account_id": data.get("account_id") or data.get("accountId") or "",
            "source_provider": data.get("source_provider") or data.get("sourceProvider") or "",
            "source_pick_code": data.get("source_pick_code") or data.get("pickCode") or "",
            "source_url": data.get("source_url") or "",
            "source_headers": json_dumps(data.get("source_headers") or {}),
            "file_path": data.get("file_path") or data.get("filePath") or "",
            "file_name": data.get("file_name") or data.get("fileName") or "remote-file",
            "remote_dir": data.get("remote_dir") or data.get("remoteDir") or "",
            "remote_path": "",
            "size": int(data.get("size") or 0),
            "sha1": data.get("sha1") or "",
            "sha256": data.get("sha256") or "",
            "uploaded": 0,
            "total": int(data.get("size") or 0),
            "percent": 0,
            "speed_bps": 0.0,
            "attempts": 0,
            "max_attempts": int(data.get("max_attempts") or data.get("maxAttempts") or 3),
            "last_error": "",
            "logs": json_dumps([f"{now} 已创建任务"]),
            "result": json_dumps({}),
            "created_at": now,
            "updated_at": now,
            "started_at": "",
            "finished_at": "",
        }
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        self.db.execute(f"INSERT INTO transfer_jobs ({columns}) VALUES ({placeholders})", list(row.values()))
        return self.get_job(job_id) or row

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM transfer_jobs WHERE id = ?", [job_id])

    def list_jobs(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM transfer_jobs ORDER BY created_at DESC LIMIT ?", [limit])
        for row in rows:
            row["logs"] = json_loads(row.get("logs"), [])
            row["result"] = json_loads(row.get("result"), {})
            row["source_headers"] = json_loads(row.get("source_headers"), {})
        return rows

    def patch_job(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        if not patch:
            return self.get_job(job_id)
        values: list[Any] = []
        assignments: list[str] = []
        for key, value in patch.items():
            if key in ("logs", "result", "source_headers") and not isinstance(value, str):
                value = json_dumps(value)
            assignments.append(f"{key} = ?")
            values.append(value)
        assignments.append("updated_at = ?")
        values.append(now_iso())
        values.append(job_id)
        self.db.execute(f"UPDATE transfer_jobs SET {', '.join(assignments)} WHERE id = ?", values)
        return self.get_job(job_id)

    def append_job_log(self, job_id: str, message: str) -> None:
        row = self.get_job(job_id)
        if not row:
            return
        logs = json_loads(row.get("logs"), [])
        logs.append(f"{now_iso()} {message}")
        self.patch_job(job_id, {"logs": logs[-200:]})

    def claim_jobs(self, limit: int) -> list[dict[str, Any]]:
        rows = self.db.query(
            """
            SELECT * FROM transfer_jobs
            WHERE status IN ('queued', 'retry')
              AND attempts < max_attempts
            ORDER BY created_at ASC
            LIMIT ?
            """,
            [limit],
        )
        claimed: list[dict[str, Any]] = []
        for row in rows:
            attempts = int(row.get("attempts") or 0) + 1
            updated = self.patch_job(
                row["id"],
                {
                    "status": "running",
                    "phase": "准备",
                    "attempts": attempts,
                    "started_at": row.get("started_at") or now_iso(),
                    "last_error": "",
                },
            )
            if updated:
                claimed.append(updated)
        return claimed

    def retry_job(self, job_id: str) -> dict[str, Any] | None:
        return self.patch_job(job_id, {"status": "queued", "phase": "", "last_error": "", "uploaded": 0, "percent": 0, "speed_bps": 0})

    def delete_job(self, job_id: str) -> None:
        self.db.execute("DELETE FROM transfer_jobs WHERE id = ?", [job_id])

    def record_fingerprint(self, job: dict[str, Any], result: dict[str, Any]) -> None:
        size = int(result.get("size") or job.get("size") or 0)
        file_name = result.get("fileName") or job.get("file_name") or ""
        sha1 = result.get("sha1") or job.get("sha1") or ""
        sha256 = result.get("sha256") or job.get("sha256") or ""
        key = sha1 or sha256 or f"{file_name.lower()}:{size}"
        existing = self.db.one("SELECT id FROM fingerprints WHERE key = ? LIMIT 1", [key])
        now = now_iso()
        row_id = (existing or {}).get("id") or new_id()
        self.db.execute(
            """
            INSERT OR REPLACE INTO fingerprints (
              id, key, file_name, size, sha1, sha256, profile_id, remote_path,
              source_type, created_at, updated_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row_id,
                key,
                file_name,
                size,
                sha1,
                sha256,
                job.get("profile_id") or "",
                result.get("remotePath") or job.get("remote_path") or "",
                job.get("type") or "",
                now if not existing else now,
                now,
                json_dumps({}),
            ],
        )

    def fingerprint_count(self) -> int:
        row = self.db.one("SELECT COUNT(*) AS count FROM fingerprints")
        return int((row or {}).get("count") or 0)

    def stats(self) -> dict[str, Any]:
        jobs = self.db.one(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running,
              SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS queued,
              SUM(CASE WHEN status = 'retry' THEN 1 ELSE 0 END) AS retry,
              SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done,
              SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
              SUM(CASE WHEN status = 'running' THEN speed_bps ELSE 0 END) AS speed_bps,
              SUM(CASE WHEN status = 'done' THEN size ELSE 0 END) AS uploaded_size
            FROM transfer_jobs
            """
        ) or {}
        profiles = self.db.one("SELECT COUNT(*) AS count FROM sp_profiles WHERE enabled = TRUE") or {}
        return {
            "profiles": int(profiles.get("count") or 0),
            "fingerprints": self.fingerprint_count(),
            "jobs": {key: int(jobs.get(key) or 0) for key in ("total", "running", "queued", "retry", "done", "failed")},
            "speedBps": float(jobs.get("speed_bps") or 0),
            "uploadedSize": int(jobs.get("uploaded_size") or 0),
        }
