#!/usr/bin/env python3
"""Conservative source scan for accidentally committed credentials."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai-style-key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github-token": re.compile(r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "kie-key-assignment": re.compile(
        r"(?i)KIE_API_KEY\s*=\s*[\"']?(?!\.{3}|<|your|redacted|example|\$)[A-Za-z0-9_-]{16,}"
    ),
}
SKIP_PARTS = {".git", ".venv", "build", "dist", "outputs", "kie-media-output", "__pycache__", ".pytest_cache"}


def candidate_files(root: Path = ROOT) -> list[Path]:
    command = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=True)
    files = []
    for line in result.stdout.splitlines():
        path = root / line
        if path.is_file() and not SKIP_PARTS.intersection(path.relative_to(root).parts):
            files.append(path)
    return files


def scan(root: Path = ROOT) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for path in candidate_files(root):
        data = path.read_bytes()
        if len(data) > 2_000_000 or b"\x00" in data:
            continue
        text = data.decode("utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    hits.append({"file": str(path.relative_to(root)), "line": line_number, "pattern": label})
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    hits = scan()
    if args.json:
        print(json.dumps({"passed": not hits, "hits": hits}, indent=2))
    elif hits:
        for hit in hits:
            print(f"{hit['file']}:{hit['line']}: possible {hit['pattern']}")
    else:
        print("Secret scan passed")
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
