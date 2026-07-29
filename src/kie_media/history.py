from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SENSITIVE_MARKERS = ("token", "secret", "password", "credential", "authorization", "apikey")


def _sensitive_key(key: str) -> bool:
    normalized = "".join(ch for ch in key.lower() if ch.isalnum())
    return normalized == "headers" or normalized.endswith("key") or any(marker in normalized for marker in SENSITIVE_MARKERS)


def default_home() -> Path:
    override = os.environ.get("KIE_MEDIA_HOME")
    if override: return Path(override).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share") / "kie-media"


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if not _sensitive_key(k)}
    if isinstance(value, list): return [_scrub(item) for item in value]
    return value


class HistoryStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_home() / "history.jsonl"

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        item = _scrub(dict(record))
        item.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.chmod(self.path, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0: return []
        if not self.path.exists(): return []
        rows = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: continue
        return list(reversed(rows[-max(0, limit):]))

    def cost_profile(self) -> dict[str, dict[str, float | int]]:
        """Aggregate observed successful task costs without counting duplicate rows."""
        if not self.path.exists():
            return {}
        by_task: dict[str, tuple[str, float]] = {}
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("state") or "").casefold() not in {"success", "completed", "complete", "succeeded"}:
                continue
            task_id = str(row.get("task_id") or "")
            model = str(row.get("model") or "")
            credits = row.get("credits_consumed")
            if not task_id or not model or isinstance(credits, bool) or not isinstance(credits, (int, float)) or credits < 0:
                continue
            by_task[task_id] = (model, float(credits))
        grouped: dict[str, list[float]] = {}
        for model, credits in by_task.values():
            grouped.setdefault(model, []).append(credits)
        return {
            model: {
                "samples": len(values),
                "median_credits": float(statistics.median(values)),
                "minimum_credits": min(values),
                "maximum_credits": max(values),
            }
            for model, values in sorted(grouped.items())
        }
