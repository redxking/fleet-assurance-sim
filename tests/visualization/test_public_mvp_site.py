"""Focused contract, security, and accessibility tests for the public MVP site."""

from __future__ import annotations

import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
INDEX = SITE / "index.html"
NOT_FOUND = SITE / "404.html"
STYLES = SITE / "assets" / "styles.css"
SCRIPT = SITE / "assets" / "app.js"
FAVICON = SITE / "assets" / "favicon.svg"
SOCIAL_PREVIEW = SITE / "assets" / "social-preview.png"
PACK = SITE / "data" / "scenario-pack.json"
MANIFEST = SITE / "data" / "manifest.json"
PUBLIC_URL = "https://redxking.github.io/fleet-assurance-sim/"


class DocumentAudit(HTMLParser):
    """Collect structural facts without adding a third-party HTML parser."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.labels_for: list[str] = []
        self.references: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.scripts: list[dict[str, str | None]] = []
        self.styles: list[dict[str, str | None]] = []
        self.event_handlers: list[str] = []
        self.inputs: list[dict[str, str | None]] = []
        self.landmarks: list[str] = []
        self.inline_style_count = 0
        self.inline_script_text = ""
        self._in_script_without_src = False
        self.html_language: str | None = None
        self.meta: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.html_language = values.get("lang")
        if values.get("id"):
            self.ids.append(str(values["id"]))
        if tag == "label" and values.get("for"):
            self.labels_for.append(str(values["for"]))
        for name in ("aria-labelledby", "aria-describedby"):
            if values.get(name):
                self.references.extend(str(values[name]).split())
        if tag in {"a", "link"}:
            self.links.append((tag, str(values.get("href", ""))))
        if tag == "script":
            self.scripts.append(values)
            self._in_script_without_src = not bool(values.get("src"))
        if tag == "style":
            self.styles.append(values)
        if tag == "input":
            self.inputs.append(values)
        if tag in {"main", "nav", "header", "footer"}:
            self.landmarks.append(tag)
        if "style" in values:
            self.inline_style_count += 1
        self.event_handlers.extend(name for name, _ in attrs if name.lower().startswith("on"))
        if tag == "meta":
            self.meta.append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script_without_src = False

    def handle_data(self, data: str) -> None:
        if self._in_script_without_src:
            self.inline_script_text += data


def _audit(path: Path) -> tuple[str, DocumentAudit]:
    html = path.read_text(encoding="utf-8")
    parser = DocumentAudit()
    parser.feed(html)
    parser.close()
    return html, parser


def _meta_content(audit: DocumentAudit, key: str, value: str) -> str | None:
    for item in audit.meta:
        if item.get(key) == value:
            return item.get("content")
    return None


def test_public_site_has_the_closed_local_asset_set() -> None:
    expected = {
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
    actual = {path.relative_to(SITE).as_posix() for path in SITE.rglob("*") if path.is_file()}
    assert actual == expected
    assert FAVICON.read_text(encoding="utf-8").startswith("<svg")
    assert SOCIAL_PREVIEW.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (SITE / "schemas" / "public_mvp_scenario_pack.schema.json").read_bytes() == (
        ROOT / "schemas" / "public_mvp_scenario_pack.schema.json"
    ).read_bytes()


def test_index_has_accessible_landmarks_references_and_controls() -> None:
    html, audit = _audit(INDEX)
    assert html.startswith("<!doctype html>")
    assert audit.html_language == "en"
    assert {"header", "nav", "main", "footer"}.issubset(audit.landmarks)
    assert len(audit.ids) == len(set(audit.ids))
    assert set(audit.labels_for).issubset(audit.ids)
    assert set(audit.references).issubset(audit.ids)
    assert {"scenario-select", "compare-toggle", "compare-select"}.issubset(audit.ids)
    assert '<a class="skip-link" href="#main-content">' in html
    assert 'role="status" aria-live="polite"' in html
    assert (
        'id="selection-announcement" class="screen-reader-only" role="status" aria-live="polite" aria-atomic="true"'
        in html
    )
    assert 'aria-describedby="scenario-help"' in html
    assert 'role="alert" hidden' in html
    assert 'role="img" aria-labelledby="pressure-title"' in html
    assert '<canvas id="pressure-canvas" aria-hidden="true"></canvas>' in html
    assert (
        "Modeled maximum queue-wait pressure ratio over time for retained representative replication 0"
        in html
    )
    assert 'role="region" aria-label="Wait pressure over time data table"' in html
    assert all(item.get("type") not in {"file", "password", "email"} for item in audit.inputs)


def test_index_uses_a_strict_self_only_runtime_policy() -> None:
    _, audit = _audit(INDEX)
    csp = _meta_content(audit, "http-equiv", "Content-Security-Policy")
    assert csp is not None
    for directive in (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ):
        assert directive in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert audit.inline_script_text.strip() == ""
    assert audit.styles == []
    assert audit.inline_style_count == 0
    assert audit.event_handlers == []
    assert [item.get("src") for item in audit.scripts] == ["assets/app.js"]
    for tag, href in audit.links:
        if tag == "link" and "canonical" in href:
            continue
        parsed = urlparse(href)
        assert not parsed.scheme or parsed.scheme == "https"
        assert parsed.scheme != "https" or parsed.netloc in {
            "github.com",
            "redxking.github.io",
        }


def test_public_copy_keeps_the_scientific_and_authority_boundary_visible() -> None:
    html = INDEX.read_text(encoding="utf-8")
    for statement in (
        "Synthetic research only.",
        "not operational recommendations",
        "not proof of deployment readiness",
        "What this does not establish",
        "External validation or authorized measured evidence",
        "No accounts. No uploads. No analytics. No operational actions.",
        "The browser does not run a new simulation or transmit your selections or user-provided data; it only loads the checked-in static package from this site.",
        "Each resource capacity is recomputed from target fleet size",
        "Cross-fleet views are not fixed-capacity scale-transfer tests.",
        "No confidence or credible interval is provided; they cannot support threshold or transfer decisions.",
        "A value above 1.0× means projected or observed queue wait exceeded the configured max-wait boundary",
    ):
        assert statement in html
    assert "upload" not in html.lower().replace("no uploads", "")
    assert "sign in" not in html.lower()
    assert "log in" not in html.lower()
    assert "disruption" not in html.lower()


def test_index_exposes_download_reproduction_and_feedback_paths() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert 'href="data/scenario-pack.json" download' in html
    assert "blob/main/QUICKSTART.md" in html
    assert "github.com/redxking/fleet-assurance-sim/discussions" in html
    assert "github.com/redxking/fleet-assurance-sim/issues/new/choose" in html
    assert "blob/main/CONTRIBUTING.md" in html
    assert "blob/main/docs/successor_prospective_protocol.md" in html


def test_social_metadata_is_absolute_specific_and_bound_to_the_card() -> None:
    _, audit = _audit(INDEX)
    assert _meta_content(audit, "property", "og:title") == "Fleet Assurance Playground"
    assert _meta_content(audit, "property", "og:url") == PUBLIC_URL
    card = f"{PUBLIC_URL}assets/social-preview.png"
    assert _meta_content(audit, "property", "og:image") == card
    assert _meta_content(audit, "name", "twitter:card") == "summary_large_image"
    assert _meta_content(audit, "name", "twitter:image") == card
    html = INDEX.read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{PUBLIC_URL}">' in html
    assert 'property="og:image:width" content="1200"' in html
    assert 'property="og:image:height" content="630"' in html


def test_css_covers_focus_touch_responsiveness_and_motion_preferences() -> None:
    css = STYLES.read_text(encoding="utf-8")
    assert ":focus-visible" in css
    assert "outline:3px solid var(--sky)" in css
    assert "min-height:44px" in css
    assert "min-height:48px" in css
    assert "@media(max-width:900px)" in css
    assert "@media(max-width:620px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "@media(forced-colors:active)" in css
    assert "overflow-x:hidden" in css
    assert "width:calc(100% - 1rem)" in css


def test_javascript_loads_and_cryptographically_binds_only_local_data() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'const PACK_URL = "data/scenario-pack.json"' in script
    assert 'const MANIFEST_URL = "data/manifest.json"' in script
    assert "Promise.all([" in script
    assert 'fetch(PACK_URL, { cache: "no-store", credentials: "same-origin" })' in script
    assert 'fetch(MANIFEST_URL, { cache: "no-store", credentials: "same-origin" })' in script
    assert 'subtle.digest("SHA-256", bytes)' in script
    assert "artifact.bytes === packBytes.byteLength" in script
    assert "await sha256(packBytes) === artifact.sha256" in script
    assert "await sha256(canonicalBytes) === claimedSelfHash" in script
    assert 'textContent = "Bytes match manifest"' in script
    assert "validatePack(parsed)" in script
    assert "scenario grid is not the exact registered Cartesian product" in script


def test_javascript_fails_closed_and_has_no_tracking_or_injection_surfaces() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
        "XMLHttpRequest",
        "WebSocket",
        "sendBeacon",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "gtag",
        "google-analytics",
        "segment.io",
    ):
        assert forbidden not in script
    assert 'document.body.dataset.appState = "error"' in script
    assert 'byId("explorer").hidden = true' in script
    assert "No fallback values have been substituted." in script
    assert "bool(pack.synthetic_only, true" in script
    assert "bool(pack.external_validation, false" in script
    assert "bool(pack.operational_use_authorized, false" in script
    assert "bool(outcomes.definition_uses_ex_ante_pressure, false" in script
    assert 'design.capacity_scaling === "proportional_to_target_fleet_size"' in script
    assert "selected.disturbance_fraction === 0" in script
    assert 'value === "none_all_projected_pressures_zero"' in script
    assert "paired capacity-case model comparison" in script
    assert "unpaired descriptive model comparison" in script
    assert "scenario.fleet_size === comparison.fleet_size" in script
    assert "scenario.profile === comparison.profile" in script
    assert 'label: "Ex-ante wait pressure"' in script
    assert 'unit: "registered wait boundary"' in script
    assert 'unit: "seconds per target agent"' in script
    assert "agent-seconds" not in script
    assert "of capacity" not in script
    assert "formatRatio(maxObserved)" in script
    assert "formatBoundaryDelta(delta)" in script
    assert "formatBoundaryDelta(pressureDelta)" in script
    assert "boundary-ratio units" in script
    assert "formatRatio(Math.abs(pressureDelta))" not in script


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_javascript_parses_in_a_real_javascript_runtime() -> None:
    completed = subprocess.run(
        [shutil.which("node") or "node", "--check", str(SCRIPT)],
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_scenario_pack_matches_the_interface_contract() -> None:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert pack["schema_version"] == "1.0"
    assert pack["pack_id"] == "fleet-public-mvp-synthetic-v1"
    assert pack["synthetic_only"] is True
    assert pack["external_validation"] is False
    assert pack["operational_use_authorized"] is False
    assert pack["design"]["capacity_scaling"] == "proportional_to_target_fleet_size"
    assert len(pack["scenarios"]) == 27
    assert manifest["artifact"]["filename"] == "scenario-pack.json"
    assert manifest["artifact"]["bytes"] == PACK.stat().st_size
    assert manifest["scenario_count"] == len(pack["scenarios"])
    assert manifest["generator_name"] == "build_public_mvp_scenarios"
    for scenario in pack["scenarios"]:
        assert scenario["disturbance_fraction"] == 0
        if scenario["ex_ante_pressure"]["value"] == 0:
            assert scenario["ex_ante_pressure"]["binding_resource"] == (
                "none_all_projected_pressures_zero"
            )
        assert scenario["ex_ante_pressure"]["not_an_operational_outcome"] is True
        assert scenario["operational_outcomes"]["definition_uses_ex_ante_pressure"] is False


def test_404_page_is_scriptless_helpful_and_self_contained() -> None:
    html, audit = _audit(NOT_FOUND)
    assert audit.html_language == "en"
    assert audit.scripts == []
    assert audit.styles == []
    assert audit.inline_style_count == 0
    assert audit.event_handlers == []
    assert "This path is outside the model." in html
    assert 'href="./">Return to the playground</a>' in html
    csp = _meta_content(audit, "http-equiv", "Content-Security-Policy")
    assert csp is not None and "default-src 'none'" in csp
    assert "script-src" not in csp
