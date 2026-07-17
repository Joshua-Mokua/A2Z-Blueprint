"""tests/test_bsc_library_integrity.py — the KPI library must not disagree with itself.

Every BSC bug found on 2026-07-16 was one shape: two representations of the same truth,
drifting apart silently. None of them raised. Each simply returned a plausible number.

  1. get_active_kpis() iterated `pillars` as a dict when the live file holds a list —
     the KPI Library admin page had been broken and nobody knew.
  2. active_kpis listed 52 ids; 43 no longer existed. Migrations had renamed them in
     kpis[] and role_kpis but not in the allowlist.
  3. KPI_ID_ALIASES mapped DEP_GROWTH -> "Retail & MSME Deposit Growth" while
     "Total Deposit Growth" carried the id DEP_GROWTH. The alias won, so the MD was
     scored on retail deposits instead of total. The number looked entirely reasonable.
  4. Director CCB carried K012 twice, double-counting its weight.

These tests assert the invariants those bugs violated. They are cheap, they read the
real library rather than a fixture — a fixture cannot catch a migration that forgot a
file — and each one would have failed loudly on the day the bug was introduced.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

LIB_PATH = Path(__file__).resolve().parents[1] / "data" / "kpi_library.json"


@pytest.fixture(scope="module")
def lib() -> dict:
    if not LIB_PATH.exists():
        pytest.skip(f"{LIB_PATH} not present")
    return json.loads(LIB_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def kpi_ids(lib) -> set:
    return {k["id"] for k in lib.get("kpis", []) if isinstance(k, dict) and k.get("id")}


class TestAliasMap:
    """An alias must never shadow a real id."""

    def test_no_alias_key_is_a_real_kpi_id(self, kpi_ids):
        from utils.bsc_score_computation import KPI_ID_ALIASES

        clash = sorted(set(KPI_ID_ALIASES) & kpi_ids)
        assert not clash, (
            "These keys are aliases AND real KPI ids: "
            f"{clash}. Resolution tries the alias first, so the real KPI is "
            "unreachable and its holders are scored on a different measure. This is "
            "how DEP_GROWTH silently scored the MD on retail deposits instead of "
            "total. When a migration promotes a legacy code to a canonical id, delete "
            "its alias in the same commit."
        )

    def test_every_alias_resolves_to_a_real_kpi(self, kpi_ids):
        from utils.bsc_score_computation import KPI_ID_ALIASES

        dangling = sorted(
            f"{k} -> {v}" for k, v in KPI_ID_ALIASES.items() if v not in kpi_ids
        )
        assert not dangling, (
            f"Aliases pointing at KPIs that no longer exist: {dangling}. "
            "The reference resolves to nothing and the measure is dropped from the "
            "scorecard without a word."
        )


class TestRoleWeights:
    """role_kpi_weights and role_kpis are two views of one scorecard."""

    def test_weighted_kpis_are_assigned_to_the_role(self, lib):
        rk = lib.get("role_kpis", {})
        rw = lib.get("role_kpi_weights", {})
        errors = []
        for role, spec in rw.items():
            assigned = set(rk.get(role) or [])
            weighted = set((spec.get("kpis") or {}).keys())
            orphan = sorted(weighted - assigned)
            if orphan:
                errors.append(f"{role!r}: weighted but not assigned -> {orphan}")
        assert not errors, (
            "role_kpi_weights carries KPIs that role_kpis does not list:\n  "
            + "\n  ".join(errors)
            + "\nThe weight is real and the KPI is invisible, so the scorecard's "
            "weights no longer total what it claims."
        )

    def test_no_role_lists_a_kpi_twice(self, lib):
        rk = lib.get("role_kpis", {})
        dupes = {}
        for role, ids in rk.items():
            if not isinstance(ids, list):
                continue
            seen, dup = set(), set()
            for i in ids:
                (dup if i in seen else seen).add(i)
            if dup:
                dupes[role] = sorted(dup)
        assert not dupes, (
            f"Roles listing the same KPI more than once: {dupes}. "
            "Director CCB carried K012 twice and its weight counted twice."
        )

    def test_every_role_kpi_reference_exists(self, lib, kpi_ids):
        from utils.bsc_score_computation import KPI_ID_ALIASES

        rk = lib.get("role_kpis", {})
        rw = lib.get("role_kpi_weights", {})
        errors = []
        # Only roles with a real 2026 scorecard: the legacy roles carry historic
        # references we are not fixing here, and a test that fails for a known
        # unrelated reason gets ignored, which is worse than no test.
        for role in rw:
            for ref in rk.get(role) or []:
                if ref in kpi_ids:
                    continue
                if KPI_ID_ALIASES.get(ref) in kpi_ids:
                    continue
                errors.append(f"{role!r} -> {ref!r}")
        assert not errors, (
            "Scorecard KPI references that resolve to nothing:\n  "
            + "\n  ".join(errors)
        )


class TestActiveFlags:
    """The active allowlist and the per-KPI flag must agree."""

    def test_active_kpis_list_has_no_ghosts(self, lib, kpi_ids):
        listed = lib.get("active_kpis")
        if not listed:
            pytest.skip("no active_kpis allowlist in this library")
        ghosts = sorted(set(listed) - kpi_ids)
        assert not ghosts, (
            f"{len(ghosts)} entries in active_kpis name KPIs that do not exist: "
            f"{ghosts[:8]}{' ...' if len(ghosts) > 8 else ''}. "
            "43 of 52 were stale once, because migrations renamed ids in kpis[] and "
            "role_kpis but never here."
        )


class TestFixedKpis:
    """A bank-fixed KPI is one number for everyone — so it must not be a unit's own."""

    def test_fixed_kpis_have_a_bank_target(self):
        fixed_p = LIB_PATH.parent / "fixed_kpis.json"
        bank_p = LIB_PATH.parent / "bank_targets.json"
        if not (fixed_p.exists() and bank_p.exists()):
            pytest.skip("fixed_kpis / bank_targets not present")
        fixed = json.loads(fixed_p.read_text(encoding="utf-8"))
        bank = json.loads(bank_p.read_text(encoding="utf-8"))
        errors = []
        for period, entry in fixed.items():
            if period.startswith("_") or not isinstance(entry, dict):
                continue
            for kid in entry.get("kpis") or []:
                year = period.split("-")[0]
                if f"{kid}|{year}" not in bank and f"{kid}|{period}" not in bank:
                    errors.append(f"{period}: {kid}")
        assert not errors, (
            "KPIs marked bank-fixed with no bank target — they resolve to nothing "
            f"and silently drop off every scorecard that carries them: {errors[:10]}"
        )
