from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import zlib
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
SCHEMA_PATH = ROOT / "schemas" / "public_mvp_scenario_pack.schema.json"
SITE_SCHEMA_PATH = SITE / "schemas" / "public_mvp_scenario_pack.schema.json"
PACK_PATH = SITE / "data" / "scenario-pack.json"
MANIFEST_PATH = SITE / "data" / "manifest.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "pages.yml"

EXPECTED_SITE_FILES = frozenset(
    {
        "404.html",
        "assets/app.js",
        "assets/favicon.svg",
        "assets/social-preview.png",
        "assets/styles.css",
        "data/manifest.json",
        "data/scenario-pack.json",
        "index.html",
        "schemas/public_mvp_scenario_pack.schema.json",
    }
)
EXPECTED_PACK_SHA256 = "e2a817f05b7d31ed9581bc12bdaa0e6096efc7d04817922be6c16629e0605016"
EXPECTED_MANIFEST_SHA256 = "c4b2b44bf1e645f6340ff63c8f6c530a997a853a86e8160601d06fb245efafac"
EXPECTED_SCHEMA_SHA256 = "ebd681856c3c79010c1425503274223f0deb4f3c6f746d8378c20c538f13c187"
EXPECTED_MANIFEST_CONTENT_SHA256 = (
    "871fd4e240f49442a03f5af81befa3db122c74904fb19b7906dd4498e0f7d3d6"
)
EXPECTED_PACK_BYTES = 560_314
EXPECTED_MANIFEST_BYTES = 883
EXPECTED_SCHEMA_BYTES = 14_649
EXPECTED_SCENARIOS = 27
EXPECTED_REPLICATIONS = 16
EXPECTED_TIMESERIES_POINTS = 1_647
EXPECTED_ROOT_SEED = 20_260_820
SCHEMA_ID = (
    "https://redxking.github.io/fleet-assurance-sim/schemas/public_mvp_scenario_pack.schema.json"
)
PAGES_ORIGIN = "https://redxking.github.io"
PAGES_BASE = f"{PAGES_ORIGIN}/fleet-assurance-sim/"
REPOSITORY_BASE = "https://github.com/redxking/fleet-assurance-sim"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"non-finite JSON number: {token}")


def _read_strict_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    assert isinstance(value, dict), f"{path} must contain one JSON object"
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _resolve_json_pointer(root: dict[str, Any], reference: str) -> dict[str, Any]:
    assert reference.startswith("#/"), f"only local schema references are allowed: {reference}"
    current: Any = root
    for encoded in reference[2:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        assert isinstance(current, dict) and key in current, f"unresolved schema ref {reference}"
        current = current[key]
    assert isinstance(current, dict), f"schema ref {reference} must resolve to an object"
    return current


def _is_json_type(value: object, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        )
    if expected == "null":
        return value is None
    raise AssertionError(f"unsupported JSON Schema type in release validator: {expected}")


def _validate_schema(
    value: object,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    *,
    location: str = "$",
) -> None:
    if "$ref" in schema:
        reference = schema["$ref"]
        assert isinstance(reference, str)
        _validate_schema(
            value,
            _resolve_json_pointer(root_schema, reference),
            root_schema,
            location=location,
        )
        return

    expected_type = schema.get("type")
    if expected_type is not None:
        if isinstance(expected_type, list):
            assert any(_is_json_type(value, item) for item in expected_type), (
                f"{location} does not match allowed types {expected_type}"
            )
        else:
            assert isinstance(expected_type, str)
            assert _is_json_type(value, expected_type), (
                f"{location} must have JSON type {expected_type}, got {type(value).__name__}"
            )

    if "const" in schema:
        assert value == schema["const"], f"{location} must equal {schema['const']!r}"
    if "enum" in schema:
        assert value in schema["enum"], f"{location} is outside the closed enum"

    if isinstance(value, dict):
        required = schema.get("required", [])
        assert isinstance(required, list)
        missing = set(required) - set(value)
        assert not missing, f"{location} is missing required keys {sorted(missing)}"
        properties = schema.get("properties", {})
        assert isinstance(properties, dict)
        for key, item in value.items():
            if key in properties:
                child_schema = properties[key]
                assert isinstance(child_schema, dict)
                _validate_schema(
                    item,
                    child_schema,
                    root_schema,
                    location=f"{location}.{key}",
                )
            elif schema.get("additionalProperties") is False:
                raise AssertionError(f"{location} contains unexpected key {key!r}")
            elif isinstance(schema.get("additionalProperties"), dict):
                _validate_schema(
                    item,
                    schema["additionalProperties"],
                    root_schema,
                    location=f"{location}.{key}",
                )

    if isinstance(value, list):
        if "minItems" in schema:
            assert len(value) >= schema["minItems"], f"{location} has too few items"
        if "maxItems" in schema:
            assert len(value) <= schema["maxItems"], f"{location} has too many items"
        if schema.get("uniqueItems"):
            encoded = [_canonical_json(item) for item in value]
            assert len(encoded) == len(set(encoded)), f"{location} must contain unique items"
        prefix_items = schema.get("prefixItems", [])
        assert isinstance(prefix_items, list)
        for index, child_schema in enumerate(prefix_items):
            if index >= len(value):
                break
            assert isinstance(child_schema, dict)
            _validate_schema(
                value[index],
                child_schema,
                root_schema,
                location=f"{location}[{index}]",
            )
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            start = len(prefix_items) if prefix_items else 0
            for index, item in enumerate(value[start:], start=start):
                _validate_schema(
                    item,
                    items_schema,
                    root_schema,
                    location=f"{location}[{index}]",
                )

    if isinstance(value, str):
        if "minLength" in schema:
            assert len(value) >= schema["minLength"], f"{location} is too short"
        if "maxLength" in schema:
            assert len(value) <= schema["maxLength"], f"{location} is too long"
        if "pattern" in schema:
            assert re.search(schema["pattern"], value), f"{location} does not match its pattern"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        assert math.isfinite(value), f"{location} must be finite"
        if "minimum" in schema:
            assert value >= schema["minimum"], f"{location} is below its minimum"
        if "maximum" in schema:
            assert value <= schema["maximum"], f"{location} is above its maximum"
        if "exclusiveMinimum" in schema:
            assert value > schema["exclusiveMinimum"], (
                f"{location} is not above its exclusive minimum"
            )
        if "exclusiveMaximum" in schema:
            assert value < schema["exclusiveMaximum"], (
                f"{location} is not below its exclusive maximum"
            )


def _walk_json(value: object, *, location: str = "$") -> list[tuple[str, object]]:
    rows = [(location, value)]
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(_walk_json(item, location=f"{location}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_walk_json(item, location=f"{location}[{index}]"))
    return rows


class _HTMLAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.local_references: set[str] = set()
        self.external_anchors: set[str] = set()
        self.metadata: dict[str, str] = {}
        self.csp_values: list[str] = []
        self.html_language: str | None = None
        self.title_text: list[str] = []
        self.h1_count = 0
        self._inside_title = False
        self._inside_script = False
        self._inside_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        keys = [key.lower() for key, _ in attrs]
        if len(keys) != len(set(keys)):
            self.errors.append(f"<{tag}> contains a duplicate attribute")
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag == "html":
            self.html_language = attributes.get("lang")
        if tag == "title":
            self._inside_title = True
        if tag == "h1":
            self.h1_count += 1
        if tag == "script":
            self._inside_script = True
        if tag == "style":
            self._inside_style = True
            self.errors.append("inline <style> is not allowed")
        if tag in {"base", "iframe", "object", "embed"}:
            self.errors.append(f"<{tag}> is outside the static browser boundary")
        if "style" in attributes:
            self.errors.append(f"inline style attribute is not allowed on <{tag}>")
        if any(key.startswith("on") for key in attributes):
            self.errors.append(f"inline event handler is not allowed on <{tag}>")
        element_id = attributes.get("id")
        if element_id:
            if element_id in self.ids:
                self.errors.append(f"duplicate HTML id {element_id!r}")
            self.ids.add(element_id)

        if tag == "meta":
            identity = attributes.get("name") or attributes.get("property")
            if identity:
                self.metadata[identity.lower()] = attributes.get("content", "")
            if attributes.get("http-equiv", "").lower() == "content-security-policy":
                self.csp_values.append(attributes.get("content", ""))

        reference: str | None = None
        if "src" in attributes:
            reference = attributes["src"]
        elif tag == "link" and "href" in attributes:
            rel = set(attributes.get("rel", "").lower().split())
            if rel & {"stylesheet", "icon", "preload", "modulepreload"}:
                reference = attributes["href"]
        if reference:
            self._record_asset_reference(reference, tag=tag)

        if tag == "a" and "href" in attributes:
            href = attributes["href"]
            if href.startswith(("https://", "http://", "//")):
                self.external_anchors.add(href)
            elif href and not href.startswith("#"):
                self.local_references.add(href)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False
        if tag == "script":
            self._inside_script = False
        if tag == "style":
            self._inside_style = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_text.append(data)
        if self._inside_script and data.strip():
            self.errors.append("inline script content is not allowed")
        if self._inside_style and data.strip():
            self.errors.append("inline style content is not allowed")

    def _record_asset_reference(self, reference: str, *, tag: str) -> None:
        if reference.startswith(("https://", "http://", "//", "data:", "javascript:")):
            self.errors.append(f"external or embedded asset on <{tag}>: {reference}")
        else:
            self.local_references.add(reference)


def _parse_csp(value: str) -> dict[str, tuple[str, ...]]:
    directives: dict[str, tuple[str, ...]] = {}
    for section in value.split(";"):
        tokens = section.strip().split()
        if not tokens:
            continue
        name = tokens[0].lower()
        assert name not in directives, f"duplicate CSP directive {name}"
        directives[name] = tuple(tokens[1:])
    return directives


def _resolve_site_reference(page: Path, reference: str) -> str | None:
    parsed = urlsplit(reference)
    assert not parsed.scheme and not parsed.netloc, f"asset must be same-package: {reference}"
    assert not parsed.path.startswith("/"), f"root-relative path breaks project Pages: {reference}"
    decoded = unquote(parsed.path)
    candidate = PurePosixPath(page.relative_to(SITE).parent.as_posix()) / decoded
    normalized_parts: list[str] = []
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        assert part != "..", f"reference escapes the static package: {reference}"
        normalized_parts.append(part)
    if not normalized_parts:
        return None
    return PurePosixPath(*normalized_parts).as_posix()


def test_static_artifact_closure_and_size_limits() -> None:
    assert SITE.is_dir() and not SITE.is_symlink()
    actual_files: set[str] = set()
    total_bytes = 0
    for item in SITE.rglob("*"):
        assert not item.is_symlink(), f"symbolic links are forbidden in Pages artifact: {item}"
        if not item.is_file():
            continue
        relative = item.relative_to(SITE).as_posix()
        assert item.stat().st_nlink == 1, f"hard-linked Pages artifact is forbidden: {relative}"
        assert item.stat().st_size > 0, f"empty Pages artifact: {relative}"
        actual_files.add(relative)
        total_bytes += item.stat().st_size
    assert actual_files == EXPECTED_SITE_FILES
    assert total_bytes <= 10 * 1024 * 1024
    assert PACK_PATH.stat().st_size == EXPECTED_PACK_BYTES
    assert MANIFEST_PATH.stat().st_size == EXPECTED_MANIFEST_BYTES
    assert SCHEMA_PATH.stat().st_size == EXPECTED_SCHEMA_BYTES


def test_manifest_binds_exact_release_data_and_schema() -> None:
    assert _sha256(PACK_PATH) == EXPECTED_PACK_SHA256
    assert _sha256(MANIFEST_PATH) == EXPECTED_MANIFEST_SHA256
    assert _sha256(SCHEMA_PATH) == EXPECTED_SCHEMA_SHA256
    assert SITE_SCHEMA_PATH.read_bytes() == SCHEMA_PATH.read_bytes()
    assert _sha256(SITE_SCHEMA_PATH) == EXPECTED_SCHEMA_SHA256
    manifest = _read_strict_json(MANIFEST_PATH)
    assert set(manifest) == {
        "schema_version",
        "manifest_id",
        "pack_id",
        "artifact",
        "schema",
        "scenario_count",
        "timeseries_point_count",
        "root_seed",
        "replications_per_scenario",
        "synthetic_only",
        "external_validation",
        "operational_use_authorized",
        "generator_name",
        "manifest_content_sha256",
    }
    assert manifest["schema_version"] == "1.0"
    assert manifest["manifest_id"] == "fleet-public-mvp-synthetic-v1-manifest"
    assert manifest["pack_id"] == "fleet-public-mvp-synthetic-v1"
    assert manifest["artifact"] == {
        "filename": "scenario-pack.json",
        "bytes": EXPECTED_PACK_BYTES,
        "sha256": EXPECTED_PACK_SHA256,
    }
    assert manifest["schema"] == {
        "id": SCHEMA_ID,
        "bytes": EXPECTED_SCHEMA_BYTES,
        "sha256": EXPECTED_SCHEMA_SHA256,
    }
    assert manifest["scenario_count"] == EXPECTED_SCENARIOS
    assert manifest["timeseries_point_count"] == EXPECTED_TIMESERIES_POINTS
    assert manifest["root_seed"] == EXPECTED_ROOT_SEED
    assert manifest["replications_per_scenario"] == EXPECTED_REPLICATIONS
    assert manifest["synthetic_only"] is True
    assert manifest["external_validation"] is False
    assert manifest["operational_use_authorized"] is False
    assert manifest["generator_name"] == "build_public_mvp_scenarios"
    assert manifest["manifest_content_sha256"] == EXPECTED_MANIFEST_CONTENT_SHA256
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_content_sha256"}
    assert hashlib.sha256(_canonical_json(unsigned)).hexdigest() == (
        EXPECTED_MANIFEST_CONTENT_SHA256
    )


def test_pack_conforms_to_closed_schema() -> None:
    schema = _read_strict_json(SITE_SCHEMA_PATH)
    pack = _read_strict_json(PACK_PATH)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == SCHEMA_ID
    assert schema["additionalProperties"] is False
    _validate_schema(pack, schema, schema)


def test_closed_scenario_grid_and_evidence_boundaries() -> None:
    pack = _read_strict_json(PACK_PATH)
    assert pack["synthetic_only"] is True
    assert pack["external_validation"] is False
    assert pack["operational_use_authorized"] is False
    design = pack["design"]
    assert design["root_seed"] == EXPECTED_ROOT_SEED
    assert design["replications_per_scenario"] == EXPECTED_REPLICATIONS
    assert design["fleet_sizes"] == [100, 1_000, 10_000]
    assert design["scenario_count"] == EXPECTED_SCENARIOS
    assert design["timeseries_max_points_per_scenario"] == 61
    assert design["paired_capacity_comparisons"] is True
    assert design["capacity_scaling"] == "proportional_to_target_fleet_size"
    limitations = pack["limitations"]
    assert any(
        "proportional provisioning rather than fixed capacity" in item for item in limitations
    )
    assert any("no disturbance profile" in item.lower() for item in limitations)
    assert any(
        "no confidence, credible, prediction, or transfer interval" in item for item in limitations
    )

    capacities = {"constrained": 0.8, "baseline": 1.0, "expanded": 1.25}
    profiles = {"linear", "step", "bursty"}
    expected_grid = {
        (fleet_size, profile, capacity)
        for fleet_size in (100, 1_000, 10_000)
        for profile in profiles
        for capacity in capacities
    }
    scenarios = pack["scenarios"]
    actual_grid = {(row["fleet_size"], row["profile"], row["capacity_case"]) for row in scenarios}
    assert len(scenarios) == EXPECTED_SCENARIOS
    assert actual_grid == expected_grid
    assert [row["id"] for row in scenarios] == sorted(row["id"] for row in scenarios)

    total_points = 0
    for row in scenarios:
        fleet_size = row["fleet_size"]
        expected_id = f"n{fleet_size:05d}-{row['profile']}-capacity-{row['capacity_case']}"
        assert row["id"] == expected_id
        assert row["initial_fleet_size"] == round(0.1 * fleet_size)
        assert row["capacity_multiplier"] == capacities[row["capacity_case"]]
        assert row["replications"] == EXPECTED_REPLICATIONS
        pressure = row["ex_ante_pressure"]
        assert pressure["not_an_operational_outcome"] is True
        assert pressure["boundary_crossed"] is (pressure["value"] >= pressure["boundary"])
        outcomes = row["operational_outcomes"]
        assert outcomes["definition_uses_ex_ante_pressure"] is False
        times = [point["time_s"] for point in row["timeseries"]]
        assert 2 <= len(times) <= 61
        assert times == sorted(set(times))
        total_points += len(times)
    assert total_points == EXPECTED_TIMESERIES_POINTS

    forbidden_key_markers = {
        "absolute_path",
        "api_key",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
    }
    forbidden_value_markers = {
        "/Users/",
        "/home/",
        "C:\\Users\\",
        "file://",
        "ghp_",
        "github_pat_",
        "-----BEGIN PRIVATE KEY-----",
    }
    for payload in (pack, _read_strict_json(MANIFEST_PATH)):
        for location, value in _walk_json(payload):
            if isinstance(value, float):
                assert math.isfinite(value), f"non-finite public value at {location}"
            if isinstance(value, dict):
                for key in value:
                    assert not any(marker in key.lower() for marker in forbidden_key_markers), (
                        f"non-public key at {location}.{key}"
                    )
            if isinstance(value, str):
                assert not any(marker in value for marker in forbidden_value_markers), (
                    f"non-public value marker at {location}"
                )


def test_html_csp_and_local_asset_boundary() -> None:
    referenced: set[str] = set()
    for relative in ("index.html", "404.html"):
        page = SITE / relative
        audit = _HTMLAudit()
        audit.feed(page.read_text(encoding="utf-8"))
        audit.close()
        assert not audit.errors, f"{relative}: {audit.errors}"
        assert audit.html_language == "en"
        assert "".join(audit.title_text).strip()
        assert audit.h1_count == 1
        assert len(audit.csp_values) == 1
        csp = _parse_csp(audit.csp_values[0])
        required_directives = {
            "default-src": ("'none'",),
            "style-src": ("'self'",),
            "object-src": ("'none'",),
            "base-uri": ("'none'",),
            "form-action": ("'none'",),
            "frame-ancestors": ("'none'",),
        }
        for name, expected in required_directives.items():
            assert csp.get(name) == expected, f"{relative}: unsafe or missing {name}"
        assert set(csp.get("img-src", ())) == {"'self'", "data:"}
        if relative == "index.html":
            assert csp.get("script-src") == ("'self'",)
            assert csp.get("connect-src") == ("'self'",)
            assert csp.get("font-src") == ("'none'",)
        else:
            assert "script-src" not in csp
            assert "connect-src" not in csp
        for href in audit.external_anchors:
            assert href.startswith(REPOSITORY_BASE), f"unapproved external link: {href}"
            assert urlsplit(href).scheme == "https"
        for reference in audit.local_references:
            resolved = _resolve_site_reference(page, reference)
            if resolved is not None:
                assert resolved in EXPECTED_SITE_FILES, (
                    f"{relative} references undeclared artifact {resolved}"
                )
                referenced.add(resolved)

        if relative == "index.html":
            assert audit.metadata.get("description")
            assert audit.metadata.get("referrer") == "no-referrer"
            assert audit.metadata.get("og:image") == (f"{PAGES_BASE}assets/social-preview.png")
            assert audit.metadata.get("twitter:image") == (f"{PAGES_BASE}assets/social-preview.png")
            referenced.add("assets/social-preview.png")
            canonical = audit.metadata.get("og:url")
            assert canonical == PAGES_BASE

    assert {
        "assets/app.js",
        "assets/favicon.svg",
        "assets/social-preview.png",
        "assets/styles.css",
        "data/manifest.json",
        "data/scenario-pack.json",
    }.issubset(referenced)


def test_css_and_javascript_have_no_external_runtime_interfaces() -> None:
    css = (SITE / "assets" / "styles.css").read_text(encoding="utf-8")
    javascript = (SITE / "assets" / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"@import\s", css, flags=re.IGNORECASE)
    assert not re.search(r"(?:https?:)?//", css)
    for raw_url in re.findall(r"url\(([^)]+)\)", css, flags=re.IGNORECASE):
        url = raw_url.strip().strip("\"'")
        assert not url.startswith(("http:", "https:", "//", "data:"))
        resolved = _resolve_site_reference(SITE / "assets" / "styles.css", url)
        assert resolved in EXPECTED_SITE_FILES

    declared_urls = set(re.findall(r"https?://[^\"']+", javascript))
    assert declared_urls == {SCHEMA_ID}
    assert "data/scenario-pack.json" in javascript
    assert re.search(r"\bfetch\s*\(", javascript)
    forbidden_browser_interfaces = {
        "XMLHttpRequest",
        "WebSocket",
        "EventSource",
        "sendBeacon",
        "RTCPeerConnection",
        "navigator.geolocation",
        "navigator.credentials",
        "navigator.serviceWorker",
        "document.cookie",
        "localStorage",
        "sessionStorage",
    }
    for interface in forbidden_browser_interfaces:
        assert interface not in javascript, f"network or persistence interface present: {interface}"
    assert not re.search(r"\b(eval|Function)\s*\(", javascript)
    assert not re.search(r"\bimport\s*\(", javascript)


def test_social_preview_is_valid_expected_png() -> None:
    path = SITE / "assets" / "social-preview.png"
    payload = path.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(payload) <= 2 * 1024 * 1024
    offset = 8
    chunks: list[bytes] = []
    width = height = None
    while offset < len(payload):
        assert offset + 12 <= len(payload), "truncated PNG chunk"
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_data = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : offset + 12 + length])[0]
        assert zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF == expected_crc
        chunks.append(chunk_type)
        if chunk_type == b"IHDR":
            assert length == 13
            width, height = struct.unpack(">II", chunk_data[:8])
        offset += 12 + length
        if chunk_type == b"IEND":
            break
    assert offset == len(payload), "PNG contains data after IEND"
    assert chunks[0] == b"IHDR" and chunks[-1] == b"IEND" and b"IDAT" in chunks
    assert (width, height) == (1_200, 630)
    assert not any(
        marker in payload for marker in (b"/Users/", b"/home/", b"file://", b"github_pat_", b"ghp_")
    )


def test_workflow_is_pinned_least_privilege_and_main_only() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "pull_request_target:" not in workflow
    assert "secrets." not in workflow
    assert "branches:\n      - main" in workflow
    assert "paths:" not in workflow
    assert workflow.count("github.ref == 'refs/heads/main'") == 2
    assert "github.event_name != 'pull_request'" in workflow
    assert workflow.count("pages: write") == 1
    assert "pages: read" not in workflow
    assert workflow.count("id-token: write") == 1
    assert workflow.count("contents: read") == 2
    assert "path: site" in workflow
    for test_path in (
        "tests/schema/test_public_mvp_scenario_pack.py",
        "tests/integration/test_public_mvp_release_surface.py",
        "tests/visualization/test_public_mvp_site.py",
    ):
        assert test_path in workflow
    assert "requirements-stage3-freeze.txt jsonschema==4.25.1" in workflow
    assert "python -m pip install --no-deps --editable ." in workflow
    assert "assert version('jsonschema') == '4.25.1'" in workflow
    deploy_position = workflow.index("\n  deploy:\n")
    assert workflow.index("Upload validated Pages artifact") < deploy_position
    assert workflow.index("Configure GitHub Pages") > deploy_position
    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, flags=re.MULTILINE)
    assert uses == [
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
        "actions/upload-pages-artifact@7b1f4a764d45c48632c6b24a0339c27f5614fb0b",
        "actions/configure-pages@983d7736d9b0ae728b81ab479565c72886d7745b",
        "actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",
    ]
    assert all(re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", item) for item in uses)


def test_completed_stage3_frozen_files_remain_unchanged() -> None:
    manifest = _read_strict_json(ROOT / "manifests" / "stage3_preexecution_manifest.json")
    frozen = manifest["files"]
    assert isinstance(frozen, dict)
    assert len(frozen) == 151
    mismatches: list[str] = []
    for relative_path, expected in frozen.items():
        assert isinstance(relative_path, str)
        assert isinstance(expected, str)
        path = ROOT / relative_path
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual != expected:
            mismatches.append(relative_path)
    assert mismatches == []


def test_feedback_forms_enforce_public_data_and_claim_boundaries() -> None:
    issue_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
    discussion_dir = ROOT / ".github" / "DISCUSSION_TEMPLATE"
    assert {path.name for path in issue_dir.iterdir() if path.is_file()} == {
        "config.yml",
        "public-mvp-bug.yml",
        "public-mvp-research-review.yml",
        "public-mvp-scenario.yml",
    }
    assert {path.name for path in discussion_dir.iterdir() if path.is_file()} == {"ideas.yml"}
    forms = [
        issue_dir / "public-mvp-bug.yml",
        issue_dir / "public-mvp-research-review.yml",
        issue_dir / "public-mvp-scenario.yml",
        discussion_dir / "ideas.yml",
    ]
    for path in forms:
        content = path.read_text(encoding="utf-8")
        lowered = content.lower()
        assert "type: upload" not in lowered
        assert content.count("required: true") >= 2
        for boundary in (
            "classified",
            "export-controlled",
            "operationally sensitive",
            "restricted",
            "synthetic",
        ):
            assert boundary in lowered, f"{path.name} is missing boundary term {boundary!r}"
    bug = (issue_dir / "public-mvp-bug.yml").read_text(encoding="utf-8").lower()
    scenario = (issue_dir / "public-mvp-scenario.yml").read_text(encoding="utf-8").lower()
    research = (issue_dir / "public-mvp-research-review.yml").read_text(encoding="utf-8").lower()
    assert "usability" in bug and "scientific" in bug
    assert "falsification" in scenario and "reuse rights" in scenario
    assert "claim-to-evidence" in research and "uncertainty" in research
    config = (issue_dir / "config.yml").read_text(encoding="utf-8")
    assert "blank_issues_enabled: false" in config
    assert "/security/advisories/new" in config
