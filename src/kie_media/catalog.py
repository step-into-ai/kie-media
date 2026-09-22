from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
import yaml
from jsonschema import Draft202012Validator
from yaml.events import AliasEvent

from .models import FieldSpec, ModelSpec
from .storage import atomic_json


class CatalogError(ValueError):
    pass


class _NoAliasSafeLoader(yaml.SafeLoader):
    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            raise yaml.YAMLError("YAML aliases are disabled for remote documentation")
        return super().compose_node(parent, index)


@dataclass(frozen=True)
class CatalogEntry:
    title: str
    url: str
    kind: str
    category: str
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CatalogEntry":
        return cls(
            title=str(value["title"]),
            url=str(value["url"]),
            kind=str(value.get("kind") or "other"),
            category=str(value.get("category") or ""),
            description=str(value.get("description") or ""),
        )


def default_cache_home() -> Path:
    override = os.environ.get("KIE_MEDIA_CACHE_HOME")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "kie-media"


def _normalize(value: str) -> str:
    value = re.sub(r"(?<=\d)\.0\b", "", value.casefold())
    value = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", value)
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _spec_to_dict(spec: ModelSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "name": spec.name,
        "kind": spec.kind,
        "description": spec.description,
        "aliases": list(spec.aliases),
        "docs": spec.docs,
        "input_schema": spec.input_schema,
        "family": spec.family,
        "endpoint": spec.endpoint,
        "fields": {
            name: {
                "type": field.type.__name__,
                "required": field.required,
                "default": field.default,
                "enum": list(field.enum),
                "minimum": field.minimum,
                "maximum": field.maximum,
                "min_items": field.min_items,
                "max_items": field.max_items,
                "min_length": field.min_length,
                "max_length": field.max_length,
            }
            for name, field in spec.fields.items()
        },
    }


def _spec_from_dict(value: dict[str, Any]) -> ModelSpec:
    types = {"str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict}
    fields: dict[str, FieldSpec] = {}
    for name, raw in dict(value.get("fields") or {}).items():
        type_name = str(raw.get("type") or "str")
        if type_name not in types:
            raise CatalogError(f"Unsupported cached field type: {type_name}")
        fields[str(name)] = FieldSpec(
            types[type_name],
            required=bool(raw.get("required")),
            default=raw.get("default"),
            enum=tuple(raw.get("enum") or ()),
            minimum=raw.get("minimum"),
            maximum=raw.get("maximum"),
            min_items=raw.get("min_items"),
            max_items=raw.get("max_items"),
            min_length=raw.get("min_length"),
            max_length=raw.get("max_length"),
        )
    return ModelSpec(
        id=str(value["id"]),
        name=str(value.get("name") or value["id"]),
        kind=str(value.get("kind") or "custom"),
        description=str(value.get("description") or ""),
        aliases=tuple(str(item) for item in value.get("aliases") or ()),
        fields=fields,
        docs=str(value.get("docs") or ""),
        input_schema=dict(value.get("input_schema") or {}),
        family=str(value.get("family") or "task"),
        endpoint=str(value.get("endpoint") or "/api/v1/jobs/createTask"),
    )


def _atomic_private_json(path: Path, value: Any) -> None:
    atomic_json(path, value)


def _merge_schema(parts: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for part in parts:
        for key, value in part.items():
            if key == "properties":
                result.setdefault("properties", {}).update(value or {})
            elif key == "required":
                result["required"] = list(dict.fromkeys([*result.get("required", []), *(value or [])]))
            else:
                result[key] = value
    return result


def _resolve_schema(node: Any, root: dict[str, Any], depth: int = 0) -> Any:
    if depth > 20:
        raise CatalogError("OpenAPI schema reference depth exceeded")
    if isinstance(node, list):
        return [_resolve_schema(item, root, depth + 1) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        ref = str(node["$ref"])
        if not ref.startswith("#/"):
            raise CatalogError("External OpenAPI references are not allowed")
        target: Any = root
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                raise CatalogError(f"Unresolved OpenAPI reference: {ref}")
            target = target[part]
        merged = _resolve_schema(target, root, depth + 1)
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        return _merge_schema([merged, _resolve_schema(siblings, root, depth + 1)]) if siblings else merged
    resolved = {key: _resolve_schema(value, root, depth + 1) for key, value in node.items()}
    if "allOf" in resolved:
        all_of = resolved.pop("allOf")
        return _merge_schema([resolved, *all_of])
    return resolved


class DocsCatalog:
    INDEX_URL = "https://docs.kie.ai/llms.txt"
    MAX_INDEX_BYTES = 2_000_000
    MAX_DOCUMENT_BYTES = 3_000_000

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        session: Any = None,
        ttl_seconds: int = 86_400,
        timeout: float = 30,
        now: Callable[[], float] | None = None,
    ):
        self.cache_dir = (cache_dir or default_cache_home()).expanduser()
        self.index_path = self.cache_dir / "index.json"
        self.models_path = self.cache_dir / "models.json"
        self.session = session or requests.Session()
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.timeout = timeout
        self.now = now or time.time

    @staticmethod
    def _trusted_document_url(url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "docs.kie.ai"
            and parsed.port is None
            and not parsed.username
            and not parsed.password
            and parsed.path.startswith("/")
            and parsed.path.endswith(".md")
            and not parsed.path.startswith("/cn/")
            and not parsed.query
            and not parsed.fragment
        )

    def _fetch_text(self, url: str, maximum: int, _attempt: int = 0) -> str:
        if url != self.INDEX_URL and not self._trusted_document_url(url):
            raise CatalogError(f"Refusing untrusted KIE documentation URL: {url}")
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=False,
                headers={"Accept": "text/plain, text/markdown;q=0.9"},
            )
            if 300 <= int(response.status_code) < 400:
                raise CatalogError("KIE documentation redirects are not followed")
            response.raise_for_status()
        except CatalogError:
            raise
        except Exception as exc:
            raise CatalogError(f"Unable to fetch KIE documentation: {type(exc).__name__}: {exc}") from exc
        announced = response.headers.get("content-length")
        if announced:
            try:
                if int(announced) > maximum:
                    raise CatalogError("KIE documentation response exceeds safety limit")
            except ValueError:
                raise CatalogError("Invalid KIE documentation content-length")
        content = bytes(response.content)
        if len(content) > maximum:
            raise CatalogError("KIE documentation response exceeds safety limit")
        content_type = str(response.headers.get("content-type") or "").casefold()
        if content_type and not any(item in content_type for item in ("text/plain", "text/markdown", "application/octet-stream")):
            if "text/html" in content_type and _attempt < 2:
                time.sleep(0.2)
                return self._fetch_text(url, maximum, _attempt + 1)
            raise CatalogError(f"Unexpected KIE documentation content type: {content_type}")
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CatalogError("KIE documentation is not valid UTF-8") from exc

    @staticmethod
    def _parse_index(text: str) -> list[CatalogEntry]:
        pattern = re.compile(r"^-\s+(.+?)\s+\[([^\]]+)\]\((https://[^)]+)\):\s*(.*)$")
        entries: list[CatalogEntry] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            match = pattern.match(raw_line.strip())
            if not match:
                continue
            category, title, url, description = match.groups()
            if "/cn/" in url or url in seen:
                continue
            category_folded = category.casefold()
            if "image" in category_folded:
                kind = "image"
            elif "video" in category_folded:
                kind = "video"
            elif "audio" in category_folded or "music" in category_folded or "voice" in category_folded:
                kind = "audio"
            elif "3d" in category_folded:
                kind = "3d"
            elif "chat" in category_folded or "llm" in category_folded:
                kind = "chat"
            else:
                kind = "other"
            entries.append(CatalogEntry(title.strip(), url, kind, category.strip(), description.strip()))
            seen.add(url)
        if not entries:
            raise CatalogError("KIE model index contained no documentation entries")
        return entries

    def _read_index_cache(self) -> tuple[float, list[CatalogEntry]]:
        if not self.index_path.is_file():
            return 0.0, []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return float(payload.get("fetched_at") or 0), [CatalogEntry.from_dict(row) for row in payload.get("entries") or []]
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return 0.0, []

    def _entries(self, refresh: bool = False) -> list[CatalogEntry]:
        fetched_at, cached = self._read_index_cache()
        fresh = cached and self.now() - fetched_at <= self.ttl_seconds
        if cached and fresh and not refresh:
            return cached
        try:
            entries = self._parse_index(self._fetch_text(self.INDEX_URL, self.MAX_INDEX_BYTES))
            _atomic_private_json(
                self.index_path,
                {"version": 1, "source": self.INDEX_URL, "fetched_at": self.now(), "entries": [entry.to_dict() for entry in entries]},
            )
            return entries
        except CatalogError:
            if cached:
                return cached
            raise

    @staticmethod
    def _score(entry: CatalogEntry, query: str) -> int:
        needle = _normalize(query)
        title = _normalize(entry.title)
        url = _normalize(urlparse(entry.url).path)
        if not needle:
            return 1
        if needle == title:
            return 1000
        if title.startswith(needle):
            return 900
        if needle in title:
            return 800
        query_tokens = set(needle.split())
        title_tokens = set(title.split()) | set(url.split())
        if query_tokens and query_tokens <= title_tokens:
            return 700 + len(query_tokens)
        overlap = len(query_tokens & title_tokens)
        return overlap * 10 if overlap else 0

    def search(self, query: str = "", *, kind: str | None = None, refresh: bool = False) -> list[CatalogEntry]:
        rows = [entry for entry in self._entries(refresh) if (not kind or entry.kind == kind)]
        ranked = [(self._score(entry, query), entry) for entry in rows]
        ranked = [item for item in ranked if item[0] > 0]
        # A concrete multi-token name should not be buried in every catalog
        # entry sharing one generic token (for example "Pro" or "Image").
        # Keep broad one-word discovery broad, but collapse strong phrase
        # matches to the equally relevant workflow variants.
        if len(_normalize(query).split()) >= 2 and ranked:
            best = max(score for score, _ in ranked)
            if best >= 800:
                ranked = [item for item in ranked if item[0] == best]
        ranked.sort(key=lambda item: (-item[0], item[1].title.casefold(), item[1].url))
        return [entry for _, entry in ranked]

    def _read_models(self) -> list[ModelSpec]:
        if not self.models_path.is_file():
            return []
        try:
            payload = json.loads(self.models_path.read_text(encoding="utf-8"))
            return [_spec_from_dict(row) for row in payload.get("models") or []]
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, CatalogError):
            return []

    @staticmethod
    def _accepts_image_reference(spec: ModelSpec) -> bool:
        return bool({"image_url", "image_urls", "first_frame_url", "reference_image_urls"}.intersection(spec.fields))

    def cached_model(
        self,
        name: str,
        *,
        kind: str | None = None,
        needs_reference: bool | None = None,
    ) -> ModelSpec | None:
        needle = _normalize(name)
        models = self._read_models()
        exact: list[ModelSpec] = []
        partial: list[ModelSpec] = []
        for spec in models:
            keys = (spec.id, spec.name, *spec.aliases)
            if any(name == key or needle == _normalize(key) for key in keys):
                exact.append(spec)
            elif any(needle and needle in _normalize(key) for key in keys):
                partial.append(spec)
        candidates = exact or partial
        if kind:
            candidates = [spec for spec in candidates if spec.kind == kind]
        if needs_reference is True:
            candidates = [spec for spec in candidates if self._accepts_image_reference(spec)]
        elif needs_reference is False and len(candidates) > 1:
            without_reference = [spec for spec in candidates if not self._accepts_image_reference(spec)]
            if without_reference:
                candidates = without_reference
        unique = {spec.id: spec for spec in candidates}
        return next(iter(unique.values())) if len(unique) == 1 else None

    def _save_model(self, spec: ModelSpec) -> None:
        models = {item.id: item for item in self._read_models()}
        models[spec.id] = spec
        _atomic_private_json(
            self.models_path,
            {"version": 1, "updated_at": self.now(), "models": [_spec_to_dict(models[key]) for key in sorted(models)]},
        )

    @staticmethod
    def _extract_model(entry: CatalogEntry, text: str) -> ModelSpec:
        documents = re.findall(r"```ya?ml\s*\n(.*?)\n```", text, flags=re.DOTALL | re.IGNORECASE)
        root: dict[str, Any] | None = None
        endpoint = "/api/v1/jobs/createTask"
        family = "task"
        for document in documents:
            try:
                parsed = yaml.load(document, Loader=_NoAliasSafeLoader)
            except yaml.YAMLError as exc:
                raise CatalogError(f"Invalid OpenAPI YAML for {entry.title}: {exc}") from exc
            if isinstance(parsed, dict):
                for candidate in dict(parsed.get("paths") or {}):
                    if candidate == "/api/v1/jobs/createTask":
                        root, endpoint, family = parsed, candidate, "task"
                        break
                    if re.fullmatch(r"/[A-Za-z0-9._-]+/v1/chat/completions", candidate):
                        root, endpoint, family = parsed, candidate, "chat"
                        break
                    if candidate in {"/codex/v1/responses", "/api/v1/responses"}:
                        root, endpoint, family = parsed, candidate, "responses"
                        break
                    if candidate == "/claude/v1/messages":
                        root, endpoint, family = parsed, candidate, "messages"
                        break
                    if re.fullmatch(r"/gemini/v1/models/[A-Za-z0-9._-]+:(?:streamGenerateContent|generateContent)", candidate):
                        root, endpoint, family = parsed, candidate, "gemini"
                        break
                if root is not None:
                    break
        if root is None:
            raise CatalogError(f"{entry.title} has no supported task/chat/responses endpoint")
        post = root["paths"][endpoint].get("post") or {}
        try:
            body = post["requestBody"]["content"]["application/json"]["schema"]
        except (KeyError, TypeError) as exc:
            raise CatalogError(f"{entry.title} has no usable createTask request schema") from exc
        body = _resolve_schema(body, root)
        properties = dict(body.get("properties") or {})
        model_schema = _resolve_schema(properties.get("model") or {}, root)
        model_id = model_schema.get("const") or model_schema.get("default")
        if not model_id and len(model_schema.get("enum") or []) == 1:
            model_id = model_schema["enum"][0]
        if not model_id and not model_schema.get("enum"):
            model_id = model_schema.get("example")
            if not model_id and len(model_schema.get("examples") or []) == 1:
                model_id = model_schema["examples"][0]
        if family == "chat" and not model_schema:
            model_id = endpoint.split("/")[1]
        if family == "gemini" and not model_schema:
            model_id = endpoint.rsplit("/", 1)[1].split(":")[0]
        multiple_variants = family != "task" and not model_id and len(model_schema.get("enum") or []) > 1
        if multiple_variants:
            model_id = post.get("operationId") or _normalize(entry.title).replace(" ", "-")
        input_schema = _resolve_schema(properties.get("input") or {}, root) if family == "task" else body
        if not isinstance(model_id, str) or not model_id.strip() or not isinstance(input_schema, dict):
            raise CatalogError(f"{entry.title} has no trustworthy model ID or input schema")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_.:-]{0,199}", model_id):
            raise CatalogError("Invalid documented model selector")
        if family != "task" and "model" in properties and not multiple_variants:
            input_schema["properties"]["model"] = {**model_schema, "const": model_id, "default": model_id}
        input_properties = dict(input_schema.get("properties") or {})
        for combination in ("oneOf", "anyOf"):
            for variant in input_schema.get(combination, []):
                for name, contract in variant.get("properties", {}).items():
                    input_properties.setdefault(name, contract)
        # Keep alternatives intact. The union at the envelope only rejects
        # unknown names; required/type constraints still belong to each branch.
        if not input_schema.get("properties") and input_properties:
            input_schema["properties"] = {name: {} for name in input_properties}
        required = {str(item) for item in input_schema.get("required") or []}
        type_map = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}
        fields: dict[str, FieldSpec] = {}
        for name, raw_schema in input_properties.items():
            schema = _resolve_schema(raw_schema, root)
            raw_type = schema.get("type")
            if isinstance(raw_type, list):
                raw_type = next((item for item in raw_type if item != "null"), None)
            field_type = type_map.get(raw_type)
            if field_type is None:
                continue
            fields[str(name)] = FieldSpec(
                field_type,
                required=str(name) in required,
                default=schema.get("default"),
                enum=tuple(schema.get("enum") or ()),
                minimum=schema.get("minimum"),
                maximum=schema.get("maximum"),
                min_items=schema.get("minItems"),
                max_items=schema.get("maxItems"),
                min_length=schema.get("minLength"),
                max_length=schema.get("maxLength"),
            )
        if not input_properties:
            raise CatalogError(f"{entry.title} does not expose a usable input contract")
        input_schema.setdefault("additionalProperties", False)
        try:
            Draft202012Validator.check_schema(input_schema)
        except Exception as exc:
            raise CatalogError(f"Invalid input schema for {entry.title}: {exc}") from exc
        description = str(post.get("description") or entry.description or "").strip()
        description = " ".join(description.split())[:500]
        name = str(post.get("summary") or entry.title).strip()
        return ModelSpec(
            id=model_id.strip(),
            name=name,
            kind="chat" if family != "task" else entry.kind,
            description=description,
            aliases=(entry.title,),
            fields=fields,
            docs=entry.url.removesuffix(".md"),
            input_schema=input_schema,
            family=family,
            endpoint=endpoint,
        )

    @staticmethod
    def _mode_rank(entry: CatalogEntry, needs_reference: bool | None) -> int:
        title = _normalize(entry.title)
        reference_terms = ("image to image", "image to video", "edit", "reference")
        text_terms = ("text to image", "text to video")
        if needs_reference is True:
            if any(term in title for term in reference_terms):
                return 0
            if any(term in title for term in text_terms):
                return 2
            return 1
        # Without explicit context, prefer the text-only generation variant;
        # callers with reference media pass needs_reference=True.
        if any(term in title for term in text_terms):
            return 0
        if any(term in title for term in reference_terms):
            return 2
        return 1

    def resolve(
        self,
        query: str,
        *,
        kind: str | None = None,
        refresh: bool = False,
        needs_reference: bool | None = None,
    ) -> ModelSpec:
        cached = self.cached_model(query, kind=kind, needs_reference=needs_reference)
        if not refresh:
            if cached:
                return cached
        try:
            matches = self.search(query, kind=kind, refresh=refresh)
        except CatalogError:
            if cached:
                return cached
            raise
        if not matches:
            if cached:
                return cached
            raise CatalogError(f"No KIE model documentation matched: {query}")
        best_score = self._score(matches[0], query)
        tied = [entry for entry in matches if self._score(entry, query) == best_score]
        if len(tied) > 1:
            best_mode = min(self._mode_rank(entry, needs_reference) for entry in tied)
            tied = [entry for entry in tied if self._mode_rank(entry, needs_reference) == best_mode]
        if len(tied) > 1:
            names = ", ".join(entry.title for entry in tied[:5])
            raise CatalogError(f"Ambiguous KIE model name {query!r}; matches: {names}")
        entry = tied[0]
        if not self._trusted_document_url(entry.url):
            raise CatalogError(f"Refusing untrusted KIE documentation URL: {entry.url}")
        try:
            spec = self._extract_model(entry, self._fetch_text(entry.url, self.MAX_DOCUMENT_BYTES))
        except CatalogError:
            if cached:
                return cached
            raise
        if kind and spec.kind != kind:
            raise CatalogError(f"Requested {kind} model, but KIE documents {spec.name} as {spec.kind}")
        self._save_model(spec)
        return spec
