"""tests/integration/test_v10_27_audit_gate_g123.py — v10.27 Audit/GRC arc closure.

Locks Phase 2 batch 4 (Audit/GRC arc, v10.23-v10.27). Mirrors v10.22 G122 +
v10.16 G121 + v10.10 G120 closure patterns.

Validates ENH-210 audit_trail_certification module shipped in v10.27.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1027G123GateRegistered(unittest.TestCase):
    def test_g123_function_exists(self):
        from scripts.audit import gate_audit_grc_engines_implemented
        self.assertTrue(callable(gate_audit_grc_engines_implemented))

    def test_g123_in_gates_list(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        self.assertIn("G123", gate_ids)

    def test_g123_after_g122(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        idx_122 = gate_ids.index("G122")
        idx_123 = gate_ids.index("G123")
        self.assertGreater(idx_123, idx_122)

    def test_total_gate_count_at_least_123(self):
        """At v10.27 closure, ≥123 gates."""
        from scripts.audit import GATES
        self.assertGreaterEqual(len(GATES), 123)


class TestV1027G123Passes(unittest.TestCase):
    def test_g123_passes(self):
        from scripts.audit import gate_audit_grc_engines_implemented
        r = gate_audit_grc_engines_implemented()
        self.assertTrue(r["passed"],
                          f"G123 should pass; violations: "
                          f"{r.get('violations')}")

    def test_g123_returns_correct_id(self):
        from scripts.audit import gate_audit_grc_engines_implemented
        r = gate_audit_grc_engines_implemented()
        self.assertEqual(r["id"], "G123")
        self.assertEqual(r["name"], "audit_grc_engines_implemented")

    def test_g123_summary_reports_closure_set_preserved(self):
        from scripts.audit import gate_audit_grc_engines_implemented
        r = gate_audit_grc_engines_implemented()
        self.assertIn("closure set 17/17 preserved", r["summary"])


class TestV1027ENH210Module(unittest.TestCase):
    """Validate ENH-210 audit_trail_certification module."""

    def test_module_imports(self):
        from utils import audit_trail_certification  # noqa

    def test_self_test_passes(self):
        from utils import audit_trail_certification
        audit_trail_certification.self_test()

    def test_chain_integrity_detects_tamper(self):
        from utils.audit_trail_certification import (
            append_entry, verify_chain_integrity,
            AuditTrailEventType, AuditTrailEntry)
        chain = []
        for i in range(3):
            e = append_entry(
                chain=chain, entry_id=f"E{i+1}",
                event_type=AuditTrailEventType.CONTROL_TEST_EXECUTED,
                timestamp_utc=f"2026-01-{i+1:02d}T10:00:00Z",
                actor_user_id="alice",
                source_engine="audit_core",
                target_object_type="Test",
                target_object_id=f"T{i+1}",
                payload={"verdict": "EFFECTIVE"})
            chain.append(e)
        # Verify intact
        self.assertTrue(verify_chain_integrity(chain=chain).is_intact)
        # Tamper middle entry's actor_user_id but keep stored hash
        chain[1] = AuditTrailEntry(
            entry_id=chain[1].entry_id,
            sequence_number=chain[1].sequence_number,
            event_type=chain[1].event_type,
            timestamp_utc=chain[1].timestamp_utc,
            actor_user_id="MALICIOUS",
            source_engine=chain[1].source_engine,
            target_object_type=chain[1].target_object_type,
            target_object_id=chain[1].target_object_id,
            payload_json=chain[1].payload_json,
            previous_hash=chain[1].previous_hash,
            entry_hash=chain[1].entry_hash)
        result = verify_chain_integrity(chain=chain)
        self.assertFalse(result.is_intact)
        self.assertEqual(result.first_break_sequence, 2)

    def test_attestation_dual_role_blocked(self):
        """Same user signing both CEO + CFO blocks ATTEST."""
        from utils.audit_trail_certification import (
            AuditTrailCertificationEngine,
            ComplianceAttestation, ComplianceFramework,
            AttestationStatus,
            AttestationSignature, CertifierAttestationRole)
        eng = AuditTrailCertificationEngine()
        eng.file_attestation(ComplianceAttestation(
            attestation_id="A1",
            framework=ComplianceFramework.SOX_302,
            period_label="x", period_start="2026-01-01",
            period_end="2026-03-31",
            status=AttestationStatus.SIGNATURES_PENDING,
            period_seal_id="S1",
            chain_hash_at_attestation="abc",
            signatures=(
                AttestationSignature(
                    signature_id="SG1",
                    role=CertifierAttestationRole.CEO,
                    user_id="dual_role_user",
                    signed_at_utc="t", signature_hash="h1"),
                AttestationSignature(
                    signature_id="SG2",
                    role=CertifierAttestationRole.CFO,
                    user_id="dual_role_user",    # SAME USER
                    signed_at_utc="t", signature_hash="h2"),
            )))
        with self.assertRaises(ValueError):
            eng.transition_attestation(
                attestation_id="A1",
                to_status=AttestationStatus.ATTESTED,
                actor_user_id="x", timestamp="t")


class TestV1027AllChangelogsPresent(unittest.TestCase):
    """All v10.23-v10.27 CHANGELOGs present."""

    def test_changelog_v10_23_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.23.md").exists())

    def test_changelog_v10_24_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.24.md").exists())

    def test_changelog_v10_25_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.25.md").exists())

    def test_changelog_v10_26_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.26.md").exists())

    def test_changelog_v10_27_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.27.md").exists())


class TestV1027MasterPromptVersion(unittest.TestCase):
    def test_master_prompt_at_v10_27_or_later(self):
        import re
        content = Path("Master_Prompt_v3.md").read_text(encoding="utf-8")
        matches = re.findall(r"v10\.(\d+)", content)
        self.assertTrue(matches)
        max_minor = max(int(m) for m in matches)
        self.assertGreaterEqual(max_minor, 27)


class TestV1027EngineHubIntegration(unittest.TestCase):
    """Engine Hub Tier 11 surfaces all 5 audit engines."""

    def test_tier_11_in_admin_page(self):
        content = Path("pages/7_admin.py").read_text(encoding="utf-8")
        self.assertIn("Tier 11", content)

    def test_all_5_audit_engines_in_hub(self):
        content = Path("pages/7_admin.py").read_text(encoding="utf-8")
        for engine in (
            "audit_core", "audit_controls_issues",
            "audit_analytics_vendor", "audit_dashboards_portal",
            "audit_trail_certification",
        ):
            self.assertIn(f'"{engine}"', content,
                            f"Engine Hub missing {engine}")


class TestV1027AllRequiredEnginesImport(unittest.TestCase):
    def test_all_5_engines_import(self):
        for module in (
            "utils.audit_core",
            "utils.audit_controls_issues",
            "utils.audit_analytics_vendor",
            "utils.audit_dashboards_portal",
            "utils.audit_trail_certification",
        ):
            try:
                __import__(module)
            except Exception as e:
                self.fail(f"Failed to import {module}: {e}")


class TestV1027AuditFullPasses(unittest.TestCase):
    """Full audit returns clean — closure verification."""

    def test_full_audit_passes(self):
        from scripts.audit import GATES
        passing = 0
        failing: list = []
        for gate_id, fn in GATES:
            r = fn()
            if r["passed"]:
                passing += 1
            else:
                failing.append(gate_id)
        self.assertEqual(
            passing, len(GATES),
            f"Expected {len(GATES)} passing gates; failing: {failing}")


class TestV1027AllPhase2ArcsClosed(unittest.TestCase):
    """All 4 closed Phase 2 arcs have closure gates passing."""

    def test_g120_climate_passes(self):
        from scripts.audit import gate_climate_esg_engines_implemented
        self.assertTrue(gate_climate_esg_engines_implemented()["passed"])

    def test_g121_credit_passes(self):
        from scripts.audit import gate_credit_engines_implemented
        self.assertTrue(gate_credit_engines_implemented()["passed"])

    def test_g122_rms_passes(self):
        from scripts.audit import gate_rms_engines_implemented
        self.assertTrue(gate_rms_engines_implemented()["passed"])

    def test_g123_audit_grc_passes(self):
        from scripts.audit import gate_audit_grc_engines_implemented
        self.assertTrue(gate_audit_grc_engines_implemented()["passed"])


if __name__ == "__main__":
    unittest.main()
