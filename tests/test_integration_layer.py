"""tests/test_integration_layer.py — v10.108.

End-to-end verification of the operational-table autofit pathway.
Covers the four pieces shipped in v10.108:

    1. utils.kpi_ownership      — ownership contract (cascade ∪ role_kpis)
    2. utils.kpi_aggregation_rules — registry + 6 patterns
    3. utils.staff_field_resolver  — STAFF_FIELD_BY_TABLE
    4. utils.actuals_engine.compute_actuals_from_operational_tables

The headline simulation is the **ownership-gate enforcement test**:
synthetic loan_applications with 5 RMs, only 4 own K011 → autofit
produces actuals for 4, drops the 5th silently. This proves the
contract that distinguishes Phase 1D's correctness from naive
"submit per-staff actual for everyone" approaches.

Tests are self-contained — no live PostgreSQL, no live FLEXCUBE,
no Streamlit. Each test uses a tmp_path fixture so the actuals_engine
data_dir can be redirected without touching the repo's data/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Helper: build a minimal data_dir for an isolated test run ─────────

def _seed_isolated_data_dir(tmp_path: Path,
                            users_data: dict,
                            cascade_data: dict,
                            tables: dict[str, list],
                            kpi_library: dict | None = None) -> Path:
    """Create an isolated data_dir with the JSON files we need.
    `tables` is {table_name: list_of_row_dicts}. Returns the data_dir
    path."""
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / "users.json").write_text(
        json.dumps(users_data), encoding="utf-8")
    (d / "target_cascade.json").write_text(
        json.dumps(cascade_data), encoding="utf-8")
    if kpi_library is not None:
        (d / "kpi_library.json").write_text(
            json.dumps(kpi_library), encoding="utf-8")
    else:
        # Use the real library so role_kpis lookups work
        real = REPO_ROOT / "data" / "kpi_library.json"
        (d / "kpi_library.json").write_text(
            real.read_text(encoding="utf-8"), encoding="utf-8")
    for table_name, rows in tables.items():
        (d / f"{table_name}.json").write_text(
            json.dumps(rows), encoding="utf-8")
    return d


# ─── kpi_ownership tests ────────────────────────────────────────────────

class TestKpiOwnership:
    """Verifies the union-rule ownership contract."""

    def test_role_default_kpi_owned_without_cascade_lock(
            self, tmp_path, monkeypatch):
        """A KPI in role_kpis[role] is owned even when cascade is not
        locked. This is the role-default path."""
        from utils import kpi_ownership

        users = {
            "u1": {"staff_code": "S001", "role": "Branch Manager"}
        }
        # Branch Manager role_kpis includes 'PBT' per real library.
        # No cascade lock for S001/2026.
        d = _seed_isolated_data_dir(tmp_path, users, {}, {})
        monkeypatch.setattr(
            kpi_ownership, "_data_dir", lambda: d)
        kpi_ownership._refresh_caches()

        assert kpi_ownership.is_kpi_owned_by_staff(
            "S001", "PBT", "2026") is True

    def test_cascade_kpi_not_owned_without_lock(
            self, tmp_path, monkeypatch):
        """A KPI present in cascade allocations but NOT locked is
        NOT owned. This is the cascade-lock-gate path.

        Uses a custom library where Teller's role_kpis is empty so
        the only possible ownership path is via cascade lock.
        """
        from utils import kpi_ownership

        # Custom library where Teller has NO role_kpis — guarantees
        # cascade is the only path to ownership
        custom_lib = {
            "pillars": [{"id": "Financial", "weight": 1.0}],
            "kpis": [{
                "id": "Loan Book Growth", "code": "LOAN_GROWTH",
                "name": "Loan Book Growth", "pillar": "Financial",
                "weight": 0.10, "unit": "KES M", "direction": "higher",
                "active": True, "description": "x",
                "source": "cbs_loans",
            }],
            "role_kpis": {"Teller": []},
        }
        users = {"u1": {"staff_code": "S001", "role": "Teller"}}
        cascade = {
            "300001|Loan Book Growth|2026": {
                "from_code": "300001", "kpi": "Loan Book Growth",
                "period": "2026",
                "allocations": [{"to_code": "S001", "amount": 100}]
            }
            # Note: no deadline|S001|2026 lock record
        }
        d = _seed_isolated_data_dir(
            tmp_path, users, cascade, {}, kpi_library=custom_lib)
        monkeypatch.setattr(
            kpi_ownership, "_data_dir", lambda: d)
        kpi_ownership._refresh_caches()

        assert kpi_ownership.is_kpi_owned_by_staff(
            "S001", "Loan Book Growth", "2026") is False
        assert kpi_ownership.is_cascade_locked("S001", "2026") is False

    def test_cascade_kpi_owned_when_locked(
            self, tmp_path, monkeypatch):
        """The same cascade allocation, but with the lock record
        present, IS owned."""
        from utils import kpi_ownership

        custom_lib = {
            "pillars": [{"id": "Financial", "weight": 1.0}],
            "kpis": [{
                "id": "Loan Book Growth", "code": "LOAN_GROWTH",
                "name": "Loan Book Growth", "pillar": "Financial",
                "weight": 0.10, "unit": "KES M", "direction": "higher",
                "active": True, "description": "x",
                "source": "cbs_loans",
            }],
            "role_kpis": {"Teller": []},
        }
        users = {"u1": {"staff_code": "S001", "role": "Teller"}}
        cascade = {
            "300001|Loan Book Growth|2026": {
                "from_code": "300001", "kpi": "Loan Book Growth",
                "period": "2026",
                "allocations": [{"to_code": "S001", "amount": 100}]
            },
            "deadline|S001|2026": {
                "staff_code": "S001", "period": "2026",
                "targets_locked": True,
            },
        }
        d = _seed_isolated_data_dir(
            tmp_path, users, cascade, {}, kpi_library=custom_lib)
        monkeypatch.setattr(
            kpi_ownership, "_data_dir", lambda: d)
        kpi_ownership._refresh_caches()

        assert kpi_ownership.is_cascade_locked("S001", "2026") is True
        assert kpi_ownership.is_kpi_owned_by_staff(
            "S001", "Loan Book Growth", "2026") is True

    def test_owned_kpis_returns_union(self, tmp_path, monkeypatch):
        """owned_kpis_for_staff returns the union of role + cascade."""
        from utils import kpi_ownership

        users = {"u1": {"staff_code": "S001",
                        "role": "Branch Manager"}}
        cascade = {
            "300001|PAR|2026": {
                "from_code": "300001", "kpi": "PAR",
                "period": "2026",
                "allocations": [{"to_code": "S001", "amount": 5}]
            },
            "deadline|S001|2026": {
                "staff_code": "S001", "period": "2026",
                "targets_locked": True,
            },
        }
        d = _seed_isolated_data_dir(tmp_path, users, cascade, {})
        monkeypatch.setattr(
            kpi_ownership, "_data_dir", lambda: d)
        kpi_ownership._refresh_caches()

        owned = kpi_ownership.owned_kpis_for_staff("S001", "2026")
        # Must include role-default (PBT, etc. for Branch Manager)
        # AND cascade-allocated (PAR).
        assert "PAR" in owned
        # Branch Manager has PBT in real role_kpis
        assert "PBT" in owned

    def test_empty_inputs_return_false(self, tmp_path, monkeypatch):
        """Defensive: empty staff_code / kpi / period -> False."""
        from utils import kpi_ownership
        d = _seed_isolated_data_dir(tmp_path, {}, {}, {})
        monkeypatch.setattr(
            kpi_ownership, "_data_dir", lambda: d)
        kpi_ownership._refresh_caches()

        assert kpi_ownership.is_kpi_owned_by_staff(
            "", "PBT", "2026") is False
        assert kpi_ownership.is_kpi_owned_by_staff(
            "S001", "", "2026") is False
        assert kpi_ownership.is_kpi_owned_by_staff(
            "S001", "PBT", "") is False


# ─── kpi_aggregation_rules tests — one per pattern ──────────────────────

class TestAggregationPatterns:

    def test_count_pattern(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_COUNT, compute_rule)
        rule = AggregationRule(
            kpi_id="TEST_COUNT", source_table="t",
            pattern=PATTERN_COUNT,
            predicate=lambda r: r.get("status") == "approved",
            period_field="created_at",
        )
        rows = [
            {"officer": "A", "status": "approved",
             "created_at": "2026-04-15"},
            {"officer": "A", "status": "approved",
             "created_at": "2026-04-20"},
            {"officer": "A", "status": "rejected",
             "created_at": "2026-04-22"},
            {"officer": "B", "status": "approved",
             "created_at": "2026-04-15"},
            # Wrong period — should be excluded
            {"officer": "A", "status": "approved",
             "created_at": "2026-03-15"},
        ]
        result = compute_rule(rule, rows, "2026-04", "officer")
        assert result == {"A": 2, "B": 1}

    def test_sum_pattern(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_SUM, compute_rule)
        rule = AggregationRule(
            kpi_id="TEST_SUM", source_table="t",
            pattern=PATTERN_SUM,
            predicate=lambda r: r.get("status") == "disbursed",
            value_field="amount",
            period_field="disbursed_at",
            decimals=0,
        )
        rows = [
            {"officer": "A", "status": "disbursed",
             "amount": 100000, "disbursed_at": "2026-04-15"},
            {"officer": "A", "status": "disbursed",
             "amount": 50000, "disbursed_at": "2026-04-20"},
            {"officer": "B", "status": "pending",
             "amount": 999, "disbursed_at": "2026-04-15"},
        ]
        result = compute_rule(rule, rows, "2026-04", "officer")
        assert result == {"A": 150000}

    def test_percentage_pattern(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_PERCENTAGE, compute_rule)
        rule = AggregationRule(
            kpi_id="TEST_PCT", source_table="t",
            pattern=PATTERN_PERCENTAGE,
            numerator_pred=lambda r: r.get("stage") == "won",
            denominator_pred=lambda r: r.get("stage") in ("won", "lost"),
            period_field="closed_at",
        )
        rows = [
            {"rm": "X", "stage": "won", "closed_at": "2026-04-10"},
            {"rm": "X", "stage": "lost", "closed_at": "2026-04-12"},
            {"rm": "X", "stage": "lost", "closed_at": "2026-04-14"},
            {"rm": "X", "stage": "open", "closed_at": "2026-04-16"},
        ]
        result = compute_rule(rule, rows, "2026-04", "rm")
        # 1 won / 3 closed (won+lost) = 33.33%
        assert result["X"] == 33.33

    def test_tat_days_pattern(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_TAT_DAYS, compute_rule)
        rule = AggregationRule(
            kpi_id="TEST_TAT", source_table="t",
            pattern=PATTERN_TAT_DAYS,
            start_field="application_date",
            end_field="decision_date",
            predicate=lambda r: r.get("status") == "decided",
            period_field="decision_date",
            decimals=1,
        )
        rows = [
            {"officer": "A", "status": "decided",
             "application_date": "2026-04-01",
             "decision_date": "2026-04-04"},  # 3 days
            {"officer": "A", "status": "decided",
             "application_date": "2026-04-10",
             "decision_date": "2026-04-15"},  # 5 days
        ]
        result = compute_rule(rule, rows, "2026-04", "officer")
        assert result["A"] == 4.0  # mean of [3, 5]

    def test_ratio_pattern_with_zero_denominator(self):
        """RATIO pattern with denominator sum of zero -> staff omitted
        (returns None, which compute_rule drops)."""
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_RATIO, compute_rule)
        rule = AggregationRule(
            kpi_id="TEST_RATIO", source_table="t",
            pattern=PATTERN_RATIO,
            numerator_field="recovered",
            denominator_field="npl",
            predicate=lambda r: True,
        )
        rows = [
            {"recoverer": "A", "recovered": 0, "npl": 0},
        ]
        result = compute_rule(rule, rows, "", "recoverer")
        assert "A" not in result  # dropped due to zero denominator

    def test_bool_fraction_pattern(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_BOOL_FRACTION, compute_rule)
        rule = AggregationRule(
            kpi_id="TEST_BOOL", source_table="t",
            pattern=PATTERN_BOOL_FRACTION,
            bool_field="passed",
            predicate=lambda r: r.get("review_completed") is True,
            period_field="reviewed_at",
        )
        rows = [
            {"reviewer": "Z", "review_completed": True, "passed": True,
             "reviewed_at": "2026-04-05"},
            {"reviewer": "Z", "review_completed": True, "passed": True,
             "reviewed_at": "2026-04-10"},
            {"reviewer": "Z", "review_completed": True, "passed": False,
             "reviewed_at": "2026-04-15"},
            {"reviewer": "Z", "review_completed": False, "passed": False,
             "reviewed_at": "2026-04-20"},  # filtered out by predicate
        ]
        result = compute_rule(rule, rows, "2026-04", "reviewer")
        # 2 of 3 applicable rows passed -> 66.67%
        assert result["Z"] == 66.67

    def test_invalid_rule_rejected(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, register, PATTERN_SUM)
        bad_rule = AggregationRule(
            kpi_id="BAD", source_table="t",
            pattern=PATTERN_SUM,
            # Missing predicate AND value_field
        )
        with pytest.raises(ValueError, match="SUM requires"):
            register(bad_rule)


# ─── staff_field_resolver tests ─────────────────────────────────────────

class TestStaffFieldResolver:
    def test_known_table_returns_specific_field(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("loan_applications") == "assigned_officer"
        assert resolve_staff_field("pipeline") == "rm_code"
        assert resolve_staff_field("debt_recovery") == "recovery_officer"
        assert resolve_staff_field("legal_matters") == "attorney"

    def test_unknown_table_returns_default(self):
        from utils.staff_field_resolver import (
            resolve_staff_field, DEFAULT_STAFF_FIELD)
        assert resolve_staff_field("unknown_table") == DEFAULT_STAFF_FIELD
        assert DEFAULT_STAFF_FIELD == "staff_code"

    def test_override_takes_precedence(self):
        from utils.staff_field_resolver import resolve_staff_field
        # loan_applications normally → assigned_officer; override wins.
        assert resolve_staff_field(
            "loan_applications", "supervisor_code") == "supervisor_code"

    def test_empty_override_ignored(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field(
            "loan_applications", "") == "assigned_officer"


# ─── End-to-end simulation: the ownership-gate enforcement test ────────

class TestEndToEndOwnershipGate:
    """The headline test of v10.108. Synthetic loan_applications
    table with 5 RMs. Only 4 own K011 ('Loan Processing TAT') in
    their role_kpis. Autofit must submit actuals for 4, drop the
    5th silently."""

    def test_5_rms_one_dropped_via_ownership_gate(
            self, tmp_path, monkeypatch):
        from utils import kpi_ownership, actuals_engine

        # Set up: 5 RMs, all with same role 'Relationship Manager'.
        # Real library role_kpis has K011 in Relationship Manager?
        # We'll set up a custom library to control ownership precisely.
        custom_lib = {
            "pillars": [
                {"id": "Operational Excellence", "weight": 0.25},
                {"id": "Financial", "weight": 0.40},
            ],
            "kpis": [
                {"id": "K011", "code": "LOAN_TAT",
                 "name": "Loan Processing TAT",
                 "pillar": "Operational Excellence", "weight": 0.10,
                 "unit": "days", "direction": "lower",
                 "active": True, "description": "Mean TAT",
                 "source": "loan_applications"}
            ],
            "role_kpis": {
                "Relationship Manager": ["K011"],
                "Operations Officer":   [],   # NO K011
            },
        }

        # 4 RMs are 'Relationship Manager' (own K011).
        # 1 is 'Operations Officer' (no K011 in role_kpis,
        # no cascade lock -> not owned).
        users = {
            "rm1": {"staff_code": "RM001",
                    "role": "Relationship Manager"},
            "rm2": {"staff_code": "RM002",
                    "role": "Relationship Manager"},
            "rm3": {"staff_code": "RM003",
                    "role": "Relationship Manager"},
            "rm4": {"staff_code": "RM004",
                    "role": "Relationship Manager"},
            "ops": {"staff_code": "RM005",
                    "role": "Operations Officer"},
        }

        # Synthetic loan_applications table — each RM has 2 applications
        # decided in 2026-04, with realistic TAT values.
        loan_apps = []
        for sc, days in [("RM001", [3, 5]),  ("RM002", [4, 6]),
                         ("RM003", [2, 8]),  ("RM004", [10, 14]),
                         ("RM005", [7, 9])]:
            for i, d in enumerate(days):
                start = f"2026-04-{1 + i*5:02d}"
                end_day = 1 + i*5 + d
                end = f"2026-04-{end_day:02d}"
                loan_apps.append({
                    "assigned_officer": sc,
                    "status": "approved",
                    "application_date": start,
                    "decision_date": end,
                })

        # Cascade is empty — only role-default ownership in this test.
        cascade = {}

        d = _seed_isolated_data_dir(
            tmp_path, users, cascade,
            {"loan_applications": loan_apps},
            kpi_library=custom_lib)

        # Redirect both modules' data_dir to our isolated one
        monkeypatch.setattr(
            kpi_ownership, "_data_dir", lambda: d)
        kpi_ownership._refresh_caches()
        # The actuals_engine uses get_cbs_paths() to find data_dir;
        # patch it to return our isolated one.
        monkeypatch.setattr(
            actuals_engine, "get_cbs_paths",
            lambda: (d, d))

        # Patch the BSC submit so we can inspect what was submitted
        # without exercising the real bsc_engine persistence chain.
        submitted_records = []

        def fake_submit_batch(records, source_module, actor):
            submitted_records.extend(records)
            return {"ok": len(records), "rejected": 0, "errors": []}

        # Patch at the kpi_aggregation_rules import site by patching
        # bsc_engine.submit_batch directly. Both kpi_ownership lookups
        # and the function under test pull bsc_engine fresh.
        with patch("utils.bsc_engine.submit_batch",
                   side_effect=fake_submit_batch):
            result = actuals_engine.compute_actuals_from_operational_tables(
                "2026-04")

        # The contract:
        # - 5 staff appeared in loan_applications.
        # - 4 owned K011 (Relationship Managers).
        # - 1 did not (Operations Officer).
        # - actuals_submitted should be 4, dropped should be 1.
        assert result["success"] is True
        assert result["actuals_submitted"] == 4, (
            f"Expected 4 owned actuals submitted, got "
            f"{result['actuals_submitted']}. by_rule={result['by_rule']}")
        assert result["actuals_dropped"] == 1, (
            f"Expected 1 actual dropped via ownership gate, got "
            f"{result['actuals_dropped']}. by_rule={result['by_rule']}")

        # Verify only the 4 RMs (not the Operations Officer) made it
        # to bsc_engine.submit_batch.
        submitted_codes = {r["staff_code"] for r in submitted_records}
        assert submitted_codes == {"RM001", "RM002", "RM003", "RM004"}, (
            f"Expected only RM001-RM004 submitted, got {submitted_codes}. "
            f"RM005 should have been silently dropped by the ownership "
            f"gate because Operations Officer has no K011 in role_kpis.")

        # Verify all submissions were for K011
        assert all(r["kpi_id"] == "K011" for r in submitted_records)

        # Verify period
        assert all(r["period"] == "2026-04" for r in submitted_records)


class TestG143GateMode:
    """Verifies G143 ships in informational-pass mode."""

    def test_g143_passes_in_informational_mode(self):
        """Even when registry is incomplete, G143 returns passed=True
        in v10.108. Strict mode is v10.110+."""
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            result = audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)
        assert result["id"] == "G143"
        assert result["passed"] is True, (
            f"G143 should pass in informational mode in v10.108. "
            f"Summary: {result['summary']}")
        # The informational summary must surface coverage progress
        assert "informational" in result["summary"].lower()
        assert "operational-source KPIs" in result["summary"]
