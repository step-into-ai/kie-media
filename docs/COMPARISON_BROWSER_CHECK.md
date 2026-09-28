# Comparison browser acceptance

This optional offline smoke test serves a temporary directions collection over
loopback HTTP. It does not require a KIE key or call a provider. It uses real,
locally generated PNG/MP4 fixtures, including filenames with spaces, Unicode,
`#` and `%`. Requires Python 3.11+, ffmpeg on PATH and Playwright Chromium.

```bash
python -m pip install -e ".[dev]" playwright==1.63.0
python -m playwright install chromium
PYTHONPATH=src:. python scripts/check_comparison_browser.py --screenshots outputs/browser
```

On PowerShell, set `$env:PYTHONPATH = "src;."` before the last command.
The script checks desktop (1440px) and mobile (390px) layout, decoded images and
videos, pending placeholders, escaped brief text, expandable motion details,
selection download and the exported file's real CLI compose dry-run. Browser
errors, failed HTTP requests, horizontal overflow and incorrect selection data
fail the check. Inspect both generated screenshots for visual acceptance.
Generated fixtures are deleted; screenshots stay in the ignored output folder.
An existing Chromium executable can be selected with `KIE_BROWSER_EXECUTABLE`.

Acceptance on 2026-09-28: Playwright 1.63.0 / Chromium 153.0.8010.0, all checks
passed, desktop/mobile screenshots visually inspected. In this environment the
Playwright CDN returned invalid archives, so the installed Chromium executable
from `@sparticuz/chromium` 153.0.0 was used. No browser security flags were added.

To inspect your own collection manually:

```bash
kie-media project compare ./ideas/directions.json --json
python -m http.server 8000 --bind 127.0.0.1 --directory ./ideas
```

Open `http://127.0.0.1:8000/comparison.html`. Keep the collection and its media
in place while serving. Comparison media links are relative and URL-encoded,
so the browser loads previews from HTTP rather than blocked local file URLs.
Stop the server with Ctrl+C after inspection.
