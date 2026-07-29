from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .history import default_home


class PreferencesError(ValueError):
    pass


TIERS = ("budget", "balanced", "premium")


def _model_value(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if len(value) > 300 or any(ord(char) < 32 for char in value):
        raise PreferencesError(f"Invalid {field}")
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned


@dataclass(frozen=True)
class Preferences:
    default_tier: str = "balanced"
    image_model: str | None = None
    video_model: str | None = None
    excluded_models: tuple[str, ...] = ()
    max_jobs: int = 5

    def validate(self) -> "Preferences":
        if self.default_tier not in TIERS:
            raise PreferencesError(f"default_tier must be one of: {', '.join(TIERS)}")
        if isinstance(self.max_jobs, bool) or not isinstance(self.max_jobs, int) or not 1 <= self.max_jobs <= 100:
            raise PreferencesError("max_jobs must be an integer from 1 to 100")
        _model_value(self.image_model, "image_model")
        _model_value(self.video_model, "video_model")
        for model in self.excluded_models:
            _model_value(model, "excluded_models")
        return self

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["excluded_models"] = list(self.excluded_models)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Preferences":
        try:
            prefs = cls(
                default_tier=str(value.get("default_tier") or "balanced"),
                image_model=_model_value(value.get("image_model"), "image_model"),
                video_model=_model_value(value.get("video_model"), "video_model"),
                excluded_models=tuple(str(item) for item in value.get("excluded_models") or ()),
                max_jobs=int(value.get("max_jobs", 5)),
            )
        except (TypeError, ValueError) as exc:
            raise PreferencesError(f"Invalid preferences: {exc}") from exc
        return prefs.validate()


class PreferencesStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_home() / "preferences.json"

    def load(self) -> Preferences:
        if not self.path.is_file():
            return Preferences()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PreferencesError(f"Unable to read preferences: {exc}") from exc
        if not isinstance(payload, dict):
            raise PreferencesError("Preferences file must contain a JSON object")
        return Preferences.from_dict(payload)

    def save(self, preferences: Preferences) -> None:
        preferences.validate()
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not parent_existed:
            try:
                os.chmod(self.path.parent, 0o700)
            except OSError:
                pass
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        temp = Path(temp_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(preferences.to_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def reset(self) -> Preferences:
        preferences = Preferences()
        self.save(preferences)
        return preferences
