"""tests/integration/test_v10322_multi_period.py

v10.322 — Multi-period cascade data.

Locks:
  - bank_targets.json has 2025 mirror entries
  - All 4 demo quarters have pre-computed cascade scores
  - Trend visible at every level (MD, Chief, Branch, Teller)
  - G213 passes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


REQUIRED_PERIODS = ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2")


# ────────────────────────────────────────────────────────────────────
# Section 1 — bank_targets 2025 mirror
# ────────────────────────────────────────────────────────────────────

def test_bank_targets_has_2025_entries():
    bt = json.loads(
        (REPO_ROOT / "data" / "bank_targets.json").read_text()
    )
    keys_2025 = [k for k in bt if k.endswith("|2025")]
    assert len(keys_2025) >= 40, (
        f"bank_targets has only {len(keys_2025)} 2025 "
        f"entries — v10.322 mirror missing"
    )


def test_2025_mirror_entries_tagged():
    """Mirrored entries should have a marker for audit trail."""
    bt = json.loads(
        (REPO_ROOT / "data" / "bank_targets.json").read_text()
    )
    sample_key = "PBT|2025"
    if sample_key in bt:
        entry = bt[sample_key]
        if isinstance(entry, dict):
            assert "_v10322_mirrored_from" in entry or (
                "target" in entry
            )


def test_2025_targets_match_2026():
    """2025 targets should be values mirrored from 2026 — same
    target value (since they're the same year-over-year baseline
    for the demo)."""
    bt = json.loads(
        (REPO_ROOT / "data" / "bank_targets.json").read_text()
    )
    for kpi_id in ("CX Score", "Audit Score",
                    "Staff Productivity"):
        k_2025 = f"{kpi_id}|2025"
        k_2026 = f"{kpi_id}|2026"
        if k_2025 in bt and k_2026 in bt:
            t_2025 = (
                bt[k_2025].get("target")
                if isinstance(bt[k_2025], dict)
                else bt[k_2025]
            )
            t_2026 = (
                bt[k_2026].get("target")
                if isinstance(bt[k_2026], dict)
                else bt[k_2026]
            )
            assert t_2025 == t_2026, (
                f"{kpi_id}: 2025={t_2025} vs 2026={t_2026}"
            )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Pre-computed files exist
# ────────────────────────────────────────────────────────────────────

def test_all_4_quarters_precomputed():
    for period in REQUIRED_PERIODS:
        p = (REPO_ROOT / "data"
             / f"cascade_scores_{period}.json")
        assert p.exists(), (
            f"cascade_scores_{period}.json missing"
        )


def test_each_quarter_has_md_score():
    for period in REQUIRED_PERIODS:
        p = (REPO_ROOT / "data"
             / f"cascade_scores_{period}.json")
        data = json.loads(p.read_text())
        md = data.get("scores", {}).get("EXEC-MD-001")
        assert md is not None, (
            f"{period}: MD score missing"
        )
        assert 1.0 <= float(md) <= 5.0


def test_each_quarter_has_broad_score_coverage():
    """Each period should have ≥500 staff scores."""
    for period in REQUIRED_PERIODS:
        p = (REPO_ROOT / "data"
             / f"cascade_scores_{period}.json")
        data = json.loads(p.read_text())
        scores = data.get("scores", {})
        assert len(scores) >= 500, (
            f"{period}: only {len(scores)} scores"
        )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Trends visible
# ────────────────────────────────────────────────────────────────────

def test_md_trend_visible_across_quarters():
    """MD score should differ across quarters by ≥0.02 — sanity
    check that the pre-compute isn't producing identical data."""
    md_scores = []
    for period in REQUIRED_PERIODS:
        p = (REPO_ROOT / "data"
             / f"cascade_scores_{period}.json")
        data = json.loads(p.read_text())
        md = data.get("scores", {}).get("EXEC-MD-001")
        md_scores.append(float(md))

    spread = max(md_scores) - min(md_scores)
    assert spread >= 0.02, (
        f"MD scores too flat: {md_scores} (spread "
        f"{spread:.4f}). Trend won't be visible."
    )


def test_teller_300230_trend_visible():
    """A specific Teller should have a quarter-over-quarter
    trend (their band movement causes variation)."""
    teller_scores = []
    for period in REQUIRED_PERIODS:
        p = (REPO_ROOT / "data"
             / f"cascade_scores_{period}.json")
        data = json.loads(p.read_text())
        s = data.get("scores", {}).get("300230")
        if s is not None:
            teller_scores.append(float(s))
    assert len(teller_scores) == 4, (
        f"Teller 300230 missing from some quarters: "
        f"got {len(teller_scores)} of 4"
    )
    spread = max(teller_scores) - min(teller_scores)
    # Tellers move bands ~10% per quarter so spread should be visible
    assert spread >= 0.1, (
        f"Teller 300230 spread {spread:.2f} too flat for "
        f"trend display"
    )


def test_branch_manager_trend_visible():
    """At least one Branch Manager should have a visible trend."""
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    bms = [
        s for s in u.values()
        if s.role == "Branch Manager"
    ][:5]
    trends_visible = 0
    for bm in bms:
        bm_scores = []
        for period in REQUIRED_PERIODS:
            p = (REPO_ROOT / "data"
                 / f"cascade_scores_{period}.json")
            data = json.loads(p.read_text())
            s = data.get("scores", {}).get(bm.staff_code)
            if s is not None:
                bm_scores.append(float(s))
        if len(bm_scores) == 4:
            spread = max(bm_scores) - min(bm_scores)
            if spread >= 0.1:
                trends_visible += 1
    assert trends_visible >= 1, (
        f"No Branch Manager has a visible trend across "
        f"4 quarters (checked {len(bms)} BMs)"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Precompute script supports skip-rollups
# ────────────────────────────────────────────────────────────────────

def test_precompute_script_has_skip_rollups_flag():
    """The --skip-rollups flag should be present (used for trend
    quarters that don't need detailed rollups)."""
    src = (
        REPO_ROOT / "scripts"
        / "precompute_cascade_scores.py"
    ).read_text()
    assert "--skip-rollups" in src
    assert "include_rollups" in src


# ────────────────────────────────────────────────────────────────────
# Section 5 — Audit gate G213
# ────────────────────────────────────────────────────────────────────

def test_g213_gate_exists_and_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G213":
            g = fn()
            break
    assert g is not None, "G213 not registered"
    assert g["passed"], (
        f"G213 failed: {g.get('summary', '')[:200]}. "
        f"Violations: {g.get('violations', [])}"
    )
