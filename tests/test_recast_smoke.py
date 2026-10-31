"""Regression: recasting must resume one paid task, never submit a replacement."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kie_media.client import TaskResult
from kie_media.recast import build_recast_plan, run_recast


class RecastSmokeTests(unittest.TestCase):
    def test_poll_failure_resumes_known_task(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.mp4"
            source.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"source" * 8)
            reference = root / "hero.png"
            reference.write_bytes(b"\x89PNG\r\n\x1a\n" + b"reference" * 8)
            output = root / "result.mp4"
            output.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"result" * 8)
            def metadata(path):
                return {"duration": 6 if Path(path).suffix == ".mp4" else 0,
                        "width": 720, "height": 720, "video": Path(path).suffix == ".mp4",
                        "image": Path(path).suffix == ".png", "audio": False}
            with patch("kie_media.recast.probe", side_effect=metadata):
                plan = build_recast_plan(source, "Replace the performer with the reference character",
                                         references=[reference])
                client = Mock()
                client.resolve_media.side_effect = lambda value, kind: "https://example.test/" + Path(value).name
                client.create_task.return_value = ("one-paid-task", {})
                client.wait.side_effect = [TimeoutError("poll interrupted"),
                    TaskResult(task_id="one-paid-task", state="success", urls=["https://example.test/result.mp4"])]
                client.download_urls.return_value = [str(output)]
                manifest = root / "recast-run.json"
                first = run_recast(plan, manifest, client=client)
                self.assertEqual(first["state"], "pending")
                second = run_recast(plan, manifest, client=client)
                self.assertEqual(second["state"], "awaiting_review")
                client.create_task.assert_called_once()
                stored = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(stored["execution"]["task_id"], "one-paid-task")


if __name__ == "__main__":
    unittest.main()
