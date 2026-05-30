from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .db import AppDatabase, json_dumps, new_id
from .utils import clean


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint_key(file_name: str, size: int) -> str | None:
    name = clean(file_name).lower()
    if not name:
        return None
    return f"{name}:{int(size)}"


class DedupeStore:
    def __init__(self, database: AppDatabase):
        self.database = database

    def count(self) -> int:
        rows = self.database.query("SELECT COUNT(*) AS count FROM media_fingerprints")
        return int(rows[0]["count"] if rows else 0)

    def list(self, limit: int = 1000) -> list[dict[str, Any]]:
        return self.database.query(
            "SELECT * FROM media_fingerprints ORDER BY created_at DESC LIMIT ?", [limit]
        )

    def latest(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.list(limit)

    def find(self, file_name: str, size: int) -> dict[str, Any] | None:
        key = fingerprint_key(file_name, size)
        if not key:
            return None
        rows = self.database.query(
            "SELECT * FROM media_fingerprints WHERE key = ? ORDER BY created_at ASC LIMIT 1",
            [key],
        )
        return rows[0] if rows else None

    def record(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        file_name = clean(entry.get("fileName") or entry.get("file_name"))
        size = int(entry.get("size") or 0)
        key = fingerprint_key(file_name, size)
        if not key:
            return None
        profile_id = clean(entry.get("profileId") or entry.get("profile_id"))
        remote_path = clean(entry.get("remotePath") or entry.get("remote_path"))
        existing = self.database.query(
            """
            SELECT id, created_at FROM media_fingerprints
            WHERE key = ? AND profile_id = ? AND remote_path = ?
            LIMIT 1
            """,
            [key, profile_id, remote_path],
        )
        item = {
            "id": existing[0]["id"] if existing else entry.get("id") or new_id(),
            "algorithm": "name+size",
            "hash": f"{file_name}:{size}",
            "size": int(entry.get("size") or 0),
            "key": key,
            "source_type": clean(entry.get("sourceType") or entry.get("source_type")),
            "profile_id": profile_id,
            "remote_path": remote_path,
            "file_name": clean(entry.get("fileName") or entry.get("file_name")),
            "item_id": clean(entry.get("itemId") or entry.get("item_id")),
            "web_url": clean(entry.get("webUrl") or entry.get("web_url")),
            "scanned_at": clean(entry.get("scannedAt") or entry.get("scanned_at")),
            "created_at": existing[0]["created_at"] if existing else clean(entry.get("createdAt") or entry.get("created_at")) or now_iso(),
            "updated_at": now_iso(),
            "metadata": json_dumps(entry.get("metadata") or {}),
        }
        if existing:
            self.database.execute(
                """
                UPDATE media_fingerprints
                SET algorithm = ?, hash = ?, size = ?, key = ?, source_type = ?,
                    profile_id = ?, remote_path = ?, file_name = ?, item_id = ?,
                    web_url = ?, scanned_at = ?, created_at = ?, updated_at = ?, metadata = ?
                WHERE id = ?
                """,
                [
                    item["algorithm"],
                    item["hash"],
                    item["size"],
                    item["key"],
                    item["source_type"],
                    item["profile_id"],
                    item["remote_path"],
                    item["file_name"],
                    item["item_id"],
                    item["web_url"],
                    item["scanned_at"],
                    item["created_at"],
                    item["updated_at"],
                    item["metadata"],
                    item["id"],
                ],
            )
        else:
            self.database.execute(
                """
                INSERT INTO media_fingerprints (
                  id, algorithm, hash, size, key, source_type, profile_id, remote_path,
                  file_name, item_id, web_url, scanned_at, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                list(item.values()),
            )
        return item

    def record_many(self, entries: list[dict[str, Any]]) -> int:
        changed = 0
        for entry in entries:
            if self.record(entry):
                changed += 1
        return changed

    def prune_profile(self, profile_id: str, current_pairs: set[tuple[str, str]], root_path: str = "") -> int:
        """Remove fingerprints for a profile that no longer exist in the latest scan."""
        profile_id = clean(profile_id)
        root = clean(root_path).replace("\\", "/").strip("/")
        rows = self.database.query(
            "SELECT id, remote_path, key FROM media_fingerprints WHERE profile_id = ? ORDER BY updated_at DESC, created_at DESC",
            [profile_id],
        )
        stale_ids: list[str] = []
        seen_pairs: set[tuple[str, str]] = set()
        for row in rows:
            remote_path = clean(row.get("remote_path")).replace("\\", "/").strip("/")
            if root and remote_path != root and not remote_path.startswith(f"{root}/"):
                continue
            pair = (remote_path, clean(row.get("key")))
            if pair not in current_pairs or pair in seen_pairs:
                stale_ids.append(row["id"])
                continue
            seen_pairs.add(pair)
        for item_id in stale_ids:
            self.database.execute("DELETE FROM media_fingerprints WHERE id = ?", [item_id])
        return len(stale_ids)

    def find_duplicates(self) -> list[dict[str, Any]]:
        """查找重复指纹：同一文件名+大小出现至少2次"""
        rows = self.database.query("""
            SELECT key, COUNT(*) AS count,
                   STRING_AGG(id, ',') AS ids,
                   STRING_AGG(file_name, ',') AS files,
                   STRING_AGG(profile_id, ',') AS profiles,
                   STRING_AGG(remote_path, ',') AS paths,
                   STRING_AGG(item_id, ',') AS items,
                   STRING_AGG(web_url, ',') AS urls,
                   hash, size
            FROM media_fingerprints
            GROUP BY key, hash, size
            HAVING COUNT(*) > 1
            ORDER BY size DESC
            LIMIT 200
        """)
        for row in rows:
            row["count"] = int(row["count"])
            row["size"] = int(row["size"])
        return rows

    def remove_by_item(self, item_id: str) -> int:
        item_id = clean(item_id)
        if not item_id:
            return 0
        rows = self.database.query("SELECT COUNT(*) AS count FROM media_fingerprints WHERE item_id = ?", [item_id])
        count = int((rows[0] if rows else {}).get("count") or 0)
        if count:
            self.database.execute("DELETE FROM media_fingerprints WHERE item_id = ?", [item_id])
        return count

    def remove_by_profile_path(self, profile_id: str, remote_path: str) -> int:
        profile_id = clean(profile_id)
        path = clean(remote_path).replace("\\", "/").strip("/")
        if not profile_id or not path:
            return 0
        rows = self.database.query(
            "SELECT id, remote_path FROM media_fingerprints WHERE profile_id = ?",
            [profile_id],
        )
        remove_ids: list[str] = []
        for row in rows:
            current_path = clean(row.get("remote_path")).replace("\\", "/").strip("/")
            if current_path == path or current_path.startswith(f"{path}/"):
                remove_ids.append(row["id"])
        for item_id in remove_ids:
            self.database.execute("DELETE FROM media_fingerprints WHERE id = ?", [item_id])
        return len(remove_ids)

    def clear(self) -> None:
        self.database.execute("DELETE FROM media_fingerprints")
