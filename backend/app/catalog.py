from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from .dedupe import fingerprint_key


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def entries_for_remote_file(profile: dict[str, Any], file: dict[str, Any]) -> list[dict[str, Any]]:
    base = {
        "size": int(file.get("size") or 0),
        "sourceType": "sp-scan",
        "profileId": profile.get("id"),
        "remotePath": file.get("remotePath"),
        "fileName": PurePosixPath(file.get("remotePath") or "").name,
        "itemId": file.get("id") or "",
        "webUrl": file.get("webUrl") or "",
        "scannedAt": now_iso(),
    }
    file_name = PurePosixPath(file.get("remotePath") or "").name
    if not file_name:
        return []
    return [{
        "size": int(file.get("size") or 0),
        "sourceType": "sp-scan",
        "profileId": profile.get("id"),
        "remotePath": file.get("remotePath"),
        "fileName": file_name,
        "itemId": file.get("id") or "",
        "webUrl": file.get("webUrl") or "",
        "scannedAt": now_iso(),
    }]


class CatalogService:
    def __init__(self, profile_store, graph_client, dedupe_store):
        self.profile_store = profile_store
        self.graph = graph_client
        self.dedupe = dedupe_store
        self.status = {
            "running": False,
            "lastStartedAt": "",
            "lastFinishedAt": "",
            "lastError": "",
            "scannedProfiles": 0,
            "scannedFiles": 0,
            "indexedFingerprints": 0,
            "removedFingerprints": 0,
        }

    def get_status(self) -> dict[str, Any]:
        return dict(self.status)

    async def scan_all(self, profile_id: str = "") -> dict[str, Any]:
        if self.status["running"]:
            raise ValueError("全局媒体目录正在扫描")
        self.status.update(
            {
                "running": True,
                "lastStartedAt": now_iso(),
                "lastFinishedAt": "",
                "lastError": "",
                "scannedProfiles": 0,
                "scannedFiles": 0,
                "indexedFingerprints": 0,
                "removedFingerprints": 0,
            }
        )
        try:
            profiles = self.profile_store.list(True)
            if profile_id:
                profiles = [item for item in profiles if item.get("id") == profile_id]
                if profiles and not profiles[0].get("capacityEnabled", True):
                    raise ValueError("该 SP 未启用自动容量池，不允许执行目录扫描")
            else:
                profiles = [item for item in profiles if item.get("capacityEnabled", True)]
            for profile in profiles:
                root = profile.get("rootPath") or ""
                files = await self.graph.list_remote_tree(profile, root.strip("/"))
                entries = [entry for file in files for entry in entries_for_remote_file(profile, file)]
                self.status["indexedFingerprints"] += self.dedupe.record_many(entries)
                current_pairs: set[tuple[str, str]] = set()
                for entry in entries:
                    remote_path = str(entry.get("remotePath") or "").replace("\\", "/").strip("/")
                    key = fingerprint_key(entry.get("fileName") or "", int(entry.get("size") or 0))
                    if remote_path and key:
                        current_pairs.add((remote_path, key))
                self.status["removedFingerprints"] += self.dedupe.prune_profile(profile["id"], current_pairs, root)
                self.status["scannedProfiles"] += 1
                self.status["scannedFiles"] += len(files)
            self.status["lastFinishedAt"] = now_iso()
            self.status["running"] = False
            return self.get_status()
        except Exception as error:
            self.status["lastError"] = str(error)
            raise
        finally:
            self.status["running"] = False
