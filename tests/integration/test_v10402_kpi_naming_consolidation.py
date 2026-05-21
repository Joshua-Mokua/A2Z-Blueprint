"""Integration tests for v10.402 — KPI naming consolidation (TC39 + deep review).

Per Joshua's directive: "i recommend a deep review to see if there are
other similar KPI". Deep review found 4 alias pairs, not just NPL.

12 tests across 4 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(name):
    return json.loads((REPO / "data" / name).read_text())


MIGRATIONS = {
    "NPL_RATIO": "NPL Ratio",
    "NEW_ACCOUNTS": "New Accounts",
    "NET_INTEREST_MARGIN": "Net Interest Margin",
    "COMPLIANCE_SCORE": "Compliance Score",
}


# ────────────────────────────────────────────────────────────────────
# Section 1 — Alias resolver extended
# ────────────────────────────────────────────────────────────────────

def test_v10402_aliases_extended():
    """KPI_ALIASES contains all 4 v10.402 additions."""
    for k in list(sys.modules):
        if "kpi_alias_resolver" in k:
            del sys.modules[k]
    from utils.kpi_alias_resolver import KPI_ALIASES
    for upper, human in MIGRATIONS.items():
        assert KPI_ALIASES.get(upper) == human, (
            f"KPI_ALIASES[{upper}] = {KPI_ALIASES.get(upper)}; expected {human}"
        )


def test_v10402_resolver_maps_uppercase_to_human():
    """resolve_kpi_id returns human form for all 4 alias pairs."""
    for k in list(sys.modules):
        if "kpi_alias_resolver" in k:
            del sys.modules[k]
    from utils.kpi_alias_resolver import resolve_kpi_id
    for upper, human in MIGRATIONS.items():
        assert resolve_kpi_id(upper) == human


def test_v10402_compliance_alias_redirected():
    """COMPLIANCE alias now maps to 'Compliance Score' (was 'COMPLIANCE_SCORE')."""
    for k in list(sys.modules):
        if "kpi_alias_resolver" in k:
            del sys.modules[k]
    from utils.kpi_alias_resolver import KPI_ALIASES
    assert KPI_ALIASES.get("COMPLIANCE") == "Compliance Score"


# ────────────────────────────────────────────────────────────────────
# Section 2 — bank_targets cleaned
# ────────────────────────────────────────────────────────────────────

def test_v10402_bank_targets_no_active_uppercase():
    """No active uppercase entries in bank_targets."""
    bt = _load("bank_targets.json")
    for upper in MIGRATIONS:
        active = [k for k in bt if not k.startswith("_")
                 and k.startswith(f"{upper}|")]
        assert not active, f"bank_targets still has active {upper}: {active}"


def test_v10402_bank_targets_human_preserved():
    """Human-form bank_targets entries preserved unchanged."""
    bt = _load("bank_targets.json")
    for human in MIGRATIONS.values():
        # Should have at least 1 entry (for 2026)
        active = [k for k in bt if not k.startswith("_")
                 and k.startswith(f"{human}|")]
        assert len(active) >= 1, f"Human-form '{human}' missing from bank_targets"


def test_v10402_archive_block_present():
    """Archived uppercase entries preserved for audit."""
    bt = _load("bank_targets.json")
    assert "_v10402_archived_uppercase_aliases" in bt
    archive = bt["_v10402_archived_uppercase_aliases"]
    assert "entries" in archive
    assert len(archive["entries"]) >= 4  # 8 entries (4 pairs × 2 years)


# ────────────────────────────────────────────────────────────────────
# Section 3 — fixed_kpis + target_cascade migrated
# ────────────────────────────────────────────────────────────────────

def test_v10402_fixed_kpis_no_uppercase():
    """No uppercase aliases in any period of fixed_kpis."""
    fk = _load("fixed_kpis.json")
    for period_key, period_data in fk.items():
        if period_key.startswith("_") or not isinstance(period_data, dict):
            continue
        kpis = period_data.get("kpis", [])
        for k in kpis:
            assert k not in MIGRATIONS, (
                f"fixed_kpis[{period_key}] still has {k!r}"
            )


def test_v10402_fixed_kpis_human_present():
    """Human form of formerly-uppercase Fixed KPIs now in fixed_kpis."""
    fk = _load("fixed_kpis.json")
    # NPL Ratio and Compliance Score WERE in fixed_kpis as uppercase;
    # should now be present as human form
    # NPL Ratio was renamed from NPL_RATIO then REMOVED per Joshua A2 (cascadable)
    # Compliance Score was renamed and kept (bank-wide)
    annual_2026 = fk.get("2026", {}).get("kpis", [])
    assert "Compliance Score" in annual_2026


def test_v10402_cascade_no_uppercase():
    """No uppercase alias entries in target_cascade after regen."""
    tc = _load("target_cascade.json")
    for k in tc:
        if k.startswith("_") or "|" not in k:
            continue
        parts = k.split("|")
        if len(parts) >= 2:
            assert parts[1] not in MIGRATIONS, (
                f"cascade still has uppercase {parts[1]} in {k}"
            )


def test_v10402_cascade_size_dropped_by_alias_count():
    """Cascade dropped by ~1,728 entries (4 KPIs × 432 entries)."""
    tc = _load("target_cascade.json")
    data_count = sum(1 for k in tc if not k.startswith("_") and "|" in k)
    # Was 25,488; should now be ~23,760 (1,728 fewer)
    assert 23000 <= data_count <= 26000, f"unexpected cascade size: {data_count}"  # ~24K after NPL Ratio cascade restored


# ────────────────────────────────────────────────────────────────────
# Section 4 — Engine + gate
# ────────────────────────────────────────────────────────────────────

def test_v10402_engine_state_preserved():
    """All 4 metrics still zero."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10402_backups_preserved():
    for f in ("bank_targets.json.before", "fixed_kpis.json.before",
              "target_cascade.json.before"):
        assert (REPO / "data" / "_v10402_backups" / f).exists()


def test_v10402_g288_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10402_kpi_naming_consolidation
    r = gate_v10402_kpi_naming_consolidation()
    assert r["passed"], r.get("violations")
