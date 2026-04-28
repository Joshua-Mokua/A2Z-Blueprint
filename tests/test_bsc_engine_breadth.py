"""tests/test_bsc_engine_breadth.py — Standard #3 breadth verification.

These tests assert that the engine reaches ≥17 distinct module-sources,
either directly (source_module=...) or via the operational-modules bridge
(metadata['original_source'] tags inside compute_operational_kpi_actuals).

The bridge architecture (one submit_batch site per bridge, multiple
sources tagged into metadata) means we cannot verify breadth by counting
submit() call sites alone. We must verify the *contents* of what those
calls produce.

Contract under test:
    Standard #3 — All modules use bsc_engine.submit().

    With our two-bridge design:
      - utils/bsc_engine.py:        the engine itself (public API)
      - utils/actuals_engine.py:    CBS-derived path (1 submit_batch site)
      - utils/core.py update_bsc_from_modules: operational path (1 site)

    The "breadth" comes from:
      (a) source_module=... values seen at submit sites,         AND
      (b) per-record original_source tags inside the operational
          bridge's metadata.

    The union must be ≥ 17 (the spec's module count).

Static + AST checks only — no live BSC engine call required. The
existing tests/test_bsc_engine.py already covers the engine's runtime
behaviour. This file scopes to "are 17 sources actually wired?"
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
UTILS = ROOT / "utils"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _direct_source_modules() -> set[str]:
    """Every distinct value of source_module=... at a submit/submit_batch
    site outside the engine itself."""
    out: set[str] = set()
    for p in (UTILS, ROOT / "pages", ROOT / "scripts"):
        if not p.exists():
            continue
        for f in p.glob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if rel == "utils/bsc_engine.py" or rel == "scripts/audit.py":
                continue
            code = _read(f)
            if not re.search(r"from\s+utils\.bsc_engine\s+import|"
                             r"import\s+utils\.bsc_engine", code):
                continue
            out.update(re.findall(r'source_module\s*=\s*["\']([^"\']+)["\']', code))
    return out


def _operational_bridge_sources() -> set[str]:
    """The set of {source: '<name>'} tags inside compute_operational_kpi_actuals."""
    core_src = _read(UTILS / "core.py")
    m = re.search(
        r"def\s+compute_operational_kpi_actuals\b.*?(?=\ndef |\Z)",
        core_src, re.DOTALL,
    )
    if not m:
        return set()
    body = m.group(0)
    return set(re.findall(r'"source"\s*:\s*"([^"]+)"', body))


# ═══════════════════════════════════════════════════════════════════════
# Engine-presence sanity
# ═══════════════════════════════════════════════════════════════════════

def test_engine_module_present():
    """utils/bsc_engine.py must exist — Standard #3 requires it."""
    assert (UTILS / "bsc_engine.py").exists(), (
        "utils/bsc_engine.py is missing. The engine is the single "
        "chokepoint for performance data (Standard #2) and the precondition "
        "for Standard #3 universal adoption."
    )


def test_operational_bridge_function_present():
    """utils/core.py.update_bsc_from_modules must exist — it's the
    operational-side bridge that fans out 17 module sources into one
    submit_batch call."""
    src = _read(UTILS / "core.py")
    assert "def update_bsc_from_modules" in src, (
        "update_bsc_from_modules is the operational-modules bridge. "
        "Removing it removes 15+ module-sources from the engine's reach."
    )


def test_compute_operational_kpi_actuals_present():
    """utils/core.py.compute_operational_kpi_actuals is the inner
    compute pass that tags each KPI value with its originating module."""
    src = _read(UTILS / "core.py")
    assert "def compute_operational_kpi_actuals" in src, (
        "compute_operational_kpi_actuals is missing — it's the function "
        "that produces 'source': '<module>' tags for each KPI value, "
        "which the bridge preserves into metadata.original_source."
    )


# ═══════════════════════════════════════════════════════════════════════
# Direct adoption (source_module=...)
# ═══════════════════════════════════════════════════════════════════════

def test_at_least_one_direct_submit_site():
    """At least ONE submit_batch site outside the engine must exist."""
    direct = _direct_source_modules()
    assert direct, (
        "No submit/submit_batch site found with source_module=... outside "
        "utils/bsc_engine.py. The engine has no callers."
    )


def test_actuals_engine_is_a_direct_submitter():
    """utils/actuals_engine.py must be one of the direct submitters
    (CBS-derived KPI path)."""
    direct = _direct_source_modules()
    # The convention is source_module="actuals_engine"
    assert "actuals_engine" in direct, (
        f"Expected source_module='actuals_engine' from utils/actuals_engine.py "
        f"(CBS-derived KPIs). Found direct sources: {sorted(direct)}"
    )


def test_operational_modules_is_a_direct_submitter():
    """utils/core.py.update_bsc_from_modules must submit with
    source_module='operational_modules' (per v5.19 wiring)."""
    direct = _direct_source_modules()
    assert "operational_modules" in direct, (
        f"Expected source_module='operational_modules' from "
        f"utils/core.py.update_bsc_from_modules. Found: {sorted(direct)}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Bridge breadth — the operational bridge must cover ≥15 distinct sources
# ═══════════════════════════════════════════════════════════════════════

def test_operational_bridge_covers_at_least_15_sources():
    """compute_operational_kpi_actuals must tag KPI values from at least
    15 distinct source modules. Combined with the 2 direct submitters
    (actuals_engine + operational_modules), this gets us to ≥17 union."""
    bridge = _operational_bridge_sources()
    assert len(bridge) >= 15, (
        f"compute_operational_kpi_actuals tags only {len(bridge)} distinct "
        f"sources — need ≥15 to satisfy Standard #3's 17-module spec when "
        f"combined with the 2 direct submitters. Found: {sorted(bridge)}"
    )


def test_operational_bridge_covers_core_business_modules():
    """Spot-check that the bridge covers the most important business
    modules. If any of these falls out of the bridge, Standard #3
    regresses on a high-impact path."""
    bridge = _operational_bridge_sources()
    # Highest-impact modules by KPI weight
    required_minimum = {
        "projects",            # K036/K037/K038
        "loan_applications",   # K042/K043
        "ews_cases",           # K044/K045
        "aml_alerts",          # K046/K047
        "pipeline",            # K039/K040/K041
    }
    missing = required_minimum - bridge
    assert not missing, (
        f"Operational bridge is missing critical modules: {sorted(missing)}. "
        f"Bridge currently covers: {sorted(bridge)}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Union breadth — the headline metric for G17
# ═══════════════════════════════════════════════════════════════════════

def test_union_breadth_meets_spec_target():
    """The union of direct source_module values + operational bridge
    sources must be ≥ 17 (Standard #3 target).

    This is the test that proves "All 17 modules use bsc_engine.submit()"
    — not via 17 separate submit() sites, but via 17 distinct sources
    flowing through the engine via the bridges."""
    direct = _direct_source_modules()
    bridge = _operational_bridge_sources()
    union = direct | bridge
    target = 17
    assert len(union) >= target, (
        f"Engine breadth {len(union)} < spec target {target}. "
        f"Direct: {sorted(direct)}\nBridge: {sorted(bridge)}\n"
        f"Union: {sorted(union)}"
    )


def test_metadata_original_source_preserved_in_operational_bridge():
    """The bridge MUST preserve the per-KPI 'source' tag into
    metadata['original_source']. Without this, breadth via metadata
    is invisible to downstream consumers and to G17."""
    src = _read(UTILS / "core.py")
    # Find update_bsc_from_modules body
    m = re.search(r"def\s+update_bsc_from_modules\b.*?(?=\ndef |\Z)", src, re.DOTALL)
    assert m, "update_bsc_from_modules not found"
    body = m.group(0)
    # Check the metadata builder preserves original_source
    assert '"original_source"' in body, (
        "update_bsc_from_modules no longer copies the per-KPI 'source' tag "
        "into metadata['original_source']. Standard #3 breadth becomes "
        "invisible to downstream auditors."
    )


# ═══════════════════════════════════════════════════════════════════════
# No-bypass invariant (defence-in-depth — duplicates G8 but pinpointed)
# ═══════════════════════════════════════════════════════════════════════

def test_no_module_writes_bsc_actuals_directly():
    """No file outside utils/bsc_engine.py + scripts/audit.py is allowed
    to write a bsc_actuals_*.json file directly. G8 enforces this; this
    test pins the invariant locally so the bsc_engine test file fails
    loudly if someone introduces a bypass."""
    bypass_rx = re.compile(
        r"save_json\s*\([^)]*bsc_actuals|bsc_actuals_[A-Za-z0-9_-]+\.json",
        re.IGNORECASE,
    )
    bypasses: list[str] = []
    for p in (UTILS, ROOT / "pages", ROOT / "scripts"):
        if not p.exists():
            continue
        for f in p.glob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if rel in {"utils/bsc_engine.py", "scripts/audit.py"}:
                continue
            code = _read(f)
            for m in bypass_rx.finditer(code):
                # Skip docstring + comment hits
                line_start = code.rfind("\n", 0, m.start()) + 1
                line = code[line_start:code.find("\n", m.end())]
                if line.lstrip().startswith("#"): continue
                if "noqa: a2z-bsc-bypass" in line: continue
                # Skip docstring detection: if we're inside a """ block that's
                # opened before this line and not yet closed
                preceding = code[:m.start()]
                triple_quotes = preceding.count('"""') + preceding.count("'''")
                if triple_quotes % 2 == 1:
                    continue  # inside a docstring
                bypasses.append(f"{rel}:L{code.count(chr(10), 0, m.start()) + 1} {line.strip()[:80]}")
    assert not bypasses, (
        f"Found bypass writes to bsc_actuals — Standard #3 violated:\n  " +
        "\n  ".join(bypasses)
    )
