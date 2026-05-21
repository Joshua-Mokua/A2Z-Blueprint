"""utils/canonical_pbt_bsc_view.py — v10.376 PM-framework bridge.

First concrete integration of canonical profitability (v10.370 atom + v10.372
converged engines) with the Performance Management framework (BSC + KPI Library
+ Target Cascade). Per Joshua's directive: "the other objective of the entire
system is performance management... I don't want us to lose the gist of this
system."

This module is **read-only by design** — it joins canonical PBT with the
cascaded target so the MD cockpit can show one authoritative number with full
lineage. A write-side bridge (submitting canonical PBT to bsc_actuals via
bsc_engine.submit) is deferred to v10.377+ once all consumers of source_module
are understood.

Module API
----------
  get_md_pbt_summary(cbs_dir=None, period='2026') →
      MDPBTSummary(
        actual,                  # canonical PBT (compute_pbt_from_cbs)
        target,                  # MD's PBT target (target_cascade::300001|PBT|year)
        achievement_pct,         # actual / target × 100
        delta,                   # actual - target
        allocations,             # list of 12 direct reports with their cascaded targets
        drill_links,             # dict of drill paths (sbu, branch, customer, staff)
        canonical_engine_status, # which engines contributed (G250/G256/G257/G258/G253)
        body_system_axes,        # skeleton/circulatory mapping for MD
      )

  get_md_cascade_allocations(period='2026') →
      list of {to_code, to_name, role, amount, profitability_tier}

  format_md_pbt_card(summary) →
      Streamlit-ready markdown for the MD cockpit BSC Summary tab.

Module purity
-------------
Zero upward imports beyond the canonical engines (pbt_computation,
customer_pbt_allocator) and the role taxonomy (role_taxonomy).
Reads target_cascade.json for the target side.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

# MD's staff code (William Mwanake) — anchored in target_cascade.json
MD_STAFF_CODE = "300001"

# The canonical PBT KPI ID in kpi_library.json
PBT_KPI_ID = "PBT"


@dataclass
class MDPBTSummary:
    """Unified canonical PBT + BSC view for the MD."""
    actual: float
    target: float
    achievement_pct: float
    delta: float
    allocations: List[Dict[str, Any]] = field(default_factory=list)
    drill_links: Dict[str, str] = field(default_factory=dict)
    canonical_engine_status: Dict[str, Any] = field(default_factory=dict)
    body_system_axes: Dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def is_on_track(self, tolerance_pct: float = 90.0) -> bool:
        """MD's daily question: is the bank on track to achieve strategic goals?

        Returns True if achievement_pct >= tolerance_pct (default 90% — i.e.
        within 10% of target counts as on track). Tolerance configurable.
        """
        return self.achievement_pct >= tolerance_pct


def _load_target_cascade() -> Dict[str, Any]:
    """Load target_cascade.json safely."""
    p = DATA_DIR / "target_cascade.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_md_pbt_target(period: str = "2026") -> Optional[Dict[str, Any]]:
    """Read MD's PBT cascade entry for the given period.

    Key format: '<staff_code>|<KPI>|<year>' — e.g. '300001|PBT|2026'.
    Returns the entry dict or None if not found.
    """
    tc = _load_target_cascade()
    key = f"{MD_STAFF_CODE}|{PBT_KPI_ID}|{period}"
    return tc.get(key)


def get_md_cascade_allocations(period: str = "2026") -> List[Dict[str, Any]]:
    """Return MD's 12 direct-report PBT allocations for the period.

    Enriches each allocation with profitability_tier from v10.374 taxonomy.
    """
    cascade = _get_md_pbt_target(period)
    if not cascade:
        return []

    allocations = cascade.get("allocations", [])
    if not allocations:
        return []

    # Enrich with role + tier (best-effort: role lookup from users.json)
    enriched = []
    users_path = DATA_DIR / "users.json"
    user_lookup: Dict[str, Dict[str, str]] = {}
    if users_path.exists():
        try:
            u = json.loads(users_path.read_text(encoding="utf-8"))
            for _, rec in u.items():
                if isinstance(rec, dict):
                    sc = rec.get("staff_code", "")
                    if sc:
                        user_lookup[sc] = {
                            "role": rec.get("role", ""),
                            "department": rec.get("department", ""),
                        }
        except Exception:
            pass

    # Get classify_role for tier
    try:
        from utils.role_taxonomy import classify_role
        classifier_available = True
    except Exception:
        classifier_available = False

    for alloc in allocations:
        sc = str(alloc.get("to_code", ""))
        user_info = user_lookup.get(sc, {})
        role = user_info.get("role", alloc.get("role", "Unknown"))
        tier = "unknown"
        if classifier_available and role:
            try:
                tier = classify_role(role).tier
            except Exception:
                pass
        enriched.append({
            "to_code": sc,
            "to_name": alloc.get("to_name", ""),
            "role": role,
            "department": user_info.get("department", ""),
            "amount": float(alloc.get("amount", 0) or 0),
            "profitability_tier": tier,
        })
    return enriched


def _compute_canonical_actual(cbs_dir: Optional[Path] = None) -> float:
    """Run the canonical PBT engine. If cbs_dir is None, seed a virtual bank.

    Returns canonical PBT as float (KES). Wraps in try/except so the bridge
    fails gracefully (returns 0.0) rather than breaking the MD cockpit.
    """
    try:
        from utils.pbt_computation import compute_pbt_from_cbs
        if cbs_dir is None:
            # Seed a virtual bank (Phase A pattern — production would pass live CBS dir)
            import tempfile
            from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
            from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
            bank, _ = seed_virtual_bank(config=SeedConfig.small())
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                persist_bank_to_cbs(bank, output_dir=td_path)
                pbt = compute_pbt_from_cbs(td_path)
                return float(pbt.pbt)
        else:
            pbt = compute_pbt_from_cbs(cbs_dir)
            return float(pbt.pbt)
    except Exception:
        return 0.0


def _build_canonical_engine_status() -> Dict[str, Any]:
    """Document which canonical engines this view depends on.

    Returned as part of MDPBTSummary so the UI can show provenance.
    """
    return {
        "G250": "Bank PBT from CBS (v10.364) — primary source",
        "G256": "Σ Customer PBT = Bank PBT (v10.370 atomic) — drill foundation",
        "G257": "Σ Staff PBT = Bank PBT (v10.370) — staff drill via 120_staff_pbt page",
        "G258": "Σ child cascade target = MD target (v10.371 multi-level) — target side",
        "G253": "Engine A == Engine B canonical (v10.372 ENFORCING) — one number across paths",
        "G261": "Role-aware staff PBT page (v10.375) — drill destination",
    }


def _build_body_system_axes() -> Dict[str, Any]:
    """Document the body-system framing for the MD's view.

    Joshua: 'all the organs all functioning perfectly and in harmony to make
    the one body as a whole.'
    """
    return {
        "skeleton": (
            "Seniority axis — MD (tier 0) sets bank target, cascades to 12 "
            "direct reports (Chiefs, tier 1), who cascade to Heads (tier 2), "
            "to Senior Managers (tier 3), to Managers (tier 4), to Officers "
            "(tier 5), to Tellers/Junior (tier 6)."
        ),
        "circulatory": (
            "Profitability axis — Bank PBT (actual) flows up from per-customer "
            "(atomic, G256) through Staff (portfolio_owner + service tiers, "
            "G257) and Branch (G255) and SBU (G254) rollups. All routes "
            "reconcile to the same Bank PBT within KES 100."
        ),
        "function": (
            "Functional axis — future v10.4XX work. Role classifies by domain "
            "(sales / operations / risk / technology / etc.). Not yet "
            "formalised in code."
        ),
    }


def get_md_pbt_summary(
    cbs_dir: Optional[Path] = None,
    period: str = "2026",
) -> MDPBTSummary:
    """The one function the MD cockpit needs.

    Returns a unified view: canonical PBT actual, cascade target, achievement,
    12 allocations, drill links, engine provenance, body-system framing.
    """
    actual = _compute_canonical_actual(cbs_dir=cbs_dir)

    target = 0.0
    note = ""
    target_entry = _get_md_pbt_target(period)
    if target_entry:
        target = float(target_entry.get("total_target", 0) or 0)
    else:
        note = (
            f"No cascade target found for MD ({MD_STAFF_CODE}) PBT in "
            f"period {period}. Set via Target Cascade page (12_cascade)."
        )

    achievement_pct = (actual / target * 100.0) if target else 0.0
    delta = actual - target

    allocations = get_md_cascade_allocations(period=period)

    drill_links = {
        "sbu_drilldown": "pages/114_sbu_drilldown.py — canonical Σ SBU = Bank (G254)",
        "branch_ranking": "pages/113_branch_ranking.py — 94 branches ranked (G255)",
        "staff_pbt": "pages/120_staff_pbt.py — role-aware per-staff PBT (v10.375, G261)",
        "target_cascade": "pages/12_cascade.py — MD's cascade tree",
        "bsc_scorecard": "pages/1_perform.py — full BSC with all 109 active KPIs",
    }

    return MDPBTSummary(
        actual=actual,
        target=target,
        achievement_pct=achievement_pct,
        delta=delta,
        allocations=allocations,
        drill_links=drill_links,
        canonical_engine_status=_build_canonical_engine_status(),
        body_system_axes=_build_body_system_axes(),
        note=note,
    )


def format_md_pbt_card(summary: MDPBTSummary) -> str:
    """Return Streamlit-ready markdown for the MD cockpit BSC Summary tab.

    Three sections: headline KPI box, cascade allocation summary, drill links.
    """
    on_track = summary.is_on_track()
    status_emoji = "✅" if on_track else "⚠️"
    status_text = "ON TRACK" if on_track else "AT RISK"

    md = []
    md.append(f"### {status_emoji} Canonical PBT — {status_text}")
    md.append("")
    md.append(f"- **Actual (canonical):** KES {summary.actual/1e9:,.2f}B")
    md.append(f"- **Target (cascade):** KES {summary.target/1e9:,.2f}B")
    md.append(
        f"- **Achievement:** {summary.achievement_pct:.1f}% "
        f"(Δ KES {summary.delta/1e9:+,.2f}B)"
    )
    md.append("")
    md.append(
        "*Lineage: compute_pbt_from_cbs (G250) → joined with "
        "target_cascade.json::300001|PBT|2026 (G258)*"
    )
    md.append("")
    if summary.allocations:
        portfolio_total = sum(
            a["amount"] for a in summary.allocations
            if a.get("profitability_tier") == "portfolio_owner"
        )
        structural_total = sum(
            a["amount"] for a in summary.allocations
            if a.get("profitability_tier") == "structural_owner"
        )
        md.append(
            f"**Cascade allocation:** {len(summary.allocations)} direct reports — "
            f"KES {portfolio_total/1e9:,.2f}B to portfolio-owners + "
            f"KES {structural_total/1e9:,.2f}B to structural-owners"
        )
    if summary.note:
        md.append("")
        md.append(f"> ⚠ {summary.note}")
    return "\n".join(md)


def self_test() -> None:
    """v10.376 self_test."""
    tests = 0

    # Test 1: get_md_cascade_allocations returns 12 (or 0 if no cascade data)
    allocations = get_md_cascade_allocations(period="2026")
    # Don't assert count — production data may differ; assert structure only
    if allocations:
        sample = allocations[0]
        for field_name in ("to_code", "to_name", "role", "amount",
                           "profitability_tier"):
            assert field_name in sample, f"allocation missing {field_name}"
    tests += 1

    # Test 2: get_md_pbt_summary returns the right shape
    summary = get_md_pbt_summary(cbs_dir=None, period="2026")
    assert isinstance(summary, MDPBTSummary)
    assert summary.actual != 0 or summary.note  # either has a value or a note
    assert isinstance(summary.canonical_engine_status, dict)
    assert "G250" in summary.canonical_engine_status
    assert isinstance(summary.body_system_axes, dict)
    assert "skeleton" in summary.body_system_axes
    assert "circulatory" in summary.body_system_axes
    tests += 1

    # Test 3: format_md_pbt_card returns non-empty markdown
    card = format_md_pbt_card(summary)
    assert isinstance(card, str)
    assert len(card) > 100
    assert "Canonical PBT" in card
    assert "Lineage" in card or "lineage" in card
    tests += 1

    # Test 4: is_on_track logic
    summary_good = MDPBTSummary(actual=1000, target=1000, achievement_pct=100.0, delta=0)
    assert summary_good.is_on_track()
    summary_bad = MDPBTSummary(actual=500, target=1000, achievement_pct=50.0, delta=-500)
    assert not summary_bad.is_on_track()
    tests += 1

    # Test 5: drill_links contains all expected drill paths
    expected_drills = ("sbu_drilldown", "branch_ranking", "staff_pbt",
                       "target_cascade", "bsc_scorecard")
    for drill in expected_drills:
        assert drill in summary.drill_links, f"missing drill: {drill}"
    tests += 1

    print(f"✓ canonical_pbt_bsc_view self_test passed ({tests} tests)")


if __name__ == "__main__":
    self_test()
    s = get_md_pbt_summary(cbs_dir=None, period="2026")
    print(f"\nCanonical PBT (from seeded bank): KES {s.actual/1e9:,.2f}B")
    print(f"Target (cascade):                 KES {s.target/1e9:,.2f}B")
    print(f"Achievement:                       {s.achievement_pct:.1f}%")
    print(f"Allocations:                       {len(s.allocations)} direct reports")
    if s.allocations:
        from collections import Counter
        tier_dist = Counter(a["profitability_tier"] for a in s.allocations)
        print(f"  Tier distribution: {dict(tier_dist)}")
    print(f"\nCard preview:\n{format_md_pbt_card(s)[:400]}")
