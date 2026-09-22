"""Documented KIE language transports. One submission, never automatic retry."""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from .client import KieApiError, KieClient
from .models import ModelSpec, prepare_model_input


def complete(client: KieClient, spec: ModelSpec, values: dict[str, Any],
             on_event: Callable[[dict], None] | None = None) -> dict:
    endpoint = spec.endpoint
    if not ((spec.family == "responses" and endpoint in {"/codex/v1/responses", "/api/v1/responses"}) or
            (spec.family == "chat" and re.fullmatch(r"/[A-Za-z0-9._-]+/v1/chat/completions", endpoint)) or
            (spec.family == "messages" and endpoint == "/claude/v1/messages") or
            (spec.family == "gemini" and re.fullmatch(r"/gemini/v1/models/[A-Za-z0-9._-]+:(?:streamGenerateContent|generateContent)", endpoint))):
        raise KieApiError("Unsupported language endpoint")
    body = prepare_model_input(spec, values)
    headers = {**client.auth_headers, "Content-Type": "application/json"}
    response = client.session.request("POST", client.api_base + endpoint,
        headers=headers,
        json=body, timeout=client.timeout, stream=True, allow_redirects=False)
    try:
        if not 200 <= response.status_code < 300:
            raise KieApiError(f"Language request HTTP {response.status_code}; not retried", response.status_code)
        if "text/event-stream" not in response.headers.get("content-type", "").lower():
            result = response.json()
            if isinstance(result, list) and spec.family == "gemini":
                parts = [part for chunk in result for c in chunk.get("candidates", []) for part in c.get("content", {}).get("parts", [])]
                if not any(c.get("finishReason") for chunk in result for c in chunk.get("candidates", [])):
                    raise KieApiError("Gemini chunk response did not finish")
                return {"chunks": result, "text": "".join(p.get("text", "") for p in parts if not p.get("thought")),
                        "status": "completed", "usage": result[-1].get("usageMetadata") if result else None}
            if (not isinstance(result, dict) or result.get("error") or result.get("status") in {"failed", "incomplete"}
                    or isinstance(result.get("code"), int) and result["code"] != 200):
                raise KieApiError("Language request failed or returned an invalid result", payload=result)
            return result
        events, text, terminal, result = 0, [], False, {}
        tool_events = []
        data_lines: list[str] = []

        def consume(raw: str) -> None:
            nonlocal events, terminal, result
            if raw == "[DONE]":
                terminal = True
                return
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise KieApiError("Invalid language stream event")
            events += 1
            if events > 100000:
                raise KieApiError("Language stream exceeds event limit")
            if event.get("error") or event.get("type") in {"error", "response.failed", "response.incomplete"}:
                raise KieApiError("Language stream failed; partial output is not complete", payload=event)
            if event.get("type") == "response.output_text.delta":
                text.append(str(event.get("delta", "")))
            delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
            if event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                text.append(event["delta"].get("text", ""))
            if ("function_call" in event.get("type", "") or event.get("content_block", {}).get("type") == "tool_use"
                    or delta.get("type") == "input_json_delta"):
                tool_events.append(event)
            if event.get("type") == "message_stop":
                terminal = True
            if event.get("type") == "message_start":
                result["id"] = event.get("message", {}).get("id")
                result["usage"] = event.get("message", {}).get("usage", {})
            for candidate in event.get("candidates", []):
                text.extend(part.get("text", "") for part in candidate.get("content", {}).get("parts", []) if not part.get("thought"))
                if any("functionCall" in part for part in candidate.get("content", {}).get("parts", [])):
                    tool_events.append(event)
                terminal = terminal or bool(candidate.get("finishReason"))
            for choice in event.get("choices", []):
                text.append(str(choice.get("delta", {}).get("content") or ""))
                if choice.get("delta", {}).get("tool_calls"):
                    tool_events.append(event)
                terminal = terminal or choice.get("finish_reason") is not None
            if event.get("type") == "response.completed":
                terminal = True
                result = event.get("response", {})
            if "usage" in event:
                result["usage"] = {**result.get("usage", {}), **(event["usage"] or {})}
            if "usageMetadata" in event:
                result["usage"] = event["usageMetadata"]
            if on_event:
                on_event(event)

        for line in response.iter_lines(decode_unicode=True):
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif not line and data_lines:
                consume("\n".join(data_lines))
                data_lines = []
        if data_lines:
            consume("\n".join(data_lines))
        if not terminal or not events:
            raise KieApiError("Language stream interrupted before completion; do not blindly resubmit")
        return {**result, "text": "".join(text), "tool_events": tool_events, "stream_events": events, "status": "completed"}
    finally:
        response.close()
