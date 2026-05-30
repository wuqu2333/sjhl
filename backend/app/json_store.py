from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


class JsonStore:
    def __init__(self, file_path: Path, default_value: dict[str, Any]):
        self.file_path = file_path
        self.default_value = default_value

    def read(self) -> dict[str, Any]:
        if not self.file_path.exists():
            return deepcopy(self.default_value)
        return json.loads(self.file_path.read_text(encoding="utf-8-sig"))

    def write(self, value: dict[str, Any]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.file_path)

    def update(self, updater: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        value = self.read()
        next_value = updater(value)
        self.write(next_value)
        return next_value
