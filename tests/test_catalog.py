import os
import json
import stat
import tempfile
import unittest
from pathlib import Path

from kie_media.catalog import CatalogError, DocsCatalog
from kie_media.models import prepare_model_input


LLMS = """# docs.kie.ai

## API Docs
- Image Models > Seedream [Seedream5.0 Pro - Text to Image](https://docs.kie.ai/market/seedream/5-pro-text-to-image.md): High-quality image generation
- Video Models > Bytedance [Bytedance Seedance 2.0 Mini](https://docs.kie.ai/market/bytedance/seedance-2-mini.md): Fast video generation
- Image Models > Unsafe [External Model](https://evil.example/model.md): must never be fetched
- Image Models > Seedream [中文模型](https://docs.kie.ai/cn/market/seedream/5-pro-text-to-image.md): translated duplicate
"""

SEEDREAM_DOC = """# Seedream5.0 Pro - Text to Image

## OpenAPI Specification

```yaml
openapi: 3.0.1
paths:
  /api/v1/jobs/createTask:
    post:
      summary: Seedream5.0 Pro - Text to Image
      description: High-quality photorealistic image generation.
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                  enum: [seedream/5-pro-text-to-image]
                  default: seedream/5-pro-text-to-image
                input:
                  type: object
                  required: [prompt, aspect_ratio, quality]
                  properties:
                    prompt:
                      type: string
                      minLength: 3
                      maxLength: 5000
                    aspect_ratio:
                      type: string
                      enum: ['1:1', '16:9']
                      default: '1:1'
                    quality:
                      type: string
                      enum: [basic, high]
                      default: basic
                    seed:
                      type: integer
                      minimum: 0
                      maximum: 2147483647
                    image_urls:
                      type: array
                      maxItems: 10
                      items: {type: string}
```
"""

SEEDANCE_DOC = """# Bytedance Seedance 2.0 Mini

```yaml
openapi: 3.0.1
paths:
  /api/v1/jobs/createTask:
    post:
      summary: Bytedance Seedance 2.0 Mini
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                  default: bytedance/seedance-2-mini
                input:
                  type: object
                  required: [prompt]
                  properties:
                    prompt: {type: string, minLength: 3, maxLength: 20000}
                    first_frame_url: {type: string}
                    duration: {type: integer, minimum: 4, maximum: 15, default: 5}
                    resolution: {type: string, enum: [480p, 720p], default: 720p}
```
"""


class FakeResponse:
    def __init__(self, text, status=200, content_type="text/plain"):
        self.text = text
        self.content = text.encode()
        self.status_code = status
        self.headers = {"content-type": content_type, "content-length": str(len(self.content))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.get(url)
        if isinstance(response, Exception):
            raise response
        if response is None:
            return FakeResponse("missing", 404)
        return response


class CatalogTests(unittest.TestCase):
    def make_catalog(self, root, session):
        return DocsCatalog(cache_dir=Path(root), session=session, ttl_seconds=3600, now=lambda: 1000)

    def test_search_discovers_english_kie_models_and_ignores_translated_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            session = FakeSession({DocsCatalog.INDEX_URL: FakeResponse(LLMS)})
            catalog = self.make_catalog(td, session)
            rows = catalog.search("Seedream 5 Pro", kind="image", refresh=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].title, "Seedream5.0 Pro - Text to Image")
        self.assertEqual(rows[0].kind, "image")

    def test_named_model_fetches_openapi_schema_and_validates_without_api_key(self):
        url = "https://docs.kie.ai/market/seedream/5-pro-text-to-image.md"
        with tempfile.TemporaryDirectory() as td:
            session = FakeSession({DocsCatalog.INDEX_URL: FakeResponse(LLMS), url: FakeResponse(SEEDREAM_DOC, content_type="text/markdown")})
            spec = self.make_catalog(td, session).resolve("Seedream 5 Pro", kind="image", refresh=True)
            payload = prepare_model_input(spec, {"prompt": "A product image"})
        self.assertEqual(spec.id, "seedream/5-pro-text-to-image")
        self.assertEqual(spec.kind, "image")
        self.assertEqual(payload["aspect_ratio"], "1:1")
        self.assertEqual(payload["quality"], "basic")
        with self.assertRaisesRegex(ValueError, "Invalid quality"):
            prepare_model_input(spec, {"prompt": "A product image", "quality": "ultra"})

    def test_cache_supports_offline_resolution_by_title_and_model_id(self):
        url = "https://docs.kie.ai/market/bytedance/seedance-2-mini.md"
        with tempfile.TemporaryDirectory() as td:
            first = FakeSession({DocsCatalog.INDEX_URL: FakeResponse(LLMS), url: FakeResponse(SEEDANCE_DOC)})
            catalog = self.make_catalog(td, first)
            resolved = catalog.resolve("Seedance 2 Mini", kind="video", refresh=True)
            offline = DocsCatalog(cache_dir=Path(td), session=FakeSession({DocsCatalog.INDEX_URL: OSError("offline")}), ttl_seconds=0, now=lambda: 2000)
            by_title = offline.resolve("Seedance 2 Mini", kind="video")
            by_id = offline.cached_model("bytedance/seedance-2-mini")
            mode = stat.S_IMODE((Path(td) / "models.json").stat().st_mode)
        self.assertEqual(resolved.id, by_title.id)
        self.assertEqual(by_id.id, resolved.id)
        if os.name != "nt":
            self.assertEqual(mode, 0o600)

    def test_external_document_url_is_never_fetched(self):
        with tempfile.TemporaryDirectory() as td:
            session = FakeSession({DocsCatalog.INDEX_URL: FakeResponse(LLMS), "https://evil.example/model.md": FakeResponse(SEEDREAM_DOC)})
            catalog = self.make_catalog(td, session)
            with self.assertRaises(CatalogError):
                catalog.resolve("External Model", refresh=True)
        self.assertNotIn("https://evil.example/model.md", [call[0] for call in session.calls])

    def test_reference_context_disambiguates_image_to_image_variant(self):
        index = LLMS + "\n- Image Models > Seedream [Seedream5.0 Pro - Image to Image](https://docs.kie.ai/market/seedream/5-pro-image-to-image.md): edit\n"
        url = "https://docs.kie.ai/market/seedream/5-pro-image-to-image.md"
        edit_doc = SEEDREAM_DOC.replace("seedream/5-pro-text-to-image", "seedream/5-pro-image-to-image")
        with tempfile.TemporaryDirectory() as td:
            session = FakeSession({DocsCatalog.INDEX_URL: FakeResponse(index), url: FakeResponse(edit_doc)})
            spec = self.make_catalog(td, session).resolve("Seedream 5 Pro", kind="image", needs_reference=True, refresh=True)
        self.assertEqual(spec.id, "seedream/5-pro-image-to-image")

    def test_failed_refresh_uses_last_validated_model_cache(self):
        url = "https://docs.kie.ai/market/seedream/5-pro-text-to-image.md"
        with tempfile.TemporaryDirectory() as td:
            first = FakeSession({DocsCatalog.INDEX_URL: FakeResponse(LLMS), url: FakeResponse(SEEDREAM_DOC)})
            self.make_catalog(td, first).resolve("Seedream 5 Pro", refresh=True)
            failed = FakeSession({DocsCatalog.INDEX_URL: FakeResponse(LLMS), url: OSError("offline")})
            spec = self.make_catalog(td, failed).resolve("Seedream 5 Pro", refresh=True)
        self.assertEqual(spec.id, "seedream/5-pro-text-to-image")

    def test_remote_yaml_aliases_are_rejected(self):
        url = "https://docs.kie.ai/market/seedream/5-pro-text-to-image.md"
        unsafe = SEEDREAM_DOC.replace("openapi: 3.0.1", "openapi: &version 3.0.1\ncopy: *version")
        with tempfile.TemporaryDirectory() as td:
            session = FakeSession({DocsCatalog.INDEX_URL: FakeResponse(LLMS), url: FakeResponse(unsafe)})
            with self.assertRaisesRegex(CatalogError, "aliases are disabled"):
                self.make_catalog(td, session).resolve("Seedream 5 Pro", refresh=True)

    def test_ambiguous_or_non_generation_docs_do_not_become_paid_models(self):
        duplicate = LLMS + "\n- Image Models > Seedream [Seedream 5 Pro Text to Image Alt](https://docs.kie.ai/market/seedream/5-pro-text-alt.md): alternate\n"
        with tempfile.TemporaryDirectory() as td:
            catalog = self.make_catalog(td, FakeSession({DocsCatalog.INDEX_URL: FakeResponse(duplicate)}))
            with self.assertRaisesRegex(CatalogError, "Ambiguous"):
                catalog.resolve("Seedream 5 Pro", refresh=True)


if __name__ == "__main__":
    unittest.main()
