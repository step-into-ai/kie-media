import os
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from kie_media.client import KieApiError, KieClient, parse_result


class FakeResponse:
    def __init__(self, payload=None, status=200, content=b"", headers=None):
        self._payload = payload
        self.status_code = status
        self.content = content
        self.headers = headers or {"content-type": "application/json"}
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(str(self.status_code))

    def iter_content(self, chunk_size=65536):
        yield self.content


class ClientTests(unittest.TestCase):
    def test_parse_result_handles_documented_result_json(self):
        data = parse_result({"data": {"state": "success", "resultJson": '{"resultUrls":["https://x/a.png"]}'}})
        self.assertEqual(data.state, "success")
        self.assertEqual(data.urls, ["https://x/a.png"])

    def test_create_task_raises_on_kie_application_error(self):
        session = Mock()
        session.request.return_value = FakeResponse({"code": 402, "msg": "Insufficient Credits", "data": None})
        client = KieClient("secret", session=session, max_retries=0)
        with self.assertRaises(KieApiError) as ctx:
            client.create_task("x", {"prompt": "p"})
        self.assertEqual(ctx.exception.code, 402)

    def test_create_task_does_not_retry_non_idempotent_post(self):
        session = Mock()
        session.request.return_value = FakeResponse({"code": 503, "msg": "busy"}, status=503)
        client = KieClient("secret", session=session, max_retries=3)
        with self.assertRaises(KieApiError):
            client.create_task("x", {"prompt": "p"})
        self.assertEqual(session.request.call_count, 1)

    def test_wait_polls_until_success(self):
        client = KieClient("secret", session=Mock(), max_retries=0)
        client.get_task = Mock(side_effect=[
            {"code": 200, "data": {"taskId": "t", "state": "waiting"}},
            {"code": 200, "data": {"taskId": "t", "state": "success", "resultJson": '{"resultUrls":["https://x/v.mp4"]}'}},
        ])
        result = client.wait("t", timeout=2, interval=0.001)
        self.assertEqual(result.state, "success")
        self.assertEqual(result.urls[-1], "https://x/v.mp4")

    def test_wait_rejects_expired_deadline_before_polling(self):
        client = KieClient("secret", session=Mock(), max_retries=0)
        client.get_task = Mock()
        with self.assertRaises(KieApiError):
            client.wait("t", timeout=0, interval=1)
        client.get_task.assert_not_called()

    def test_wait_recovers_from_one_transient_poll_error(self):
        client = KieClient("secret", session=Mock(), max_retries=0)
        client.get_task = Mock(side_effect=[
            KieApiError("network failure"),
            {"code": 200, "data": {"taskId": "t", "state": "success", "resultJson": '{"resultUrls":[]}'}}
        ])
        self.assertEqual(client.wait("t", timeout=2, interval=0.001).state, "success")

    def test_wait_rejects_nonfinite_or_zero_polling_values(self):
        client = KieClient("secret", session=Mock(), max_retries=0)
        for timeout, interval in [(float("nan"), 1), (1, float("inf")), (1, 0)]:
            with self.assertRaises(KieApiError):
                client.wait("t", timeout=timeout, interval=interval)

    def test_upload_file_returns_download_url(self):
        session = Mock()
        session.request.return_value = FakeResponse({"success": True, "code": 200, "data": {"downloadUrl": "https://tmp/x.png"}})
        client = KieClient("secret", session=session, max_retries=0)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
            url = client.upload_file(path)
        self.assertEqual(url, "https://tmp/x.png")
        method, request_url = session.request.call_args.args[:2]
        self.assertEqual(method, "POST")
        self.assertEqual(request_url, "https://kieai.redpandaai.co/api/file-stream-upload")
        kwargs = session.request.call_args.kwargs
        self.assertIn("files", kwargs)

    def test_upload_retry_rewinds_file(self):
        bodies = []

        class UploadSession:
            calls = 0
            def request(self, method, url, **kwargs):
                self.calls += 1
                bodies.append(kwargs["files"]["file"][1].read())
                if self.calls == 1:
                    return FakeResponse({"code": 503, "msg": "busy"}, status=503)
                return FakeResponse({"success": True, "code": 200, "data": {"downloadUrl": "https://tmp/x.png"}})

        client = KieClient("secret", session=UploadSession(), max_retries=1)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\nabcdef")
            client.upload_file(path)
        self.assertEqual(bodies, [b"\x89PNG\r\n\x1a\nabcdef", b"\x89PNG\r\n\x1a\nabcdef"])

    def test_upload_rejects_non_media_and_empty_files(self):
        client = KieClient("secret", session=Mock(), max_retries=0)
        with tempfile.TemporaryDirectory() as td:
            text = Path(td) / "x.html"
            text.write_text("<html>not media</html>")
            empty = Path(td) / "empty.jpg"
            empty.touch()
            with self.assertRaises(KieApiError): client.upload_file(text)
            with self.assertRaises(KieApiError): client.upload_file(empty)
        client.session.request.assert_not_called()

    def test_upload_rejects_media_of_wrong_parameter_kind(self):
        client = KieClient("secret", session=Mock(), max_retries=0)
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "clip.mp4"
            video.write_bytes(b"\x00\x00\x00\x18ftypisommedia")
            with self.assertRaises(KieApiError):
                client.upload_file(video, expected_kind="image")
        client.session.request.assert_not_called()

    def test_remote_media_url_rejects_detectable_wrong_kind(self):
        client = KieClient("secret", session=Mock(), max_retries=0)
        with self.assertRaises(KieApiError):
            client.resolve_media("https://cdn.example/clip.mp4", "image")

    def test_download_urls_writes_persistent_assets(self):
        session = Mock()
        media = b"\x00\x00\x00\x18ftypisommedia"
        session.get.return_value = FakeResponse(None, content=media, headers={"content-type": "video/mp4"})
        client = KieClient("secret", session=session, max_retries=0)
        with tempfile.TemporaryDirectory() as td:
            paths = client.download_urls(["https://cdn.example/result"], Path(td), task_id="task1")
            self.assertEqual(Path(paths[0]).suffix, ".mp4")
            self.assertEqual(Path(paths[0]).read_bytes(), media)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(Path(paths[0]).stat().st_mode), 0o600)

    def test_download_rejects_html_and_empty_media(self):
        for content, headers in [
            (b"<html>error</html>", {"content-type": "text/html"}),
            (b"", {"content-type": "video/mp4"}),
        ]:
            session = Mock()
            session.get.return_value = FakeResponse(None, content=content, headers=headers)
            client = KieClient("secret", session=session, max_retries=0)
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(KieApiError):
                    client.download_urls(["https://cdn.example/result"], td, task_id="task1")
                self.assertEqual(list(Path(td).iterdir()), [])

    def test_download_failure_leaves_no_final_or_partial_file(self):
        class BrokenResponse(FakeResponse):
            def iter_content(self, chunk_size=65536):
                yield b"partial"
                raise OSError("disk/network broke")
        session = Mock()
        session.get.return_value = BrokenResponse(None, headers={"content-type": "video/mp4"})
        client = KieClient("secret", session=session, max_retries=0)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(KieApiError):
                client.download_urls(["https://cdn.example/result"], td, task_id="task1")
            self.assertEqual(list(Path(td).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
