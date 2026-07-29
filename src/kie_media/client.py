from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

API_BASE = "https://api.kie.ai"
# KIE documents uploads on a separate host. api.kie.ai returns 404 here.
UPLOAD_BASE = "https://kieai.redpandaai.co"
SUCCESS_STATES = {"success", "completed", "complete", "succeeded"}
FAIL_STATES = {"fail", "failed", "error", "cancelled", "canceled"}
RETRYABLE_STATUS = {429, 455, 500, 502, 503, 504}


def validate_wait_options(timeout: float, interval: float) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise KieApiError("wait timeout must be a finite value greater than zero")
    if not math.isfinite(interval) or interval <= 0:
        raise KieApiError("wait interval must be a finite value greater than zero")


def _media_signature_valid(path: Path, mime: str) -> bool:
    with path.open("rb") as handle:
        header = handle.read(16)
    if not header:
        return False
    if mime == "image/jpeg": return header.startswith(b"\xff\xd8\xff")
    if mime == "image/png": return header.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/webp": return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if mime == "image/gif": return header.startswith((b"GIF87a", b"GIF89a"))
    if mime in {"video/mp4", "video/quicktime", "audio/mp4", "audio/x-m4a"}: return header[4:8] == b"ftyp"
    if mime == "video/webm": return header.startswith(b"\x1aE\xdf\xa3")
    if mime in {"audio/mpeg", "audio/mp3"}: return header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
    if mime in {"audio/wav", "audio/x-wav"}: return header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    if mime in {"audio/ogg", "application/ogg"}: return header.startswith(b"OggS")
    if mime in {"audio/flac", "audio/x-flac"}: return header.startswith(b"fLaC")
    return False


class KieApiError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.code = code
        self.payload = payload


@dataclass
class TaskResult:
    task_id: str = ""
    model: str = ""
    state: str = ""
    urls: list[str] = field(default_factory=list)
    credits_consumed: float | None = None
    fail_code: str = ""
    fail_message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def _urls_from(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        urls.append(value)
    elif isinstance(value, list):
        for item in value:
            urls.extend(_urls_from(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"resulturls", "result_urls", "urls", "images", "imageurls", "videourls", "audiourls", "url", "downloadurl", "firstframeurl", "lastframeurl"}:
                urls.extend(_urls_from(item))
    return list(dict.fromkeys(urls))


def parse_result(payload: dict[str, Any]) -> TaskResult:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    result_json = data.get("resultJson") or data.get("result_json")
    parsed: Any = {}
    if isinstance(result_json, str) and result_json.strip():
        try: parsed = json.loads(result_json)
        except json.JSONDecodeError: parsed = {}
    elif isinstance(result_json, (dict, list)):
        parsed = result_json
    urls = _urls_from(parsed)
    if not urls:
        urls = _urls_from(data)
    state = str(data.get("state") or data.get("status") or "").lower()
    return TaskResult(
        task_id=str(data.get("taskId") or data.get("task_id") or ""),
        model=str(data.get("model") or ""), state=state, urls=urls,
        credits_consumed=data.get("creditsConsumed") if "creditsConsumed" in data else data.get("credits_consumed"),
        fail_code=str(data.get("failCode") or data.get("fail_code") or ""),
        fail_message=str(data.get("failMsg") or data.get("fail_message") or ""),
        raw=payload,
    )


class KieClient:
    def __init__(self, api_key: str, *, session: Any = None, api_base: str = API_BASE, upload_base: str = UPLOAD_BASE, timeout: float = 60, max_retries: int = 3, max_upload_bytes: int = 1_000_000_000, max_download_bytes: int = 2_000_000_000):
        if not api_key:
            raise KieApiError("KIE_API_KEY is not set")
        self.api_key = api_key
        self.session = session or requests.Session()
        self.api_base = api_base.rstrip("/")
        self.upload_base = upload_base.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_upload_bytes = max_upload_bytes
        self.max_download_bytes = max_download_bytes

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def _request(self, method: str, path: str, *, retries: int | None = None, request_timeout: float | None = None, **kwargs: Any) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        headers = dict(self.auth_headers)
        headers.update(kwargs.pop("headers", {}))
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        last_error: Exception | None = None
        retry_count = self.max_retries if retries is None else max(0, retries)
        for attempt in range(retry_count + 1):
            try:
                for file_tuple in kwargs.get("files", {}).values():
                    if len(file_tuple) > 1 and hasattr(file_tuple[1], "seek"):
                        file_tuple[1].seek(0)
                response = self.session.request(method, url, headers=headers, timeout=request_timeout or self.timeout, **kwargs)
                if response.status_code in RETRYABLE_STATUS and attempt < retry_count:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                if response.status_code >= 400:
                    try: payload = response.json()
                    except Exception: payload = {"msg": response.text[:500]}
                    raise KieApiError(payload.get("msg") or f"HTTP {response.status_code}", response.status_code, payload)
                try: payload = response.json()
                except Exception as exc: raise KieApiError("KIE returned a non-JSON response") from exc
                code = payload.get("code") if isinstance(payload, dict) else None
                if isinstance(code, int) and code != 200:
                    raise KieApiError(str(payload.get("msg") or f"KIE error {code}"), code, payload)
                if isinstance(payload, dict) and payload.get("success") is False:
                    raise KieApiError(str(payload.get("msg") or "KIE request failed"), code, payload)
                return payload
            except KieApiError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < retry_count:
                    time.sleep(min(2 ** attempt, 8))
                    continue
        raise KieApiError(f"KIE request failed: {last_error}")

    def credits(self) -> int:
        payload = self._request("GET", "/api/v1/chat/credit")
        return int(payload["data"])

    def create_task(self, model: str, input_data: dict[str, Any], callback_url: str | None = None) -> tuple[str, dict[str, Any]]:
        body: dict[str, Any] = {"model": model, "input": input_data}
        if callback_url: body["callBackUrl"] = callback_url
        # Task creation is billable and non-idempotent. Retrying after an
        # ambiguous network failure could create duplicate paid tasks.
        payload = self._request("POST", "/api/v1/jobs/createTask", json=body, retries=0)
        data = payload.get("data") or {}
        task_id = data.get("taskId") or data.get("task_id") or payload.get("taskId")
        if not task_id:
            raise KieApiError("KIE accepted the request but returned no taskId", payload=payload)
        return str(task_id), payload

    def get_task(self, task_id: str, *, request_timeout: float | None = None, retries: int | None = None) -> dict[str, Any]:
        return self._request("GET", "/api/v1/jobs/recordInfo", params={"taskId": task_id}, request_timeout=request_timeout, retries=retries)

    def wait(self, task_id: str, *, timeout: float = 900, interval: float = 2) -> TaskResult:
        validate_wait_options(timeout, interval)
        deadline = time.monotonic() + timeout
        delay = max(0.0, interval)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise KieApiError(f"Timed out waiting for task {task_id} after {timeout:g}s")
            # Bound every poll to the remaining wait budget. Poll retries are
            # disabled here so retry sleeps cannot silently overrun it.
            try:
                result = parse_result(self.get_task(task_id, request_timeout=min(self.timeout, remaining), retries=0))
            except KieApiError as exc:
                if exc.code is not None and exc.code not in RETRYABLE_STATUS:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise KieApiError(f"Timed out waiting for task {task_id} after {timeout:g}s") from exc
                if delay: time.sleep(min(delay, remaining))
                delay = min(max(interval, delay * 1.35), 10.0)
                continue
            if result.state in SUCCESS_STATES:
                return result
            if result.state in FAIL_STATES:
                raise KieApiError(result.fail_message or f"Task {task_id} failed", payload=result.raw)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise KieApiError(f"Timed out waiting for task {task_id} after {timeout:g}s")
            if delay: time.sleep(min(delay, remaining))
            delay = min(max(interval, delay * 1.35), 10.0)

    def upload_file(self, path: str | Path, upload_path: str = "kie-media/uploads", *, expected_kind: str | None = None) -> str:
        file_path = Path(path).expanduser().resolve()
        if not file_path.is_file():
            raise KieApiError(f"Media file not found: {file_path}")
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        size = file_path.stat().st_size
        if size <= 0:
            raise KieApiError(f"Media file is empty: {file_path}")
        if size > self.max_upload_bytes:
            raise KieApiError(f"Media file exceeds upload safety limit ({self.max_upload_bytes} bytes): {file_path}")
        if expected_kind and not mime.startswith(f"{expected_kind}/"):
            raise KieApiError(f"Expected {expected_kind} media, got {mime}: {file_path}")
        if not _media_signature_valid(file_path, mime):
            raise KieApiError(f"Unsupported or invalid media file ({mime}): {file_path}")
        with file_path.open("rb") as handle:
            payload = self._request(
                "POST", f"{self.upload_base}/api/file-stream-upload",
                files={"file": (file_path.name, handle, mime)},
                data={"uploadPath": upload_path, "fileName": file_path.name},
            )
        data = payload.get("data") or {}
        url = data.get("downloadUrl") or data.get("download_url") or data.get("url")
        if not url:
            raise KieApiError("KIE upload returned no downloadUrl", payload=payload)
        return str(url)

    def resolve_media(self, value: str, expected_kind: str | None = None) -> str:
        if value.startswith(("https://", "http://")):
            guessed = mimetypes.guess_type(urlparse(value).path)[0]
            if expected_kind and guessed and not guessed.startswith(f"{expected_kind}/"):
                raise KieApiError(f"Expected {expected_kind} media URL, got {guessed}: {value}")
            return value
        return self.upload_file(value, expected_kind=expected_kind)

    def download_urls(self, urls: list[str], output_dir: str | Path, *, task_id: str = "result") -> list[str]:
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        ext_by_type = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "video/mp4": ".mp4", "video/webm": ".webm", "audio/mpeg": ".mp3", "audio/wav": ".wav"}
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", task_id)[:80] or "result"
        for index, url in enumerate(urls, start=1):
            response = None
            partial: Path | None = None
            try:
                response = self.session.get(url, timeout=self.timeout, stream=True)
                if response.status_code >= 400:
                    raise KieApiError(f"Download failed with HTTP {response.status_code}: {url}", response.status_code)
                announced = response.headers.get("content-length")
                if announced and int(announced) > self.max_download_bytes:
                    raise KieApiError(f"Download exceeds safety limit ({self.max_download_bytes} bytes): {url}")
                suffix = Path(urlparse(url).path).suffix.lower()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if not suffix or len(suffix) > 8:
                    suffix = ext_by_type.get(content_type) or mimetypes.guess_extension(content_type) or ".bin"
                effective_mime = content_type
                if effective_mime in {"", "application/octet-stream", "binary/octet-stream"}:
                    effective_mime = mimetypes.guess_type(f"x{suffix}")[0] or effective_mime
                if not (effective_mime.startswith("image/") or effective_mime.startswith("video/") or effective_mime.startswith("audio/")):
                    raise KieApiError(f"Download is not recognized media ({content_type or 'missing content-type'}): {url}")
                target = directory / f"{safe_id}-{index}{suffix}"
                partial = directory / f".{target.name}.{uuid.uuid4().hex}.part"
                written = 0
                fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > self.max_download_bytes:
                            raise KieApiError(f"Download exceeds safety limit ({self.max_download_bytes} bytes): {url}")
                        handle.write(chunk)
                if written == 0 or not _media_signature_valid(partial, effective_mime):
                    raise KieApiError(f"Downloaded file is empty or invalid {effective_mime}: {url}")
                os.replace(partial, target)
                os.chmod(target, 0o600)
                paths.append(str(target))
            except KieApiError:
                if partial: partial.unlink(missing_ok=True)
                raise
            except Exception as exc:
                if partial: partial.unlink(missing_ok=True)
                raise KieApiError(f"Download failed: {exc}") from exc
            finally:
                close = getattr(response, "close", None)
                if callable(close): close()
        return paths
