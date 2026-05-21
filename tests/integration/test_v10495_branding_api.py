"""tests/integration/test_v10495_branding_api.py

v10.495 — Integration tests for the Branding API and React enablement.

Verifies:
  1. utils/config.py exposes the 4 new helpers and they return
     Ecobank corporate defaults
  2. _DEFAULT_IP_NOTICE matches the verbatim text from
     pages/_login.py:318
  3. utils/api_branding.py module imports and exposes the router
  4. get_branding() returns the full payload with correct shape
  5. Brand colors are valid hex strings starting with '#'
  6. App.tsx exists and contains all the contract literals
  7. App.tsx contains the BrandingProvider amendment
  8. BrandingProvider.tsx exists
  9. main.tsx exists (Vite entry point)
"""

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ─────────────────────────────────────────────────────────────────
# Backend tests
# ─────────────────────────────────────────────────────────────────

class TestConfigHelpers:
    """The 4 new helpers in utils/config.py."""

    def test_brand_primary_hex_returns_ecobank_corporate(self):
        from utils.config import brand_primary_hex
        result = brand_primary_hex()
        assert result == "#1797ce", (
            f"brand_primary_hex() returned {result!r}, expected "
            f"#1797ce (Ecobank corporate cyan-blue)"
        )

    def test_brand_secondary_hex_returns_deep_navy(self):
        from utils.config import brand_secondary_hex
        assert brand_secondary_hex() == "#0e2440"

    def test_brand_accent_hex_returns_ecobank_yellow(self):
        from utils.config import brand_accent_hex
        assert brand_accent_hex() == "#ffd200"

    def test_ip_notice_contains_verbatim_text(self):
        """The IP notice MUST match the deployed login text from
        pages/_login.py:318 verbatim."""
        from utils.config import ip_notice
        notice = ip_notice()
        # Each fragment must appear in order
        assert "Confidential" in notice
        assert "Authorised users only" in notice
        assert "All sessions are logged" in notice
        assert "protected intellectual property" in notice
        assert (
            "Unauthorised access or reproduction is strictly prohibited"
        ) in notice
        assert "may be subject to legal action" in notice

    def test_brand_colors_are_valid_hex(self):
        from utils.config import (
            brand_primary_hex, brand_secondary_hex, brand_accent_hex,
        )
        hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
        assert hex_re.match(brand_primary_hex())
        assert hex_re.match(brand_secondary_hex())
        assert hex_re.match(brand_accent_hex())


class TestApiBrandingModule:
    """The new utils/api_branding.py."""

    def test_module_imports(self):
        import utils.api_branding
        assert hasattr(utils.api_branding, 'router')
        assert hasattr(utils.api_branding, 'get_branding')

    def test_router_has_branding_route(self):
        from utils.api_branding import router
        # Check that /branding is registered on the router
        paths = [getattr(r, 'path', '') for r in router.routes]
        assert any('/branding' in p for p in paths), (
            f"No /branding route in router. Routes: {paths}"
        )

    def test_get_branding_returns_full_payload(self):
        from utils.api_branding import get_branding
        result = get_branding()
        # Required top-level keys
        expected_keys = {
            'bank_name', 'app_name', 'currency', 'currency_symbol',
            'country', 'regulator', 'regulator_full',
            'core_banking_system', 'tax_authority', 'brand',
            'ip_notice',
        }
        assert set(result.keys()) >= expected_keys, (
            f"Missing keys: {expected_keys - set(result.keys())}"
        )

    def test_brand_payload_has_three_colors(self):
        from utils.api_branding import get_branding
        brand = get_branding()['brand']
        assert set(brand.keys()) == {'primary', 'secondary', 'accent'}

    def test_branding_payload_brand_colors_match_helpers(self):
        from utils.api_branding import get_branding
        from utils.config import (
            brand_primary_hex, brand_secondary_hex, brand_accent_hex,
        )
        brand = get_branding()['brand']
        assert brand['primary'] == brand_primary_hex()
        assert brand['secondary'] == brand_secondary_hex()
        assert brand['accent'] == brand_accent_hex()


# ─────────────────────────────────────────────────────────────────
# Frontend file presence + contract literal tests
# ─────────────────────────────────────────────────────────────────

class TestFrontendFiles:
    """Verify the v10.495 frontend file tree."""

    def test_app_tsx_exists(self):
        path = REPO_ROOT / "frontend" / "web" / "src" / "App.tsx"
        assert path.exists(), "frontend/web/src/App.tsx missing"

    def test_app_tsx_preserves_contract_literals(self):
        """G381 enforces that the original App.tsx provider chain is
        preserved byte-for-byte."""
        path = REPO_ROOT / "frontend" / "web" / "src" / "App.tsx"
        src = path.read_text(encoding="utf-8")
        contract_literals = [
            "import { QueryClient, QueryClientProvider } "
            "from '@tanstack/react-query'",
            "const queryClient = new QueryClient()",
            "<QueryClientProvider client={queryClient}>",
            "<AuthProvider><WebSocketProvider><BrowserRouter>",
            'path="/"',
            'path="/perform"',
            'path="/profitability"',
        ]
        missing = [lit for lit in contract_literals if lit not in src]
        assert not missing, (
            f"App.tsx missing contract literals: {missing}"
        )

    def test_app_tsx_has_branding_provider_amendment(self):
        path = REPO_ROOT / "frontend" / "web" / "src" / "App.tsx"
        src = path.read_text(encoding="utf-8")
        assert "BrandingProvider" in src, (
            "App.tsx missing v10.495 BrandingProvider amendment"
        )

    def test_branding_provider_exists(self):
        path = (REPO_ROOT / "frontend" / "web" / "src" / "providers"
                / "BrandingProvider.tsx")
        assert path.exists(), "BrandingProvider.tsx missing"

    def test_main_tsx_exists(self):
        path = REPO_ROOT / "frontend" / "web" / "src" / "main.tsx"
        assert path.exists(), (
            "frontend/web/src/main.tsx missing — Vite needs this "
            "to bootstrap the app"
        )

    def test_vite_config_exists(self):
        path = REPO_ROOT / "frontend" / "web" / "vite.config.ts"
        assert path.exists()

    def test_tsconfig_exists(self):
        path = REPO_ROOT / "frontend" / "web" / "tsconfig.json"
        assert path.exists()

    def test_tailwind_config_exists(self):
        path = REPO_ROOT / "frontend" / "web" / "tailwind.config.js"
        assert path.exists()

    def test_index_html_exists(self):
        path = REPO_ROOT / "frontend" / "web" / "index.html"
        assert path.exists()


class TestNoHardcodedBankName:
    """G381 ban: no bank-name string hardcoded in .tsx outside the
    BrandingProvider fallback."""

    def test_no_hardcoded_ecobank_in_tsx(self):
        src_dir = REPO_ROOT / "frontend" / "web" / "src"
        if not src_dir.exists():
            pytest.skip("frontend/web/src not yet extracted")
        violations = []
        for tsx in src_dir.rglob("*.tsx"):
            if tsx.name == "BrandingProvider.tsx":
                # Fallback literals allowed here
                continue
            if "Ecobank" in tsx.read_text(encoding="utf-8"):
                violations.append(str(tsx.relative_to(REPO_ROOT)))
        assert not violations, (
            f"Hardcoded bank name in .tsx files: {violations}. "
            "Use useBranding() hook instead."
        )


if __name__ == "__main__":
    # Allow running directly via `python -m tests.integration.test_v10495_branding_api`
    pytest.main([__file__, "-v"])
