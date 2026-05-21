"""tests/test_documentation_completeness.py — Standard #7 invariants (v5.36).

These tests verify that the required documentation exists and meets the
content quality bar that audit gate G7 enforces. They duplicate G7's
checks intentionally — the gate runs in `audit.py` (manual / CI), the
tests run in pytest (every test invocation). Either signal alone would
miss drift; together they pin the contract.

The tests also verify the spec-mandated docs match the master spec's
Standard #7 requirements:
  - API Reference (OpenAPI)
  - Deployment Guide
  - DR Runbook
  - User Manuals (Staff/Manager) — that's TWO files
  - Admin Guide
  - Security Architecture
"""
from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"

# The 6 spec-required docs (Standard #7), expanded to 7 actual files
# because "User Manuals (Staff/Manager)" splits into two files.
SPEC_DOCS = [
    "API_REFERENCE.md",
    "DEPLOYMENT_GUIDE.md",
    "DR_RUNBOOK.md",
    "USER_MANUAL_STAFF.md",
    "USER_MANUAL_MANAGER.md",
    "ADMIN_GUIDE.md",
    "SECURITY_ARCHITECTURE.md",
]

# Pre-existing convention docs that must continue to exist
LEGACY_DOCS = [
    "ADMIN_CONVENTIONS.md",
    "PAGE_UX_STANDARDS.md",
    "FLEXCUBE_CUTOVER_RUNBOOK.md",
    "POSTGRESQL_MIGRATION_GUIDE.md",
    "LOAD_TESTING_RUNBOOK.md",
]

ALL_DOCS = SPEC_DOCS + LEGACY_DOCS


# ═══════════════════════════════════════════════════════════════════════
# File presence
# ═══════════════════════════════════════════════════════════════════════

class TestSpecDocsPresent:
    """Each Standard #7 doc must exist."""

    @pytest.mark.parametrize("doc", SPEC_DOCS)
    def test_spec_doc_exists(self, doc):
        path = DOCS / doc
        assert path.exists(), (
            f"Standard #7 requires {doc} in docs/. The spec lists this as "
            f"a mandatory document — operations / regulators will look "
            f"for it on day one."
        )

    @pytest.mark.parametrize("doc", LEGACY_DOCS)
    def test_legacy_doc_still_present(self, doc):
        path = DOCS / doc
        assert path.exists(), (
            f"Pre-existing doc {doc} is no longer in docs/. Documents are "
            f"never silently removed — if you intentionally retired this, "
            f"update REQUIRED_DOCS in scripts/audit.py and this test."
        )


# ═══════════════════════════════════════════════════════════════════════
# Content quality bar — each doc must be substantive, not a stub
# ═══════════════════════════════════════════════════════════════════════

# Minimum char counts. These match REQUIRED_DOC_CONTENT in scripts/audit.py.
MIN_CHARS = {
    "API_REFERENCE.md":           2000,
    "DEPLOYMENT_GUIDE.md":        2000,
    "DR_RUNBOOK.md":              2000,
    "USER_MANUAL_STAFF.md":       1500,
    "USER_MANUAL_MANAGER.md":     1500,
    "ADMIN_GUIDE.md":             2000,
    "SECURITY_ARCHITECTURE.md":   2000,
    "ADMIN_CONVENTIONS.md":       1000,
    "PAGE_UX_STANDARDS.md":       1000,
    "FLEXCUBE_CUTOVER_RUNBOOK.md":1000,
    "POSTGRESQL_MIGRATION_GUIDE.md":1000,
    "LOAD_TESTING_RUNBOOK.md":    1000,
}


class TestDocContentQuality:
    """Each doc must clear its minimum-content bar."""

    @pytest.mark.parametrize("doc,min_chars", sorted(MIN_CHARS.items()))
    def test_doc_meets_minimum_size(self, doc, min_chars):
        path = DOCS / doc
        if not path.exists():
            pytest.skip(f"{doc} doesn't exist (covered by other tests)")
        content = path.read_text(encoding="utf-8")
        assert len(content) >= min_chars, (
            f"{doc} is only {len(content)} chars; minimum is {min_chars}. "
            f"Banking documentation must be substantive, not a placeholder."
        )


class TestDocSpecificContent:
    """Each spec doc must contain section markers indicating real content."""

    def test_api_reference_describes_authentication(self):
        content = (DOCS / "API_REFERENCE.md").read_text(encoding="utf-8").lower()
        assert "authentication" in content
        assert "jwt" in content or "bearer" in content

    def test_api_reference_lists_endpoints(self):
        content = (DOCS / "API_REFERENCE.md").read_text(encoding="utf-8")
        # Must reference the actual endpoint families
        assert "/api/auth/login" in content
        assert "/api/health" in content

    def test_api_reference_documents_openapi(self):
        content = (DOCS / "API_REFERENCE.md").read_text(encoding="utf-8").lower()
        # The spec specifically calls out OpenAPI
        assert "openapi" in content

    def test_deployment_guide_covers_systemd_or_docker(self):
        content = (DOCS / "DEPLOYMENT_GUIDE.md").read_text(encoding="utf-8").lower()
        # Must cover SOME process supervision strategy
        assert any(s in content for s in ["systemd", "docker", "kubernetes"]), (
            "Deployment guide must explain how the app runs in production"
        )

    def test_deployment_guide_documents_environment_variables(self):
        content = (DOCS / "DEPLOYMENT_GUIDE.md").read_text(encoding="utf-8")
        # The required env vars must all be referenced by name
        for var in ["A2Z_DB_HOST", "A2Z_JWT_SECRET", "A2Z_DB_USER"]:
            assert var in content, (
                f"Deployment guide doesn't document {var} — operators "
                f"won't know it's required"
            )

    def test_dr_runbook_documents_rto_rpo(self):
        content = (DOCS / "DR_RUNBOOK.md").read_text(encoding="utf-8").lower()
        assert "rto" in content
        assert "rpo" in content

    def test_dr_runbook_has_pg_restore_procedure(self):
        content = (DOCS / "DR_RUNBOOK.md").read_text(encoding="utf-8").lower()
        assert "pg_restore" in content or "pg_dump" in content

    def test_user_manual_staff_explains_scorecard(self):
        content = (DOCS / "USER_MANUAL_STAFF.md").read_text(encoding="utf-8").lower()
        assert "scorecard" in content
        assert "kpi" in content

    def test_user_manual_manager_explains_team_features(self):
        content = (DOCS / "USER_MANUAL_MANAGER.md").read_text(encoding="utf-8").lower()
        assert "team" in content
        assert "approval" in content

    def test_admin_guide_explains_user_management(self):
        content = (DOCS / "ADMIN_GUIDE.md").read_text(encoding="utf-8").lower()
        assert "user" in content
        assert "audit" in content

    def test_security_architecture_documents_named_vulnerabilities(self):
        content = (DOCS / "SECURITY_ARCHITECTURE.md").read_text(encoding="utf-8").lower()
        # Must reference V-001 through V-004 by name
        for v in ["v-001", "v-002", "v-003", "v-004"]:
            assert v in content, (
                f"Security Architecture doesn't reference {v.upper()} — "
                f"the threat model is incomplete"
            )

    def test_security_architecture_links_to_audit_gates(self):
        content = (DOCS / "SECURITY_ARCHITECTURE.md").read_text(encoding="utf-8")
        # Must reference the gates that enforce each control
        for gate in ["G9", "G10", "G11", "G12"]:
            assert gate in content, (
                f"Security Architecture doesn't reference {gate} — "
                f"the link between controls and enforcement is missing"
            )


# ═══════════════════════════════════════════════════════════════════════
# Cross-document integrity
# ═══════════════════════════════════════════════════════════════════════

class TestCrossDocLinks:
    """Documents must link to each other where they reference siblings."""

    def test_api_reference_links_to_security(self):
        content = (DOCS / "API_REFERENCE.md").read_text(encoding="utf-8")
        # Should reference security architecture (the JWT/V-00X link)
        assert "Security" in content or "SECURITY" in content

    def test_deployment_links_to_dr(self):
        content = (DOCS / "DEPLOYMENT_GUIDE.md").read_text(encoding="utf-8")
        assert "DR_RUNBOOK" in content or "DR Runbook" in content or "Disaster" in content

    def test_admin_guide_links_to_other_docs(self):
        content = (DOCS / "ADMIN_GUIDE.md").read_text(encoding="utf-8")
        # Admin guide should link to at least 2 sibling docs
        sibling_links = sum(1 for sib in [
            "DEPLOYMENT_GUIDE.md", "DR_RUNBOOK.md",
            "SECURITY_ARCHITECTURE.md", "USER_MANUAL_MANAGER.md",
        ] if sib in content)
        assert sibling_links >= 2, (
            f"Admin guide links to only {sibling_links} sibling doc(s); "
            f"it should reference at least 2 for navigation"
        )


# ═══════════════════════════════════════════════════════════════════════
# G7 gate consistency
# ═══════════════════════════════════════════════════════════════════════

class TestG7Consistency:
    """REQUIRED_DOCS in audit.py must include every doc this test checks."""

    def test_audit_required_docs_includes_all_spec_docs(self):
        """audit.py's REQUIRED_DOCS list must cover every Standard #7 doc."""
        audit_src = (ROOT / "scripts" / "audit.py").read_text(encoding="utf-8")
        for doc in SPEC_DOCS:
            assert f'"{doc}"' in audit_src, (
                f"scripts/audit.py REQUIRED_DOCS doesn't include {doc} — "
                f"G7 won't enforce its presence"
            )

    def test_audit_required_doc_content_includes_spec_docs(self):
        """audit.py's REQUIRED_DOC_CONTENT must specify quality bars."""
        audit_src = (ROOT / "scripts" / "audit.py").read_text(encoding="utf-8")
        for doc in SPEC_DOCS:
            assert f'"{doc}"' in audit_src
            # Each spec doc should be in REQUIRED_DOC_CONTENT
            # (very loose check — just that the doc name appears at
            # least twice: once in REQUIRED_DOCS, once in REQUIRED_DOC_CONTENT)
            assert audit_src.count(f'"{doc}"') >= 2, (
                f"{doc} appears only once in audit.py — it's listed in "
                f"REQUIRED_DOCS but missing from REQUIRED_DOC_CONTENT, "
                f"so G7 won't enforce content quality"
            )
