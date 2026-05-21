"""tests/integration/test_v10496_design_system.py

v10.496 — Integration tests for the React design system batch.

Verifies on the user's machine after extracting the zip:
  1. All 8 primitive component files exist in src/components/
  2. lib/cn.ts and lib/tokens.ts exist
  3. types/components.ts exists
  4. Showcase page exists
  5. Dashboard refactor: imports from @/components/*
  6. App.tsx wires the /components route AND ToastProvider
  7. tokens.ts defines the required token categories
  8. No file in src/components/** has hardcoded hex colors
     (except via var(--brand-*))
  9. G382 audit gate is registered in scripts/audit.py
"""

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = REPO_ROOT / "frontend" / "web" / "src"


# ─────────────────────────────────────────────────────────────────
# Primitive presence
# ─────────────────────────────────────────────────────────────────

class TestPrimitivesExist:
    """All 8 design-system primitives are present."""

    REQUIRED = [
        "Button.tsx", "Card.tsx", "Input.tsx", "Stat.tsx",
        "Badge.tsx", "Toast.tsx", "Skeleton.tsx", "Table.tsx",
    ]

    @pytest.mark.parametrize("name", REQUIRED)
    def test_component_exists(self, name):
        path = SRC / "components" / name
        assert path.exists(), (
            f"frontend/web/src/components/{name} missing"
        )


class TestSupportFilesExist:
    """Helper utilities and types."""

    def test_cn_utility_exists(self):
        assert (SRC / "lib" / "cn.ts").exists()

    def test_tokens_file_exists(self):
        assert (SRC / "lib" / "tokens.ts").exists()

    def test_component_types_exist(self):
        assert (SRC / "types" / "components.ts").exists()

    def test_showcase_page_exists(self):
        assert (SRC / "pages" / "Showcase.tsx").exists()


# ─────────────────────────────────────────────────────────────────
# Dashboard refactor
# ─────────────────────────────────────────────────────────────────

class TestDashboardRefactor:
    """Dashboard.tsx now composes from primitives."""

    def test_dashboard_imports_components(self):
        src = (SRC / "pages" / "Dashboard.tsx").read_text(
            encoding="utf-8"
        )
        assert "@/components/" in src, (
            "Dashboard.tsx not refactored — still uses inline styles only"
        )

    def test_dashboard_no_hardcoded_bank_name(self):
        src = (SRC / "pages" / "Dashboard.tsx").read_text(
            encoding="utf-8"
        )
        assert "Ecobank" not in src


# ─────────────────────────────────────────────────────────────────
# App.tsx wiring
# ─────────────────────────────────────────────────────────────────

class TestAppTsxWiring:

    def test_app_has_components_route(self):
        src = (SRC / "App.tsx").read_text(encoding="utf-8")
        assert 'path="/components"' in src

    def test_app_has_toast_provider(self):
        src = (SRC / "App.tsx").read_text(encoding="utf-8")
        assert "ToastProvider" in src

    def test_app_preserves_g381_contract_literals(self):
        """Even with v10.496 amendments, G381's original literals
        must still be present."""
        src = (SRC / "App.tsx").read_text(encoding="utf-8")
        for lit in [
            "import { QueryClient, QueryClientProvider } "
                "from '@tanstack/react-query'",
            "const queryClient = new QueryClient()",
            "<QueryClientProvider client={queryClient}>",
            "<AuthProvider><WebSocketProvider><BrowserRouter>",
            'path="/"',
            'path="/perform"',
            'path="/profitability"',
            "BrandingProvider",
        ]:
            assert lit in src, f"App.tsx missing literal: {lit[:60]}"


# ─────────────────────────────────────────────────────────────────
# Tokens
# ─────────────────────────────────────────────────────────────────

class TestTokens:
    """tokens.ts exposes the canonical design tokens."""

    def test_tokens_defines_semantic_categories(self):
        src = (SRC / "lib" / "tokens.ts").read_text(encoding="utf-8")
        for category in ["gray", "success", "warning", "danger", "info"]:
            assert category in src, (
                f"tokens.ts missing semantic category: {category}"
            )

    def test_tokens_exports_size_variant_tone_types(self):
        src = (SRC / "lib" / "tokens.ts").read_text(encoding="utf-8")
        assert "export type Size" in src
        assert "export type Variant" in src
        assert "export type Tone" in src


# ─────────────────────────────────────────────────────────────────
# Brand discipline (G382)
# ─────────────────────────────────────────────────────────────────

class TestBrandDiscipline:
    """No hardcoded hex colors in components/** (G382)."""

    def test_no_hex_in_components(self):
        components_dir = SRC / "components"
        if not components_dir.exists():
            pytest.skip("Components dir missing")
        hex_re = re.compile(r"#[0-9a-fA-F]{6}\b")
        violations = []
        for tsx in components_dir.rglob("*.tsx"):
            text = tsx.read_text(encoding="utf-8")
            stripped = re.sub(r"var\(--brand-[a-z]+\)", "", text)
            matches = hex_re.findall(stripped)
            if matches:
                violations.append((tsx.name, matches[:3]))
        assert not violations, (
            f"Hardcoded hex colors in components: {violations}"
        )

    def test_only_tokens_ts_has_semantic_hex(self):
        """tokens.ts is the source of truth for semantic colors;
        no other file under lib/ or types/ should redefine them."""
        for ts in (SRC / "lib").rglob("*.ts"):
            if ts.name == "tokens.ts":
                continue
            text = ts.read_text(encoding="utf-8")
            # Find any hex
            matches = re.findall(r"#[0-9a-fA-F]{6}\b", text)
            assert not matches, (
                f"{ts.name} should not contain hex colors "
                f"(use tokens.ts): {matches}"
            )


# ─────────────────────────────────────────────────────────────────
# Audit gate
# ─────────────────────────────────────────────────────────────────

class TestAuditGate:

    def test_g382_registered(self):
        audit_py = (REPO_ROOT / "scripts" / "audit.py").read_text(
            encoding="utf-8"
        )
        assert "gate_v10496_design_system" in audit_py, (
            "scripts/audit.py doesn't contain G382"
        )
        assert '"G382"' in audit_py, "G382 not in GATES tuple"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
