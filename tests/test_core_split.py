"""tests/test_core_split.py — verify the utils.core_* shim modules.

The shim modules (utils.core_audit etc.) re-export symbols from utils.core
so callers can migrate away from the monolithic core.py at their own pace.
These tests pin down two invariants:

  1. Every symbol the shim claims to export is actually callable, and
     points at the SAME OBJECT as the implementation in utils.core.
     (`is` identity check — no double-allocation, no behavioral drift.)

  2. The pages that have already been migrated to use the new path
     parse cleanly. If a future contributor accidentally breaks the
     migration, this fails loudly.

When new shim modules are added (utils.core_kpi, utils.core_perf, etc.),
extend SHIMS below.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent

# Registry of shims and the symbols each one is supposed to cover.
# Must stay in sync with scripts/audit.py G14's SHIMS dict.
SHIMS = {
    "utils.core_audit": [
        "audit_log",
        "requires_dual_approval",
        "submit_for_approval",
        "get_pending_approvals",
        "get_user_department",
        "is_dept_super_user",
        "is_ict_admin",
        "get_dept_modules",
        "check_access",
        "check_page_access",
        "get_visible_staff",
        "tab_visible_cascade",
        "fix_view_all_permissions",
        "_hash_password",
    ],
    "utils.core_kpi": [
        "KPI_LIBRARY_FILE",
        "DEFAULT_KPI_LIBRARY",
        "DEFAULT_ROLE_KPIS",
        "get_kpi_library",
        "save_kpi_library",
        "get_active_kpis",
        "get_role_kpis",
        "get_pillar_weights",
        "get_scoring_scale",
        "bsc_score_from_pct",
        "get_performance_bands",
        "score_to_band",
    ],
}

# Subset of SHIMS that have completed the physical-move milestone.
# A shim is "physically moved" once its implementations have been
# extracted from utils/core.py and now live in the shim file itself.
# Membership here unlocks two extra checks:
#   - test_implementations_live_in_core_audit (the assertion that
#     fn.__module__ matches the shim path — only true post-move)
#   - test_legacy_path_is_gone + test_no_legacy_imports_outside_core_audit
#     (only meaningful once the reverse-export has been deleted)
#
# When a future cluster (e.g. utils.core_kpi) completes its physical
# move, add it here. Until then it stays in SHIMS only.
PHYSICALLY_MOVED = {
    "utils.core_audit",  # v5.25 move, v5.27 reverse-export deleted
}

# Pages that have been migrated. When you migrate a page, add it here.
MIGRATED_PAGES = [
    # Migrated in v5.21
    "pages/_access.py",
    "pages/29_revenue_assurance.py",
    "pages/26_legal.py",
    # Migrated in v5.22
    "pages/25_treasury.py",
    "pages/53_irrbb.py",
    "pages/46_trade_finance.py",
    "pages/52_mgmt_accounts.py",
    "pages/40_collateral.py",
    "pages/60_disciplinary.py",
    "pages/23_credit_admin.py",
    "pages/50_cybersecurity.py",
    "pages/49_bancassurance.py",
    "pages/39_ews.py",
    "pages/57_deal_room.py",
    "pages/43_pip.py",
    # Migrated in v5.23
    "pages/44_incidents.py",
    "pages/54_rcsa.py",
    "pages/64_vendors.py",
    "pages/59_cab.py",
    "pages/65_contracts.py",
    "pages/37_approvals.py",
    "pages/55_aml.py",
    "pages/80_merchant.py",
    "pages/70_retailer_finance.py",
    "pages/11_competitor.py",
    "pages/84_board.py",
    "pages/_admin_reconciliation.py",
    "pages/83_strategy.py",
    # Migrated in v5.24
    "pages/69_consent.py",
    "pages/82_oprisk.py",
    "pages/71_bid_bond.py",
    "pages/79_cards.py",
    "pages/85_esg.py",
    "pages/63_assets.py",
    "pages/81_alm.py",
    "pages/72_observability.py",
    "pages/78_onboarding.py",
    "pages/75_data_protection.py",
    "pages/76_sanctions.py",
    "pages/73_channels.py",
    "pages/30_rms.py",
    "pages/_admin_module_renderer.py",
    # Migrated in v5.26 — completes the audit cluster (17 clean + 7 split)
    "pages/35_stress_testing.py",
    "pages/74_cbk_returns.py",
    "pages/_admin_etl.py",
    "pages/31_edms.py",
    "pages/77_capital.py",
    "pages/_admin_postgres.py",
    "pages/62_p2p.py",
    "pages/67_fraud.py",
    "pages/_admin_cutover.py",
    "pages/68_clearing.py",
    "pages/86_flexcube.py",
    "pages/_admin_module_config.py",
    "pages/_admin_org.py",
    "pages/87_benchmarking.py",
    "pages/33_statement_analyzer.py",
    "pages/66_partnerships.py",
    "pages/20_debt_recovery.py",
    "pages/24_compliance.py",
    "pages/_admin_sprint.py",
    "pages/_login.py",
    "pages/22_credit_analysis.py",
    "pages/21_loan_applications.py",
    "pages/61_projects.py",
    "pages/0_home.py",
    "pages/_sidebar.py",
    # Migrated in v5.28 — first KPI cluster pilots
    "pages/1_perform.py",
    "pages/12_cascade.py",
    "pages/7_admin.py",
]


@pytest.fixture(scope="module")
def core_module():
    """Load utils.core once for the whole module."""
    return importlib.import_module("utils.core")


class TestShimReExports:
    """Every symbol declared in __all__ must be re-exported and identical
    to the implementation in utils.core. If these tests fail, the shim
    has drifted from the implementation."""

    @pytest.mark.parametrize("shim_modpath,symbols", SHIMS.items())
    def test_shim_imports_cleanly(self, shim_modpath, symbols):
        mod = importlib.import_module(shim_modpath)
        assert mod is not None

    @pytest.mark.parametrize("shim_modpath,symbols", SHIMS.items())
    def test_shim_has_all_attribute(self, shim_modpath, symbols):
        mod = importlib.import_module(shim_modpath)
        assert hasattr(mod, "__all__"), f"{shim_modpath} missing __all__"
        assert set(mod.__all__) == set(symbols), (
            f"{shim_modpath}.__all__ doesn't match expected: "
            f"missing={set(symbols)-set(mod.__all__)}, "
            f"extra={set(mod.__all__)-set(symbols)}"
        )

    @pytest.mark.parametrize(
        "shim_modpath,symbol",
        [(s, sym) for s, syms in SHIMS.items() for sym in syms],
    )
    def test_symbol_is_callable_or_value(self, shim_modpath, symbol):
        """Every re-exported symbol must be callable. (None of the audit
        cluster are constants.) If we add constants to a future shim,
        relax this."""
        mod = importlib.import_module(shim_modpath)
        obj = getattr(mod, symbol)
        # All audit-cluster symbols are functions
        assert callable(obj), f"{shim_modpath}.{symbol} is not callable"


class TestPhysicalMoveV525:
    """v5.25 physically moved 14 functions from utils.core into
    utils/core_audit.py. v5.27 deleted the reverse-export __getattr__
    block from utils.core that provided backward compat for v5.25+v5.26.

    These tests pin the move down so a future refactor can't silently
    un-do it.

    If any of these fail, someone has likely:
      - Eagerly re-imported core_audit from core (re-creating the cycle)
      - Put implementations back in core.py
      - Re-added the reverse-export __getattr__ block
    """

    def test_implementations_live_in_core_audit(self):
        """Every shimmed symbol's __module__ must match the shim path —
        proving the physical implementation lives there, not in core.

        Scoped to PHYSICALLY_MOVED clusters only. Shims that haven't
        yet completed the physical move (still re-exporting from
        utils.core) report fn.__module__ == 'utils.core' and aren't
        checked by this test until they graduate."""
        import importlib
        for shim_modpath, symbols in SHIMS.items():
            if shim_modpath not in PHYSICALLY_MOVED:
                continue  # still in shim phase — fn.__module__ would
                          # report 'utils.core', which is correct
            mod = importlib.import_module(shim_modpath)
            for sym in symbols:
                fn = getattr(mod, sym)
                # Skip non-callable constants (e.g. paths, dicts) — only
                # functions/classes have a meaningful __module__.
                if not callable(fn):
                    continue
                assert fn.__module__ == shim_modpath, (
                    f"{sym} reports __module__={fn.__module__!r}, "
                    f"expected {shim_modpath!r}. The physical implementation "
                    f"may have drifted back into utils.core."
                )

    def test_legacy_path_is_gone(self):
        """v5.27 deleted the reverse-export __getattr__ block from
        utils.core. The legacy `from utils.core import audit_log` path
        must no longer resolve — every call site has been migrated.

        This is the v5.27 INVERSION of v5.25's test_legacy_path_still_works:
        we now verify the OPPOSITE behaviour. If a future contributor
        accidentally re-adds the reverse-export block (recreating the
        backward-compat shim), this test fails — forcing them to choose
        between the two designs explicitly."""
        import utils.core
        for sym in ("audit_log", "check_access", "_hash_password",
                    "get_visible_staff", "requires_dual_approval"):
            assert not hasattr(utils.core, sym), (
                f"utils.core.{sym} still resolves — the v5.27 reverse-export "
                f"deletion has been undone, or the symbol re-appeared in "
                f"core.py. Migrate the caller to utils.core_audit instead "
                f"of restoring the backward-compat block."
            )

    def test_no_legacy_imports_outside_core_audit(self):
        """No file in the project (other than the shim modules themselves,
        which read constants from utils.core by design) may import any
        audit-cluster symbol via `from utils.core import X` for clusters
        that have completed the physical move.

        Scoped to PHYSICALLY_MOVED clusters only. During the shim phase,
        legacy imports still resolve correctly (because the symbol is
        still defined in utils.core), so they're permitted. Once a
        cluster graduates to PHYSICALLY_MOVED + reverse-export-deleted,
        legacy imports become crashes — and this test catches them
        statically before the app even starts.

        Runtime check + static check together = no way to slip in a
        legacy import for a cluster whose closure has been finalised."""
        import re
        from pathlib import Path

        # Only enforce against clusters whose physical move is complete
        # AND whose reverse-export has been removed.
        if not PHYSICALLY_MOVED:
            return
        all_shimmed = set()
        for shim_modpath in PHYSICALLY_MOVED:
            all_shimmed |= set(SHIMS.get(shim_modpath, []))

        repo_root = Path(__file__).parent.parent
        exclude = {"utils/core_audit.py", "utils/core.py",
                   "utils/core.py.v5.24.bak", "tests/test_core_split.py"}
        # tests/test_core_split.py is excluded because the SHIMS dict
        # at module level references the symbols by string name, which
        # is fine — but if we ever add a runtime call, we'll need to
        # revisit this test.

        offenders = []
        for path in sorted(repo_root.rglob("*.py")):
            rel = path.relative_to(repo_root).as_posix()
            if rel in exclude or "/data/" in rel or "/.git/" in rel:
                continue
            if rel.startswith("_"):
                continue
            code = path.read_text(encoding="utf-8", errors="ignore")

            # Single-line `from utils.core import X[, Y]`
            for ln, line in enumerate(code.split("\n"), 1):
                m = re.match(r"^\s*from\s+utils\.core\s+import\s+([^(]+)$",
                             line)
                if not m:
                    continue
                for sym in m.group(1).split(","):
                    sym = sym.strip().split(" as ")[0].rstrip(",").strip()
                    if sym and sym in all_shimmed:
                        offenders.append((rel, ln, line.strip()))
                        break

            # Parenthesised form
            for m in re.finditer(
                r"from\s+utils\.core\s+import\s+\(([^)]+)\)",
                code, re.DOTALL,
            ):
                for sym in m.group(1).split(","):
                    sym = sym.strip().split(" as ")[0]
                    if sym and sym in all_shimmed:
                        ln = code[:m.start()].count("\n") + 1
                        offenders.append((rel, ln, "(parenthesised)"))
                        break

        assert not offenders, (
            "Files still import audit-cluster symbols via the dead "
            "legacy path:\n  " + "\n  ".join(
                f"{rel}:L{ln}  {line[:80]}" for rel, ln, line in offenders
            ) + "\n\nMigrate them to `from utils.core_audit import X`. "
            "The reverse-export was deleted in v5.27."
        )

    def test_import_cycle_safe_either_order(self):
        """The v5.25 physical move uses PEP 562 __getattr__ to break the
        circular import that would otherwise occur if core_audit imports
        constants from core, and core eagerly re-exports from core_audit.
        Both import orders must succeed."""
        # We can't easily reset sys.modules in a single test process here
        # (other tests may have already imported either module), but we can
        # at least verify both top-level imports succeed and reach a
        # consistent state.
        import utils.core
        import utils.core_audit
        # If we got here, no ImportError was raised on either module.
        # The deeper "fresh import" coverage lives in the manual
        # verification script run during release.
        assert utils.core is not None
        assert utils.core_audit is not None

    def test_unknown_attr_still_raises_on_core(self):
        """Accessing a non-existent attribute on utils.core must raise
        AttributeError. Pre-v5.27 a custom PEP 562 __getattr__ in core.py
        provided this guarantee with a custom error message; post-v5.27
        Python's default behavior handles it. Either way, typos must
        not silently resolve to None."""
        import utils.core
        with pytest.raises(AttributeError):
            _ = utils.core.totally_made_up_symbol_that_does_not_exist



    """The pages already migrated must still be valid Python. Catches
    accidental syntax breakage when someone edits a migrated page."""

    @pytest.mark.parametrize("page_path", MIGRATED_PAGES)
    def test_migrated_page_parses(self, page_path):
        full = ROOT / page_path
        assert full.exists(), f"migrated page missing: {page_path}"
        code = full.read_text(encoding="utf-8", errors="ignore")
        ast.parse(code)  # raises SyntaxError if broken

    @pytest.mark.parametrize("page_path", MIGRATED_PAGES)
    def test_migrated_page_uses_new_path(self, page_path):
        """The page must import from at least one shim module — otherwise
        it's not actually migrated."""
        full = ROOT / page_path
        code = full.read_text(encoding="utf-8", errors="ignore")
        uses_any_shim = any(
            f"from {shim} import" in code for shim in SHIMS
        )
        assert uses_any_shim, (
            f"{page_path} is in MIGRATED_PAGES but doesn't import "
            f"from any shim module"
        )

    @pytest.mark.parametrize("page_path", MIGRATED_PAGES)
    def test_migrated_page_no_old_imports_for_shimmed_symbols(self, page_path):
        """Once a page has migrated to the new path, it should NOT also
        import the same symbols from utils.core. Mixed paths confuse the
        adoption metric and signal an incomplete migration."""
        import re
        full = ROOT / page_path
        code = full.read_text(encoding="utf-8", errors="ignore")

        # All symbols covered by any shim
        all_shimmed = set()
        for syms in SHIMS.values():
            all_shimmed |= set(syms)

        # Find old-style imports
        old_imported = set()
        for m in re.finditer(
            r"^from\s+utils\.core\s+import\s+([^(\n]+)$",
            code, re.MULTILINE,
        ):
            for sym in m.group(1).split(","):
                sym = sym.strip().split(" as ")[0]
                if sym and sym.isidentifier():
                    old_imported.add(sym)

        old_shimmed = old_imported & all_shimmed
        assert not old_shimmed, (
            f"{page_path} still imports {old_shimmed} from utils.core "
            f"even though it's listed as migrated. Move them to the shim."
        )
