"""Offline HTTP/browser acceptance. Requires Playwright Chromium and ffmpeg.

PYTHONPATH=src:. python scripts/check_comparison_browser.py
Optional --screenshots outputs/browser saves desktop/mobile evidence.
"""
import argparse
import contextlib
import io
import json
import os
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from kie_media.cli import main as cli
from kie_media.directions import compare_directions, create_directions
from kie_media.projects import create_project, review_stage, run_project


def check(screenshots=None):
    with tempfile.TemporaryDirectory(prefix="kie-browser-") as temp:
        root = Path(temp)
        source = root / "source" / "project.json"
        create_project(source, "Bottle <test> & three directions", shots=3)
        collection = root / "ideas" / "directions.json"
        create_directions(source, collection.parent)
        # Real decodable fixtures, no provider requests or credentials.
        for name, color in [("calm", "blue"), ("playful", "orange")]:
            project = collection.parent / name / "project.json"

            def runner(stage, checkpoint):
                checkpoint(stage["id"])
                video = stage["kind"] == "video"
                output = project.parent / (stage["id"] + " ü #%." + ("mp4" if video else "png"))
                command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=10"]
                command += ["-t", "1", "-pix_fmt", "yuv420p"] if video else ["-frames:v", "1"]
                subprocess.run(command + [str(output)], check=True)
                return {"state": "success", "task_id": stage["id"], "files": [str(output)]}

            result = run_project(project, phase="images", max_jobs=3, runner=runner)
            for stage in result["review_stages"]:
                review_stage(project, stage, "accepted", "Synthetic browser fixture")
            if name == "playful":
                run_project(project, phase="videos", max_jobs=3, runner=runner)
        comparison = Path(compare_directions(collection)["file"])

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                else:
                    super().do_GET()

        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(collection.parent)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=os.environ.get("KIE_BROWSER_EXECUTABLE"))
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
                page.on("requestfailed", lambda req: errors.append(req.url))
                page.on("response", lambda res: errors.append(f"HTTP {res.status}: {res.url}") if res.status >= 400 else None)
                page.goto(f"http://127.0.0.1:{server.server_port}/{comparison.name}")
                page.wait_for_function("""() => [...document.images].every(i => i.complete && i.naturalWidth > 0)
                    && [...document.querySelectorAll('video')].every(v => v.readyState >= 2 && v.videoWidth > 0)""")
                page.evaluate("() => Promise.all([...document.querySelectorAll('video')].map(v => v.play()))")
                page.wait_for_function("() => [...document.querySelectorAll('video')].every(v => v.currentTime > 0)")
                page.evaluate("() => document.querySelectorAll('video').forEach(v => v.pause())")
                assert page.locator("section").count() == 3
                assert page.locator("article").count() == 9
                assert page.locator("img").count() == 3
                assert page.locator("video").count() == 3
                assert page.get_by_text("Preview pending", exact=True).count() == 3
                assert page.locator("h1").inner_text() == "Bottle <test> & three directions"
                assert page.locator("h1 test").count() == 0
                for width, label, columns in [(1440, "desktop", 3), (390, "mobile", 1)]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.locator(".grid").first.evaluate("e => getComputedStyle(e).gridTemplateColumns.split(' ').length") == columns
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), label
                    page.locator("summary").first.click()
                    assert page.locator("details").first.get_attribute("open") is not None
                    page.locator("summary").first.click()
                    if screenshots:
                        screenshots.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(screenshots / f"{label}.png"), full_page=True)
                picks = {"scene-1": "calm", "scene-2": "playful", "scene-3": "dramatic"}
                for scene, direction in picks.items():
                    page.locator(f'select[data-scene="{scene}"]').select_option(direction)
                with page.expect_download() as download:
                    page.get_by_role("button", name="Download selection.json").click()
                selection = root / "selection.json"
                assert download.value.suggested_filename == "selection.json"
                download.value.save_as(selection)
                payload = json.loads(selection.read_text(encoding="utf-8"))
                assert payload == {"collection_id": json.loads(collection.read_text(encoding="utf-8"))["id"], "picks": picks}
                output = root / "winner" / "project.json"
                result = io.StringIO()
                with contextlib.redirect_stdout(result):
                    assert cli(["project", "compose", str(collection), "--selection-file", str(selection), "--output", str(output), "--dry-run", "--json"]) == 0
                report = json.loads(result.getvalue())
                assert report["new_jobs"] == 3 and report["paid_requests"] == 0
                assert not output.parent.exists()
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    print("PASS: HTTP images/video/pending, desktop/mobile layout, escaped text, motion details, selection download and CLI dry-run; no browser errors or paid requests.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path)
    check(parser.parse_args().screenshots)
