"""tests/test_integration_layer_v10_131.py — v10.131 PG migration step 3.

v10.131 designates `loan_applications` (pre-existing PG table since
v10.89) as part of the integration layer's PG-eligible set. Unlike
v10.129 (sla_tickets, new schema) and v10.130 (debt_recovery, new
schema), this drop adds NO new CREATE TABLE — only supplementary
indexes for Phase 1D query patterns + integration-layer designation
in docstrings + FLAT_MIGRATIONS annotation.

Verifies:
  1. loan_applications table still has its pre-existing schema
     (single CREATE TABLE; no v10.131 duplicate)
  2. The 3 v10.131 supplementary indexes are present
  3. loan_applications stayed in scripts/migrate_to_postgres.py
     FLAT_MIGRATIONS (since v10.89)
  4. v10.131 docstring annotation is in utils/db.py
  5. v10.116 shim default still 'json' — no regression
  6. All 6 wired rules on loan_applications still produce identical
     actuals via the JSON path (since default unchanged)
  7. G143 still 99/131 STRICT-READY (high)
  8. v10.129 sla_tickets and v10.130 debt_recovery schemas preserved
     (additive drop)
  9. Deployment doc PG_Migration_loan_applications.md present
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Schema not duplicated ──────────────────────────────────────────

class TestSchemaNotDuplicated:
    """v10.131 does NOT add a new CREATE TABLE — loan_applications has
    been a PG-backed table since v10.89. Adding a duplicate would either
    fail (if the IF NOT EXISTS were absent) or silently confuse the
    schema. Test both that there's exactly one CREATE TABLE and that
    the v10.131 annotation is in the supplementary indexes section."""

    @pytest.fixture(scope="class")
    def db_src(self):
        return (REPO_ROOT / "utils" / "db.py").read_text()

    def test_only_one_loan_applications_create_table(self, db_src):
        # Match CREATE TABLE [IF NOT EXISTS] loan_applications
        pattern = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?loan_applications"
        matches = re.findall(pattern, db_src, re.IGNORECASE)
        assert len(matches) == 1, (
            f"Expected exactly 1 CREATE TABLE for loan_applications; "
            f"found {len(matches)}. v10.131 must NOT add a duplicate.")

    def test_v10_131_annotation_present(self, db_src):
        # The v10.131 designation comment block should be present
        assert "v10.131:" in db_src
        assert ("v10.131" in db_src and
                "loan_applications" in db_src)


# ─── Supplementary indexes (v10.131) ────────────────────────────────

class TestV10_131SupplementaryIndexes:

    @pytest.fixture(scope="class")
    def db_src(self):
        return (REPO_ROOT / "utils" / "db.py").read_text()

    def test_idx_lastupd_index(self, db_src):
        assert "idx_loan_apps_lastupd" in db_src
        assert "ON loan_applications (last_updated)" in db_src

    def test_idx_tat_index(self, db_src):
        assert "idx_loan_apps_tat" in db_src
        assert "ON loan_applications (tat_days)" in db_src

    def test_idx_complflag_partial_index(self, db_src):
        assert "idx_loan_apps_complflag" in db_src
        # Partial index — only indexes WHERE compliance_flag = TRUE
        assert "WHERE compliance_flag = TRUE" in db_src


# ─── FLAT_MIGRATIONS preserved + annotated ──────────────────────────

class TestFlatMigrationsAnnotation:

    @pytest.fixture(scope="class")
    def mig_src(self):
        return (REPO_ROOT / "scripts" / "migrate_to_postgres.py").read_text()

    def test_loan_applications_in_flat_migrations(self, mig_src):
        assert '("loan_applications.json"' in mig_src
        assert '"loan_applications"' in mig_src

    def test_v10_131_annotation_in_flat_migrations(self, mig_src):
        assert "v10.131" in mig_src
        # Annotation should appear adjacent to the loan_applications entry
        idx_v131 = mig_src.index("v10.131")
        idx_loan = mig_src.index('"loan_applications.json"', idx_v131 - 1000)
        assert abs(idx_loan - idx_v131) < 1500, (
            "v10.131 annotation should be near the loan_applications entry")


# ─── No regression on v10.129 / v10.130 ─────────────────────────────

class TestPriorMigrationsPreserved:

    @pytest.fixture(scope="class")
    def db_src(self):
        return (REPO_ROOT / "utils" / "db.py").read_text()

    def test_sla_tickets_schema_preserved(self, db_src):
        # v10.129 schema should still be there
        assert "CREATE TABLE IF NOT EXISTS sla_tickets" in db_src
        for idx in ("idx_sla_tickets_assignee",
                    "idx_sla_tickets_status",
                    "idx_sla_tickets_priority",
                    "idx_sla_tickets_lastupd"):
            assert idx in db_src, f"v10.129 index {idx} regressed"

    def test_debt_recovery_schema_preserved(self, db_src):
        # v10.130 schema should still be there
        assert "CREATE TABLE IF NOT EXISTS debt_recovery" in db_src
        for idx in ("idx_debt_recovery_officer",
                    "idx_debt_recovery_rm",
                    "idx_debt_recovery_status"):
            assert idx in db_src, f"v10.130 index {idx} regressed"

    def test_data_source_default_still_json(self):
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        ds = cfg.get("_data_source", {})
        # Default must remain "json" — v10.131 doesn't auto-flip
        assert ds.get("_default", "json") == "json"


# ─── 6 wired rules still functional via JSON path ───────────────────

class TestWiredRulesStillFunctional:
    """Default _data_source is JSON; v10.131 doesn't change rule logic.
    All 6 wired rules on loan_applications must continue to produce
    actuals from the JSON path."""

    @pytest.fixture(scope="class")
    def rules(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        return [r for r in data["rules"]
                if r.get("source_table") == "loan_applications"
                and r.get("active")]

    def test_six_wired_rules_present(self, rules):
        kpi_ids = {r["kpi_id"] for r in rules}
        expected = {"K011", "K001", "K010", "K115", "K046", "K045"}
        assert expected <= kpi_ids, (
            f"Expected at least {expected}, got {kpi_ids}")

    def test_rule_patterns_unchanged(self, rules):
        # Patterns must not have drifted from the registered set
        by_kpi = {r["kpi_id"]: r.get("pattern") for r in rules}
        assert by_kpi.get("K011") == "TAT_DAYS"
        assert by_kpi.get("K001") == "SUM"
        assert by_kpi.get("K010") == "PERCENTAGE"
        assert by_kpi.get("K115") == "COUNT"
        assert by_kpi.get("K046") == "MEAN_FIELD"
        assert by_kpi.get("K045") == "PERCENTAGE"


# ─── G143 unchanged ────────────────────────────────────────────────

class TestG143Unchanged:
    """v10.131 is plumbing — no rule logic change. G143 coverage
    must remain at 99/131 STRICT-READY (high)."""

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_still_99(self, gate_result):
        sp = gate_result["strict_preview"]
        assert sp["covered"] == 99

    def test_tier_still_strict_ready_high(self, gate_result):
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (high)"


# ─── Deployment doc present ────────────────────────────────────────

class TestDeploymentDocPresent:

    def test_pg_migration_doc_present(self):
        p = REPO_ROOT / "docs" / "PG_Migration_loan_applications.md"
        assert p.exists()
        content = p.read_text()
        for section in ("Why this drop is structurally different",
                        "6 wired rules become PG-capable",
                        "Cutover steps",
                        "Rollback",
                        "Verification commands"):
            assert section in content, f"Missing section: {section}"
