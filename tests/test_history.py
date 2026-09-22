import os
import json
import stat
import tempfile
import unittest
from pathlib import Path

from kie_media.history import HistoryStore


class HistoryTests(unittest.TestCase):
    def test_append_and_list_recent(self):
        with tempfile.TemporaryDirectory() as td:
            store = HistoryStore(Path(td) / "history.jsonl")
            store.append({"task_id": "a", "state": "waiting"})
            store.append({"task_id": "b", "state": "success"})
            self.assertEqual([x["task_id"] for x in store.list(limit=2)], ["b", "a"])

    def test_secrets_are_never_persisted(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "history.jsonl"
            HistoryStore(path).append({
                "task_id": "a", "api_key": "secret", "headers": {"Authorization": "Bearer secret"},
                "access_token": "secret", "client_secret": "secret", "password": "secret", "x-api-key": "secret",
            })
            text = path.read_text()
            self.assertNotIn("secret", text)
            self.assertNotIn("Authorization", text)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_non_positive_limit_returns_no_rows(self):
        with tempfile.TemporaryDirectory() as td:
            store = HistoryStore(Path(td) / "history.jsonl")
            store.append({"task_id": "a"})
            self.assertEqual(store.list(limit=0), [])
            self.assertEqual(store.list(limit=-1), [])


if __name__ == "__main__":
    unittest.main()
