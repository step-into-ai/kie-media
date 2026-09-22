"""Read-only discovery/diagnostics; no uploads or generation."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .catalog import DocsCatalog, _spec_to_dict
from .storage import atomic_json


def doctor() -> dict:
    return {"python": platform.python_version(), "platform": platform.system(),
            "credentials_in_environment": bool(os.environ.get("KIE_API_KEY")),
            "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
            "state_permissions": "inherited Windows directory ACLs" if os.name == "nt" else "owner-only POSIX modes",
            "paid_requests": 0}


def audit_catalog(catalog: DocsCatalog, *, kind=None, limit=None, refresh=False) -> dict:
    entries = catalog.search(kind=kind, refresh=refresh)
    selected = entries[:limit] if limit else entries

    def inspect(entry):
        base = {**entry.to_dict(), "live_tested": False}
        try:
            document = catalog._fetch_text(entry.url, catalog.MAX_DOCUMENT_BYTES)
            spec = catalog._extract_model(entry, document)
            base.update(model=spec.id, family=spec.family, endpoint=spec.endpoint,
                        status="schema_validated", adapter_available=spec.family in {"task", "chat", "responses", "messages", "gemini"},
                        schema_sha256=hashlib.sha256(json.dumps(spec.input_schema, sort_keys=True).encode()).hexdigest())
            return base, spec
        except Exception as exc:
            base.update(status="unsupported_or_unavailable", reason=f"{type(exc).__name__}: {exc}")
            return base, None

    # Cache updates happen serially after read-only network discovery.
    with ThreadPoolExecutor(max_workers=4) as executor:
        inspected = list(executor.map(inspect, selected))
    models = {model.id: model for model in catalog._read_models()}
    for _, spec in inspected:
        if spec:
            models[spec.id] = spec
    atomic_json(catalog.models_path, {"version": 2, "models": [_spec_to_dict(m) for m in models.values()]})
    rows = [row for row, _ in inspected]
    report = {"observed_at": datetime.now(timezone.utc).isoformat(), "source": catalog.INDEX_URL,
              "indexed_documents": len(entries), "inspected_documents": len(rows),
              "schema_validated": sum(row["status"] == "schema_validated" for row in rows),
              "note": "Document/operation counts, not unique models. Schema validation is not a paid generation test.",
              "entries": rows}
    atomic_json(catalog.cache_dir / "coverage.json", report)
    return report
