from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, state_file: str) -> None:
        self._path = Path(state_file)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"last_seen_id": None}

        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
