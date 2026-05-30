from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileModel:
    id: str
    name: str
    drive_id: str = ""
    root_path: str = ""
    capacity_enabled: bool = True
