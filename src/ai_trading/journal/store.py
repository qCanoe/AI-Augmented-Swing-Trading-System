"""JSONL journal store for pipeline events."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_ALLOWED_EVENT_TYPES = {
    "cycle_start",
    "market_data",
    "candidate",
    "ai_decision",
    "risk_check",
    "order",
    "position_update",
    "cycle_end",
    "error",
}


class JournalStore:
    """Append-only JSONL event store."""

    def __init__(self, journal_dir: Path) -> None:
        self._journal_dir = journal_dir
        self._journal_dir.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        """Append one event line to daily JSONL file."""
        if event_type not in _ALLOWED_EVENT_TYPES:
            raise ValueError(f"unsupported_event_type: {event_type}")
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        file_path = self._file_path_for_day(datetime.now(timezone.utc).date())
        with file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")

    def load_recent(self, limit: int) -> list[dict[str, Any]]:
        """Load recent events from the most recent journal files."""
        if limit <= 0:
            return []

        rows: list[dict[str, Any]] = []
        files = sorted(self._journal_dir.glob("*.jsonl"), reverse=True)
        for file in files:
            lines = file.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines):
                if not line.strip():
                    continue
                rows.append(json.loads(line))
                if len(rows) >= limit:
                    return list(reversed(rows))
        return list(reversed(rows))

    def _file_path_for_day(self, day: date) -> Path:
        return self._journal_dir / f"{day.isoformat()}.jsonl"
