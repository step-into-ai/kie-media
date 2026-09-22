import unittest
from unittest.mock import Mock
from kie_media.catalog import CatalogEntry, DocsCatalog
from kie_media.client import KieClient, KieApiError
from kie_media.language import complete
from kie_media.models import ModelSpec


class LanguageTests(unittest.TestCase):
    def test_multi_model_responses_requires_explicit_variant(self):
        from kie_media.models import prepare_model_input, ModelValidationError
        doc = '''```yaml
paths:
  /api/v1/responses:
    post:
      operationId: gpt-codex-responses
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required: [model, input]
              properties:
                model: {type: string, enum: [codex-one, codex-two]}
                input: {type: string}
```'''
        spec = DocsCatalog._extract_model(CatalogEntry("Codex", "https://docs.kie.ai/market/codex/test.md", "chat", "chat"), doc)
        with self.assertRaises(ModelValidationError):
            prepare_model_input(spec, {"input": "Hello"})
        self.assertEqual(prepare_model_input(spec, {"model": "codex-two", "input": "Hello"})["model"], "codex-two")

    def test_endpoint_encoded_chat_contract(self):
        doc = '''```yaml
paths:
  /gemini-2.5-pro/v1/chat/completions:
    post:
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required: [messages]
              properties:
                messages: {type: array, minItems: 1, items: {type: object}}
                stream: {type: boolean, default: false}
```'''
        spec = DocsCatalog._extract_model(CatalogEntry("Gemini", "https://docs.kie.ai/market/chat/test.md", "chat", "chat"), doc)
        self.assertEqual(spec.id, "gemini-2.5-pro")
        self.assertEqual(spec.family, "chat")

    def response(self, lines):
        response = Mock(status_code=200, headers={"content-type": "text/event-stream"})
        response.iter_lines.return_value = lines
        return response

    def test_sse_completion_and_no_automatic_retry(self):
        response = self.response(['data: {"type":"response.output_text.delta","delta":"Hello"}', '',
                                  'data: {"type":"response.completed","response":{"id":"r1","usage":{"input_tokens":5}}}', ''])
        session = Mock()
        session.request.return_value = response
        spec = ModelSpec("gpt-test", "GPT", "chat", "", family="responses", endpoint="/codex/v1/responses")
        # Use an explicit contract; the language call must not depend on prompt validation.
        spec = ModelSpec("gpt-test", "GPT", "chat", "", input_schema={"type":"object"}, family="responses", endpoint="/codex/v1/responses")
        result = complete(KieClient("test", session=session), spec, {"input":"Hello"})
        self.assertEqual(result["text"], "Hello")
        self.assertEqual(result["usage"]["input_tokens"], 5)
        session.request.assert_called_once()
        response.close.assert_called_once()

    def test_interrupted_stream_is_not_completed(self):
        session = Mock()
        session.request.return_value = self.response(['data: {"type":"response.output_text.delta","delta":"Partial"}', ''])
        spec = ModelSpec("gpt-test", "GPT", "chat", "", input_schema={"type":"object"}, family="responses", endpoint="/codex/v1/responses")
        with self.assertRaisesRegex(KieApiError, "interrupted"):
            complete(KieClient("test", session=session), spec, {})
        session.request.assert_called_once()

    def test_untrusted_cached_endpoint_never_receives_credentials(self):
        session = Mock()
        spec = ModelSpec("evil", "Bad", "chat", "", family="chat", endpoint="https://evil.example/collect")
        with self.assertRaises(KieApiError):
            complete(KieClient("test", session=session), spec, {})
        session.request.assert_not_called()

    def test_native_gemini_stream_collects_text_and_usage(self):
        session = Mock()
        session.request.return_value = self.response([
            'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]},"finishReason":"STOP"}],"usageMetadata":{"totalTokenCount":4}}', ''])
        spec = ModelSpec("gemini-3-8-flash", "Gemini", "chat", "", input_schema={"type":"object"},
                         family="gemini", endpoint="/gemini/v1/models/gemini-3-8-flash:streamGenerateContent")
        result = complete(KieClient("test", session=session), spec, {"contents": []})
        self.assertEqual(result["text"], "Hello")
        self.assertEqual(result["usage"]["totalTokenCount"], 4)

    def test_native_claude_stream_requires_message_stop(self):
        session = Mock()
        session.request.return_value = self.response([
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}', '',
            'data: {"type":"message_stop"}', ''])
        spec = ModelSpec("claude-test", "Claude", "chat", "", input_schema={"type":"object"},
                         family="messages", endpoint="/claude/v1/messages")
        result = complete(KieClient("test", session=session), spec, {})
        self.assertEqual(result["text"], "Hi")
        self.assertEqual(session.request.call_args.kwargs["headers"]["Authorization"], "Bearer test")
        self.assertNotIn("anthropic-version", session.request.call_args.kwargs["headers"])
