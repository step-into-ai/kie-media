# Contributing

Thanks for improving KIE Media.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Required verification

```bash
python3 -m compileall -q src tests scripts
PYTHONPATH=src:. python3 -m unittest discover -s tests -v
PYTHONPATH=src:. python3 scripts/evaluate_planner.py
python3 scripts/validate_distribution.py
PYTHONPATH=. python3 scripts/sync_codex_plugin.py --check
python3 scripts/security_scan.py
.venv/bin/pip wheel . --no-deps -w /tmp/kie-media-wheel
```

## Pull requests

- Add a regression test before changing planner, model validation, manifests, or paid execution.
- Keep the canonical skill under `skills/kie-media`; adapters must only point to it.
- Planning must remain deterministic, offline, and key-free.
- Never add automatic retries around paid task creation.
- Document new workflows, CLI flags, schemas, and capability gaps.
- Do not include generated media, run manifests, API payloads, or secrets.

## Releases

Package versions use semantic versioning. Update `CHANGELOG.md` and package version together. A `vX.Y.Z` tag triggers the verified GitHub Release workflow; do not tag before CI is green.
