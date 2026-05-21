"""BSC Admin Panel — v10.430 (UI wire-up).

Renders the BSC health dashboard inside the admin page. Pure UI module
that consumes the 6 BSC Rescue engines (v10.424-v10.429):

    bsc_audit_engine             — diagnostic
    bsc_pillar_normalize_engine  — pillar canonical fixes
    bsc_library_register_engine  — registers unregistered KPIs
    bsc_completeness_engine      — fills role_kpis gaps
    bsc_weight_normalize_engine  — renormalizes weight sums
    bsc_cascade_linkage_engine   — code alignment fixes

Architecture:
  - Streamlit for now (this module is the UI layer)
  - All data comes from the engines via their public API
  - Zero engine logic in this file — only render + dispatch
  - When React frontend lands, swap this module's rendering for
    JSX components; engine layer stays unchanged

Public API:
  - render_bsc_health_dashboard(can_run_repairs: bool = False)
      Renders the full dashboard; if can_run_repairs, shows "Run fix"
      buttons gated behind a confirmation modal.

Shipped: v10.430.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import streamlit as st


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

# Map of (audit_category_key) -> (category_label, repair_fn_dotted_path,
#                                  is_destructive, help_text)
# repair_fn_dotted_path is a tuple of (module, function_name) — resolved
# lazily so this module doesn't import all 6 engines at import time.
CATEGORY_REPAIRS: Dict[str, Dict[str, Any]] = {
    "staff_coverage": {
        "label": "1. Staff Coverage",
        "icon": "👥",
        "help": ("Every staff in register has BSC entries. "
                 "Missing rows are critical — staff without BSC can't be scored."),
        "repair": None,  # No repair engine; manual investigation
    },
    "kpi_completeness": {
        "label": "2. KPI Completeness",
        "icon": "📋",
        "help": ("Each staff has the canonical KPIs configured for their role "
                 "in kpi_library.role_kpis."),
        "repair": ("utils.bsc_completeness_engine", "repair_bsc_completeness"),
        "cleanup": ("utils.bsc_completeness_engine", "repair_code_alias_artifacts"),
    },
    "pillar_canonical": {
        "label": "3. Pillar Canonical",
        "icon": "🏛️",
        "help": ("Only the 4 canonical pillars (Financial, Customer Focus, "
                 "Operational Excellence, People & Learning) are used."),
        "repair": ("utils.bsc_pillar_normalize_engine", "migrate_actuals_pillars"),
    },
    "weight_normalization": {
        "label": "4. Weight Normalization",
        "icon": "⚖️",
        "help": ("Each staff's KPI weights sum to 1.0 — required for valid BSC score aggregation."),
        "repair": ("utils.bsc_weight_normalize_engine", "renormalize_actuals_weights"),
    },
    "library_alignment": {
        "label": "5. Library Alignment",
        "icon": "📚",
        "help": ("Every KPI in BSC actuals is registered in kpi_library.json "
                 "(by name, id, or alias)."),
        "repair": ("utils.bsc_library_register_engine", "apply_full_registration"),
    },
    "cascade_linkage": {
        "label": "6. Cascade Linkage",
        "icon": "🔗",
        "help": ("Staff codes in BSC actuals match canonical register codes "
                 "— ensures cascade↔BSC connectivity."),
        "repair": ("utils.bsc_cascade_linkage_engine", "fix_bsc_codes"),
    },
    "duplicate_rows": {
        "label": "7. Duplicate Rows",
        "icon": "🔍",
        "help": ("No (Staff, KPI) pair appears twice in BSC actuals."),
        "repair": None,  # Dedup is part of completeness engine
    },
}


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _resolve_repair_fn(path: Tuple[str, str]) -> Optional[Callable]:
    """Lazy-import a repair function: ('utils.x_engine', 'fn_name')."""
    try:
        import importlib
        mod = importlib.import_module(path[0])
        return getattr(mod, path[1], None)
    except Exception:  # noqa: BLE001
        return None


def _category_status(audit_obj: Any, category_key: str) -> Tuple[str, str, int]:
    """Return (emoji, label, count) for a category's traffic-light state."""
    if category_key == "staff_coverage":
        sc = audit_obj.staff_coverage
        missing = len(sc.in_register_not_in_bsc)
        ghosts = len(sc.in_bsc_not_in_register)
        if missing == 0 and ghosts == 0:
            return ("✅", f"{sc.coverage_pct}% covered", 0)
        return ("🔴", f"{missing} missing + {ghosts} ghosts", missing + ghosts)
    if category_key == "kpi_completeness":
        kc = audit_obj.kpi_completeness
        if kc.incomplete_count == 0:
            return ("✅", f"avg {kc.avg_kpis_per_staff} KPIs/staff", 0)
        return ("⚠️", f"{kc.incomplete_count} incomplete", kc.incomplete_count)
    if category_key == "pillar_canonical":
        pc = audit_obj.pillar_canonical
        nc = sum(pc.non_canonical_pillars.values()) if pc.non_canonical_pillars else 0
        if nc == 0:
            return ("✅", "all 4 canonical pillars", 0)
        return ("⚠️", f"{nc} rows non-canonical", nc)
    if category_key == "weight_normalization":
        wn = audit_obj.weight_normalization
        if wn.not_normalized_count == 0:
            return ("✅", "all sums = 1.0", 0)
        return ("⚠️", f"{wn.not_normalized_count} not normalized", wn.not_normalized_count)
    if category_key == "library_alignment":
        la = audit_obj.library_alignment
        if la.alignment_pct >= 100.0:
            return ("✅", f"100% aligned", 0)
        return ("⚠️", f"{la.alignment_pct}% aligned", len(la.bsc_kpis_not_in_library))
    if category_key == "cascade_linkage":
        cl = audit_obj.cascade_linkage
        missing = len(cl.cascaded_targets_not_in_bsc)
        if missing == 0:
            return ("✅", "all cascade ↔ BSC linked", 0)
        return ("🔴", f"{missing} cascade missing from BSC", missing)
    if category_key == "duplicate_rows":
        dr = audit_obj.duplicate_rows
        if dr.duplicate_count == 0:
            return ("✅", "0 duplicates", 0)
        return ("🔴", f"{dr.duplicate_count} (staff,KPI) duplicates", dr.duplicate_count)
    return ("❓", "unknown", 0)


def _render_category_details(audit_obj: Any, category_key: str) -> None:
    """Render the details panel for one category."""
    if category_key == "staff_coverage":
        sc = audit_obj.staff_coverage
        st.write(f"**Register:** {sc.register_count} staff")
        st.write(f"**BSC:** {sc.bsc_unique_staff} unique")
        st.write(f"**Coverage:** {sc.coverage_pct}%")
        if sc.in_register_not_in_bsc:
            st.error(f"**{len(sc.in_register_not_in_bsc)} staff missing from BSC:**")
            st.write(", ".join(sc.in_register_not_in_bsc[:20]))
        if sc.in_bsc_not_in_register:
            st.warning(f"**{len(sc.in_bsc_not_in_register)} ghost entries (in BSC, not in register):**")
            st.write(", ".join(sc.in_bsc_not_in_register[:20]))

    elif category_key == "kpi_completeness":
        kc = audit_obj.kpi_completeness
        st.write(f"**Total staff:** {kc.total_staff}")
        st.write(f"**Avg KPIs/staff:** {kc.avg_kpis_per_staff}")
        st.write(f"**Range:** {kc.min_kpis} – {kc.max_kpis}")
        if kc.incomplete_entries:
            import pandas as pd
            rows = [
                {"Staff": e.staff_name, "Role": e.role,
                 "Current": e.kpi_count, "Threshold": e.threshold,
                 "Pillars": e.pillars_covered}
                for e in kc.incomplete_entries[:30]
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True,
                        hide_index=True)

    elif category_key == "pillar_canonical":
        pc = audit_obj.pillar_canonical
        st.write(f"**Canonical pillars:** {', '.join(pc.canonical_pillars)}")
        st.write(f"**Pillars in BSC:** {', '.join(pc.pillars_in_bsc)}")
        if pc.non_canonical_pillars:
            st.warning(f"**Non-canonical pillars used:**")
            for p, c in pc.non_canonical_pillars.items():
                st.write(f"  • '{p}' — {c} rows")
            if pc.affected_kpis:
                st.write("**Affected KPIs (sample):**")
                st.write(", ".join(list(pc.affected_kpis.keys())[:10]))

    elif category_key == "weight_normalization":
        wn = audit_obj.weight_normalization
        c1, c2, c3 = st.columns(3)
        c1.metric("Total staff", wn.total_staff)
        c2.metric("Normalized", wn.normalized_count)
        c3.metric("Not normalized", wn.not_normalized_count)
        if wn.not_normalized_count > 0:
            st.write(f"**Weight sum range:** {wn.min_weight_sum} – {wn.max_weight_sum}")
            st.write(f"**Avg weight sum:** {wn.avg_weight_sum}")
            if wn.not_normalized_samples:
                st.write("**Sample non-normalized staff:**")
                for staff, ws in wn.not_normalized_samples[:10]:
                    st.write(f"  • {staff}: sum = {ws}")

    elif category_key == "library_alignment":
        la = audit_obj.library_alignment
        c1, c2, c3 = st.columns(3)
        c1.metric("BSC unique KPIs", la.bsc_unique_kpis)
        c2.metric("Library universe", la.library_kpi_count)
        c3.metric("Alignment %", f"{la.alignment_pct}%")
        if la.bsc_kpis_not_in_library:
            st.warning(f"**{len(la.bsc_kpis_not_in_library)} BSC KPIs not in library:**")
            st.write(", ".join(la.bsc_kpis_not_in_library[:15]))

    elif category_key == "cascade_linkage":
        cl = audit_obj.cascade_linkage
        c1, c2 = st.columns(2)
        c1.metric("Cascade staff", cl.cascaded_staff_count)
        c2.metric("BSC staff (by code)", cl.bsc_staff_count)
        if cl.cascaded_targets_not_in_bsc:
            st.error(f"**Cascade staff missing from BSC by code:**")
            st.write(", ".join(cl.cascaded_targets_not_in_bsc[:20]))

    elif category_key == "duplicate_rows":
        dr = audit_obj.duplicate_rows
        st.write(f"**Total BSC rows:** {dr.total_bsc_rows}")
        st.write(f"**Duplicate (staff,KPI) pairs:** {dr.duplicate_count}")
        if dr.duplicate_pairs:
            for staff, kpi, cnt in dr.duplicate_pairs[:10]:
                st.write(f"  • {staff} × {kpi} → {cnt} rows")


def _render_repair_button(category_key: str, can_run_repairs: bool) -> None:
    """Render the 'Run fix' button + dry-run / confirm flow for a category."""
    cfg = CATEGORY_REPAIRS.get(category_key, {})
    repair_path = cfg.get("repair")
    if not repair_path:
        st.info("No automated repair for this category. Manual investigation required.")
        return

    if not can_run_repairs:
        st.caption("ℹ️ Admin role required to run repairs.")
        return

    repair_fn = _resolve_repair_fn(repair_path)
    if repair_fn is None:
        st.warning(f"Could not load repair engine: {repair_path}")
        return

    # Dry-run preview
    dry_key = f"dry_{category_key}"
    if st.button(f"🔍 Preview fix (dry-run)", key=f"btn_dry_{category_key}"):
        try:
            result = repair_fn(dry_run=True)
            st.session_state[dry_key] = result.to_dict() if hasattr(result, "to_dict") else dict(result.__dict__ if hasattr(result, "__dict__") else result)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Dry-run failed: {exc}")
            return

    if dry_key in st.session_state:
        st.code(repr(st.session_state[dry_key]), language="python")
        if st.button(f"⚠️ Apply fix (live, writes to disk)",
                     key=f"btn_run_{category_key}", type="primary"):
            try:
                result = repair_fn(dry_run=False)
                st.success(f"✓ Fix applied")
                st.code(repr(result.to_dict() if hasattr(result, "to_dict") else result),
                        language="python")
                # Optional cleanup follow-up
                cleanup_path = cfg.get("cleanup")
                if cleanup_path:
                    cleanup_fn = _resolve_repair_fn(cleanup_path)
                    if cleanup_fn:
                        cleanup_result = cleanup_fn(dry_run=False)
                        st.info(f"Cleanup ran: "
                                f"{cleanup_result.to_dict() if hasattr(cleanup_result, 'to_dict') else cleanup_result}")
                # Clear cached dry-run
                del st.session_state[dry_key]
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Live fix failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# Public API — Main render function
# ════════════════════════════════════════════════════════════════════

def render_bsc_health_dashboard(
    can_run_repairs: bool = False,
) -> Optional[Dict[str, Any]]:
    """Render the full BSC health dashboard.

    Args:
        can_run_repairs: if True, shows interactive 'Run fix' buttons.
            Usually gated by admin role.

    Returns the audit dict that was rendered (for tests / chained widgets).
    """
    st.markdown("### 🩺 BSC Health Dashboard")
    st.caption(
        "Live audit from the BSC Rescue engines (v10.424–v10.429). "
        "Every category is queryable via `/api/v1/bsc-audit/*` for React."
    )

    # Run audit
    try:
        from utils.bsc_audit_engine import bsc_full_audit
        audit = bsc_full_audit()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to load BSC audit: {exc}")
        return None

    # Top: overall health + severity counts
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    c1.metric("Overall BSC Health", f"{audit.overall_health_pct}%",
              delta=None,
              help="Percent of 7 audit categories passing")
    c2.metric("🔴 Critical", audit.issues_by_severity.get("critical", 0))
    c3.metric("⚠️ Warning", audit.issues_by_severity.get("warning", 0))
    c4.metric("ℹ️ Info", audit.issues_by_severity.get("info", 0))

    if audit.overall_health_pct >= 100:
        st.success("🎉 All 7 BSC audit categories are clean. The body is functioning as one.")
    elif audit.issues_by_severity.get("critical", 0) > 0:
        st.error(f"Critical issues present — review highlighted categories below.")
    else:
        st.warning(f"Non-critical issues present — review highlighted categories below.")

    st.divider()
    st.markdown("**Per-category status:**")

    # Per category row
    for cat_key, cfg in CATEGORY_REPAIRS.items():
        emoji, status, count = _category_status(audit, cat_key)
        with st.expander(
            f"{emoji} {cfg['icon']} {cfg['label']} — {status}",
            expanded=(emoji != "✅"),
        ):
            st.caption(cfg["help"])
            _render_category_details(audit, cat_key)

            # Repair button (only if category has issue)
            if count > 0:
                st.divider()
                _render_repair_button(cat_key, can_run_repairs=can_run_repairs)

    # Footer
    st.divider()
    st.caption(
        f"Audit generated at {audit.timestamp}. "
        f"Engine source: `utils/bsc_audit_engine.py`. "
        f"For headless access: `python scripts/audit_bsc.py --json`."
    )

    return audit.to_dict()


def render_bsc_admin_actions() -> None:
    """Render an admin action panel — re-run all migrations, etc.

    Lighter than the main dashboard; useful as a sidebar widget.
    """
    st.markdown("##### BSC Admin Actions")
    if st.button("🔄 Re-audit BSC now", key="btn_reaudit"):
        # Just rerun — the dashboard will re-fetch on next render
        st.rerun()
    st.caption("Or use the CLI: `python scripts/audit_bsc.py`")


# ════════════════════════════════════════════════════════════════════
# v10.431 — Library validation panel
# ════════════════════════════════════════════════════════════════════

def render_library_validation_panel(can_run_repairs: bool = False) -> None:
    """Render the KPI library validation panel.

    Surfaces errors/warnings from admin_validation_engine.validate_full_library.
    Provides "Apply legacy aliases" button to clean up role_kpis SNAKE_CASE
    references when admin role is granted.
    """
    st.markdown("### 🔍 KPI Library Validation")
    st.caption(
        "Live snapshot from `admin_validation_engine.validate_full_library`. "
        "Catches duplicate IDs, non-canonical pillars, malformed pillar "
        "weights, and orphaned role_kpis references before they corrupt the BSC."
    )

    try:
        from utils.admin_validation_engine import (
            validate_full_library, apply_legacy_code_aliases,
            LEGACY_CODE_ALIAS_MAP,
        )
        result = validate_full_library()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to run validation: {exc}")
        return

    # Top: badge state
    c1, c2, c3 = st.columns(3)
    if result.valid:
        c1.success(f"✅ Library validates")
    else:
        c1.error(f"❌ {len(result.errors)} error(s)")
    c2.metric("Warnings", len(result.warnings))
    c3.metric("Info", len(result.info))

    # Errors (always show all)
    if result.errors:
        st.markdown("#### ❌ Errors (must fix)")
        for e in result.errors:
            st.error(f"**{e.field}** — {e.message}")

    # Warnings (collapse)
    if result.warnings:
        with st.expander(f"⚠️ Warnings ({len(result.warnings)})",
                         expanded=len(result.warnings) <= 5):
            for w in result.warnings:
                st.warning(f"**{w.field}** — {w.message}")

    # Info (collapsed)
    if result.info:
        with st.expander(f"ℹ️ Info ({len(result.info)})", expanded=False):
            for i in result.info:
                st.info(f"**{i.field}** — {i.message}")

    # Legacy alias action (admin only)
    if can_run_repairs:
        st.divider()
        st.markdown("##### 🔧 Library cleanup actions")
        st.caption(
            "If role_kpis warnings show unresolved SNAKE_CASE codes "
            "(e.g., LOAN_DISB, FEES_COMM), the legacy-alias migration "
            "adds them as `aliases` on canonical library entries."
        )
        dry_key = "dry_legacy_aliases"
        if st.button("🔍 Preview legacy-alias migration",
                     key="btn_dry_aliases"):
            try:
                dry_result = apply_legacy_code_aliases(dry_run=True)
                st.session_state[dry_key] = dry_result.to_dict()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Dry-run failed: {exc}")
                return

        if dry_key in st.session_state:
            preview = st.session_state[dry_key]
            st.write(f"**Would add:** {preview['aliases_added']} aliases "
                     f"across {preview['library_entries_updated']} library entries")
            if preview.get("skipped_unresolved"):
                st.warning(f"Cannot resolve (no library match): "
                          f"{preview['skipped_unresolved']}")
            if preview["aliases_added"] > 0:
                if st.button("⚠️ Apply legacy aliases (writes kpi_library.json)",
                             key="btn_apply_aliases", type="primary"):
                    try:
                        live = apply_legacy_code_aliases(dry_run=False)
                        st.success(
                            f"✓ Added {live.aliases_added} aliases. "
                            f"Backup at `{live.backup_path}`."
                        )
                        del st.session_state[dry_key]
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Migration failed: {exc}")
            else:
                st.info("All legacy aliases already applied — nothing to do.")
    else:
        st.caption("ℹ️ Admin role required to run library cleanup migrations.")


# ════════════════════════════════════════════════════════════════════
# v10.432 — Cascade-BSC 360° harmony panel
# ════════════════════════════════════════════════════════════════════

def render_cascade_360_panel() -> None:
    """Render the 360° cascade↔BSC harmony audit dashboard.

    Read-only diagnostic surfacing the 5-stage rollup from
    cascade_bsc_360_engine.cascade_bsc_360_audit.
    """
    st.markdown("### 🔄 Cascade ↔ BSC 360° Harmony")
    st.caption(
        "End-to-end deep review: bank targets → MD BSC → cascade allocations "
        "→ subordinate BSC → actuals → score calculations. Five stages."
    )

    try:
        from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
        audit = cascade_bsc_360_audit()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to run 360° audit: {exc}")
        return

    # Top: harmony percentage + severity
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    c1.metric(
        "Overall harmony", f"{audit.overall_harmony_pct}%",
        delta=f"{audit.stages_passing}/{audit.total_stages} stages",
    )
    c2.metric("🔴 Critical", audit.issues_by_severity.get("critical", 0))
    c3.metric("⚠️ Warning", audit.issues_by_severity.get("warning", 0))
    c4.metric("Stages", f"{audit.stages_passing}/{audit.total_stages}")

    if audit.overall_harmony_pct >= 100:
        st.success("✅ Full harmony — cascade and BSC are 100% aligned.")
    else:
        st.warning(
            f"Partial harmony at {audit.overall_harmony_pct}%. "
            f"Detailed findings below."
        )

    # ── Stage 1: Bank → MD ────────────────────────────
    s1 = audit.bank_to_md
    pass_s1 = (
        len(s1.md_kpis_missing_bank_target) == 0
        and len(s1.target_mismatches) == 0
        and s1.md_bsc_kpi_count > 0
    )
    with st.expander(
        f"{'✅' if pass_s1 else '⚠️'} **1. Bank Targets → MD BSC** — "
        f"{s1.md_kpis_with_bank_target}/{s1.md_bsc_kpi_count} KPIs matched, "
        f"{len(s1.target_mismatches)} value mismatches",
        expanded=not pass_s1,
    ):
        st.write(f"**Bank targets configured:** {s1.bank_target_count}")
        st.write(f"**MD's BSC KPIs:** {s1.md_bsc_kpi_count}")
        st.write(f"**MD KPIs with bank target:** {s1.md_kpis_with_bank_target}")
        if s1.md_kpis_missing_bank_target:
            st.warning(
                f"**{len(s1.md_kpis_missing_bank_target)} MD KPIs without bank target:** "
                f"{s1.md_kpis_missing_bank_target}"
            )
        if s1.target_mismatches:
            st.error(f"**{len(s1.target_mismatches)} target value mismatches:**")
            import pandas as pd
            st.dataframe(pd.DataFrame(s1.target_mismatches),
                        use_container_width=True, hide_index=True)

    # ── Stage 2: Cascade integrity ────────────────────
    s2 = audit.cascade_integrity
    pass_s2 = s2.sum_mismatch_count == 0 and len(s2.orphan_allocations) == 0
    with st.expander(
        f"{'✅' if pass_s2 else '🔴'} **2. Cascade Integrity** — "
        f"{s2.valid_entries}/{s2.total_cascade_entries} valid sums, "
        f"{s2.sum_mismatch_count} mismatches, "
        f"{len(s2.orphan_allocations)} orphans",
        expanded=not pass_s2,
    ):
        st.write(f"**Total cascade entries:** {s2.total_cascade_entries}")
        st.write(f"**Valid (sum == total_target):** {s2.valid_entries}")
        st.write(f"**Zero-target entries (skipped):** {s2.zero_target_count}")
        if s2.sum_mismatches:
            st.error(
                f"**{s2.sum_mismatch_count} sum mismatches — allocations don't sum to total_target:**"
            )
            import pandas as pd
            st.dataframe(pd.DataFrame(s2.sum_mismatches),
                        use_container_width=True, hide_index=True)
        if s2.orphan_allocations:
            st.error(
                f"**{len(s2.orphan_allocations)} orphan allocations — child not in register:**"
            )
            import pandas as pd
            st.dataframe(pd.DataFrame(s2.orphan_allocations),
                        use_container_width=True, hide_index=True)

    # ── Stage 3: Cascade → BSC targets ────────────────
    s3 = audit.cascade_to_bsc
    pass_s3 = (
        len(s3.allocations_missing_bsc_row) == 0
        and len(s3.target_value_mismatches) == 0
        and s3.coverage_pct >= 99.0
    )
    with st.expander(
        f"{'✅' if pass_s3 else '🔴'} **3. Cascade Allocations → BSC Rows** — "
        f"{s3.coverage_pct}% coverage, "
        f"{len(s3.target_value_mismatches)} value mismatches",
        expanded=not pass_s3,
    ):
        st.write(f"**Total cascade allocations:** {s3.total_allocations}")
        st.write(f"**Allocations with BSC match:** {s3.allocations_with_bsc_match}")
        st.write(f"**Coverage:** {s3.coverage_pct}%")
        if s3.allocations_missing_bsc_row:
            st.error(
                f"**{len(s3.allocations_missing_bsc_row)}+ allocations missing BSC rows** "
                f"(sample of first 50):"
            )
            import pandas as pd
            st.dataframe(
                pd.DataFrame(s3.allocations_missing_bsc_row),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                "These represent staff who are being cascaded targets they don't track in their BSC. "
                "v10.433 will close this gap."
            )
        if s3.target_value_mismatches:
            st.warning(
                f"**{len(s3.target_value_mismatches)} target value mismatches** "
                f"(cascade amount ≠ BSC target):"
            )
            import pandas as pd
            st.dataframe(
                pd.DataFrame(s3.target_value_mismatches),
                use_container_width=True, hide_index=True,
            )

    # ── Stage 4: BSC actuals coverage ─────────────────
    s4 = audit.bsc_actuals
    pass_s4 = s4.target_coverage_pct >= 100.0 and s4.actuals_coverage_pct >= 99.0
    with st.expander(
        f"{'✅' if pass_s4 else '⚠️'} **4. BSC Actuals Coverage** — "
        f"{s4.actuals_coverage_pct}% rows have all actuals",
        expanded=not pass_s4,
    ):
        c1_, c2_, c3_, c4_ = st.columns(4)
        c1_.metric("Total rows", s4.total_bsc_rows)
        c2_.metric("Have targets", s4.rows_with_annual_target)
        c3_.metric("Have YTD", s4.rows_with_ytd_actual)
        c4_.metric("Have annual", s4.rows_with_annual_actual)
        if s4.rows_missing_actuals > 0:
            st.warning(f"{s4.rows_missing_actuals} rows missing one or more actuals")
        if s4.rows_missing_target > 0:
            st.error(f"{s4.rows_missing_target} rows missing Annual Target")

    # ── Stage 5: Score calculation ────────────────────
    s5 = audit.score_calculation
    pass_s5 = (
        s5.staff_with_nan_score == 0
        and s5.staff_with_computable_score == s5.total_staff
        and s5.total_staff > 0
    )
    with st.expander(
        f"{'✅' if pass_s5 else '🔴'} **5. End-to-end Score Calculation** — "
        f"{s5.staff_with_computable_score}/{s5.total_staff} staff scoreable, "
        f"avg {s5.overall_avg_score}%",
        expanded=not pass_s5,
    ):
        c1_, c2_, c3_, c4_ = st.columns(4)
        c1_.metric("Total staff", s5.total_staff)
        c2_.metric("Scoreable", s5.staff_with_computable_score)
        c3_.metric("NaN scores", s5.staff_with_nan_score)
        c4_.metric("Zero target", s5.staff_with_zero_target)
        st.write(
            f"**Avg score:** {s5.overall_avg_score}%  · "
            f"**Range:** {s5.score_range[0]}% – {s5.score_range[1]}%"
        )
        if s5.failing_staff_samples:
            st.warning("**Sample failing staff:**")
            for s in s5.failing_staff_samples:
                st.write(f"  • {s.get('staff_name')}: {s.get('reason')}")

    st.divider()
    st.caption(
        f"Audit generated at {audit.timestamp}. "
        f"For headless access: `GET /api/v1/cascade-360/audit`."
    )


# ════════════════════════════════════════════════════════════════════
# v10.433 — Cascade-BSC harmonization panel
# ════════════════════════════════════════════════════════════════════

def render_harmonize_panel(can_run_repairs: bool = False) -> None:
    """Render the 5-stage cascade-BSC harmonization migration panel.

    Stages A→E close the gaps surfaced by the 360 audit.
    All stages support dry_run; live runs gated behind admin role.
    """
    st.markdown("### 🛠️ Cascade-BSC Harmonization (v10.433)")
    st.caption(
        "Closes harmony gaps surfaced by the 360 audit. Stage A: docs "
        "Staff Productivity scale. Stage B: narrows cascade to "
        "role_kpis fit. Stage C: supplements BSC with cascade allocations. "
        "Stage D: renormalizes weights. Stage E: aligns BSC targets to "
        "cascade. All idempotent."
    )

    if not can_run_repairs:
        st.caption("ℹ️ Admin role required to run harmonization migrations.")
        return

    try:
        from utils.cascade_bsc_harmonize_engine import harmonize_all
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to load harmonize engine: {exc}")
        return

    dry_key = "dry_harmonize_all"
    if st.button("🔍 Preview harmonization (dry-run)",
                 key="btn_dry_harmonize"):
        try:
            preview = harmonize_all(dry_run=True)
            st.session_state[dry_key] = preview.to_dict()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Dry-run failed: {exc}")
            return

    if dry_key in st.session_state:
        p = st.session_state[dry_key]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Stage A", "no-op" if not p["stage_a"]["needed_fix"]
                  else "fix")
        c2.metric("Stage B entries pruned",
                  p["stage_b"]["cascade_entries_pruned"])
        c3.metric("Stage C rows added", p["stage_c"]["bsc_rows_added"])
        c4.metric("Stage D staff renorm", p["stage_d"]["staff_renormalized"])
        c5.metric("Stage E aligned", p["stage_e"]["rows_aligned"])

        total_changes = (
            p["stage_b"]["allocations_dropped"]
            + p["stage_c"]["bsc_rows_added"]
            + p["stage_d"]["rows_modified"]
            + p["stage_e"]["rows_aligned"]
        )
        if total_changes > 0:
            st.warning(
                f"This migration will make ~{total_changes:,} data changes "
                f"across cascade and BSC. Backups are auto-created in "
                f"`data/_v10433_backups/`."
            )
            if st.button(
                "⚠️ Apply harmonization (writes cascade + BSC)",
                key="btn_apply_harmonize", type="primary",
            ):
                try:
                    live = harmonize_all(dry_run=False)
                    st.success(
                        f"✅ Harmonized. "
                        f"Stage B pruned {live.stage_b.cascade_entries_pruned}, "
                        f"C added {live.stage_c.bsc_rows_added}, "
                        f"D renormalized {live.stage_d.staff_renormalized}, "
                        f"E aligned {live.stage_e.rows_aligned}."
                    )
                    del st.session_state[dry_key]
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Migration failed: {exc}")
        else:
            st.info("Already harmonized — re-running would change nothing.")


# ════════════════════════════════════════════════════════════════════
# v10.434 — Staff onboarding fit-in panel
# ════════════════════════════════════════════════════════════════════

def render_onboarding_fit_panel() -> None:
    """Render the bank-wide staff onboarding fit-in audit.

    Read-only diagnostic: surfaces how well every existing staff fits
    the canonical pattern (role_kpis → BSC → weights → score). Surfaces
    gaps that admins should fix in role_kpis or BSC.
    """
    st.markdown("### 👥 Staff Onboarding Fit-In Audit (v10.434)")
    st.caption(
        "Verifies every staff's full canonical fit: register → role_kpis "
        "→ BSC rows → weight sum 1.0 → all 4 pillars → score computable. "
        "Surfaces gaps that the next new-hire would inherit."
    )

    try:
        from utils.staff_onboarding_engine import audit_all_staff_completeness
        audit = audit_all_staff_completeness()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to run fit-in audit: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    pct_fully = (
        audit.fully_fit / audit.total_staff * 100
        if audit.total_staff else 0.0
    )
    c1.metric("Fully fit", f"{audit.fully_fit}/{audit.total_staff}",
              delta=f"{pct_fully:.1f}%")
    c2.metric("Partial fit", audit.partial_fit)
    c3.metric("Failing", audit.failing)
    c4.metric("Avg role_kpi coverage", f"{audit.avg_role_kpi_coverage_pct}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Weight sum = 1.0",
              f"{audit.weight_sum_invariant_pct}%")
    c6.metric("Score computable", f"{audit.score_computable_pct}%")
    c7.metric("All 4 pillars", f"{audit.pillar_coverage_pct}%")
    c8.metric("Failing samples",
              len(audit.failing_samples))

    if pct_fully >= 95:
        st.success(f"✅ {pct_fully:.1f}% fully fit — onboarding is solid.")
    elif pct_fully >= 80:
        st.info(
            f"ℹ️ {pct_fully:.1f}% fully fit. {audit.partial_fit} staff "
            f"have minor gaps that admin should address in role_kpis."
        )
    else:
        st.warning(
            f"⚠️ Only {pct_fully:.1f}% fully fit. "
            f"{audit.failing} staff have significant gaps."
        )

    if audit.failing_samples:
        with st.expander(
            f"🔴 Failing staff samples ({len(audit.failing_samples)})",
            expanded=False,
        ):
            for s in audit.failing_samples:
                st.error(
                    f"**{s.get('code')} {s.get('name')}** ({s.get('role')}): "
                    f"{', '.join(s.get('issues', []))}"
                )

    # Onboarding simulator (try a hypothetical new staff)
    st.divider()
    st.markdown("#### 🧪 Simulate New Staff Onboarding")
    st.caption(
        "Pick a role; see what BSC the new staff would get. No data writes."
    )

    try:
        import json as _json
        from utils.staff_onboarding_engine import simulate_onboarding
        lib_path = Path(__file__).parent.parent / "data" / "kpi_library.json"
        lib = _json.loads(lib_path.read_text(encoding="utf-8"))
        roles = sorted(lib.get("role_kpis", {}).keys())
    except Exception:  # noqa: BLE001
        roles = []

    if roles:
        chosen_role = st.selectbox(
            "Role for hypothetical new staff",
            roles, key="onboard_sim_role",
        )
        chosen_unit = st.text_input(
            "Unit / Branch",
            value="Test Unit", key="onboard_sim_unit",
        )
        if st.button("Simulate onboarding", key="btn_onboard_sim"):
            try:
                result = simulate_onboarding({
                    "Staff Code": "TST_SIM_001",
                    "Staff Name": "Hypothetical New Hire",
                    "Role": chosen_role,
                    "Unit": chosen_unit,
                })
                if not result.valid:
                    st.error(f"Validation failed: "
                            f"{[e.to_dict() for e in result.validation.errors]}")
                else:
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("BSC rows added", result.bsc_rows_added)
                    s2.metric("Weight sum", f"{result.weight_sum_post:.2f}")
                    s3.metric("Cascade allocations",
                              result.cascade_allocations_received)
                    s4.metric("Score", "✓" if result.score_computable else "✗")
                    st.write(f"**Pillar coverage:** {result.pillar_coverage}")
                    if result.role_kpis_resolved:
                        with st.expander("KPIs that would be assigned"):
                            for k in result.role_kpis_resolved:
                                st.write(f"  • {k}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Simulation failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# v10.435 — Staff exit risk panel
# ════════════════════════════════════════════════════════════════════

def render_exit_risk_panel() -> None:
    """Render the bank-wide staff exit risk audit.

    Read-only diagnostic: surfaces who carries key-person risk, which
    KPIs have sole owners, and what redistribution strategies look
    plausible. Used by HR + admin for succession planning.
    """
    st.markdown("### 🚪 Staff Exit & Target Gap Risk (v10.435)")
    st.caption(
        "Surfaces who carries 'key-person' risk - whose exit would create "
        "target gaps. Risk score 0-100 combines outgoing cascade size, "
        "value flow, role uniqueness, pillar criticality, and incoming "
        "reliance."
    )

    try:
        from utils.staff_exit_engine import audit_all_exit_risks
        audit = audit_all_exit_risks()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to run exit risk audit: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Critical (75+)", audit.critical_risk_count)
    c2.metric("High (50-74)", audit.high_risk_count)
    c3.metric("Medium (25-49)", audit.medium_risk_count)
    c4.metric("Low (<25)", audit.low_risk_count)

    c5, c6 = st.columns(2)
    c5.metric("Total staff", audit.total_staff)
    c6.metric("Avg risk score", f"{audit.avg_risk_score:.1f}")

    if audit.critical_risk_count == 0:
        st.success(
            f"✅ No critical-risk staff. "
            f"{audit.high_risk_count} high-risk warrant succession plans."
        )
    else:
        st.error(
            f"🔴 {audit.critical_risk_count} critical-risk staff need "
            f"immediate succession planning."
        )

    # Top risk drivers globally
    if audit.top_risk_drivers_global:
        with st.expander("📊 Risk drivers across the bank", expanded=False):
            for driver, count in audit.top_risk_drivers_global.items():
                st.write(f"  • **{driver}**: {count} staff")

    # Critical + high samples
    if audit.critical_staff:
        with st.expander(
            f"🔴 Critical-risk staff ({len(audit.critical_staff)})",
            expanded=True,
        ):
            import pandas as pd
            st.dataframe(
                pd.DataFrame(audit.critical_staff),
                use_container_width=True, hide_index=True,
            )

    if audit.high_staff:
        with st.expander(
            f"⚠️ High-risk staff (sample of {len(audit.high_staff)})",
            expanded=False,
        ):
            import pandas as pd
            st.dataframe(
                pd.DataFrame(audit.high_staff[:20]),
                use_container_width=True, hide_index=True,
            )

    # Exit simulator
    st.divider()
    st.markdown("#### 🧪 Simulate Staff Exit")
    st.caption(
        "Enter a staff code; see their exit impact + redistribution options. "
        "No data writes."
    )

    sim_code = st.text_input(
        "Staff Code to simulate exit",
        value="300001", key="exit_sim_code",
        help="e.g., 300001 for MD",
    )
    if st.button("Run exit simulation", key="btn_exit_sim"):
        try:
            from utils.staff_exit_engine import simulate_exit
            sim = simulate_exit(sim_code)
            r = sim.risk
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Risk score", f"{r.risk_score:.0f}",
                      delta=r.risk_band.capitalize())
            s2.metric("Outgoing cascade entries", r.outgoing_cascade_count)
            s3.metric("Role peers", r.role_peer_count)
            s4.metric("Incoming reliance", r.incoming_reliance_count)
            st.write(f"**Staff:** {sim.staff_name} ({r.role})")
            st.write(f"**Recommended strategy:** {sim.recommended_strategy}")
            if r.risk_drivers:
                st.write(f"**Drivers:** {', '.join(r.risk_drivers)}")
            if sim.redistribution_options:
                with st.expander("Redistribution options", expanded=True):
                    import pandas as pd
                    st.dataframe(pd.DataFrame([
                        {
                            "strategy": opt.strategy,
                            "valid": opt.valid,
                            "receivers": len(opt.receivers),
                            "feasibility_%": opt.feasibility_pct,
                            "unassigned_value": opt.unassigned_value,
                            "warnings": "; ".join(opt.warnings) if opt.warnings else "",
                        }
                        for opt in sim.redistribution_options
                    ]), use_container_width=True, hide_index=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Simulation failed: {exc}")


# ════════════════════════════════════════════════════════════════════
# v10.436 — HR section audit panel
# ════════════════════════════════════════════════════════════════════

def render_hr_section_audit_panel() -> None:
    """Render the People (HR) section health audit.

    Diagnostic across 6 dimensions: module placement, page completeness,
    engine wiring, REACT readiness, API coverage, data backing. Surfaces
    rescue priorities for the HR section.
    """
    st.markdown("### 🏥 People (HR) Section Health Audit (v10.436)")
    st.caption(
        "Diagnoses the HR section across 6 dimensions: placement, "
        "completeness, engine wiring, REACT/API/data readiness. "
        "This body needs rescue - audit shows priorities."
    )

    try:
        from utils.hr_section_audit_engine import hr_full_audit
        audit = hr_full_audit()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to run HR audit: {exc}")
        return

    # Top: health score
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("HR Health", f"{audit.hr_health_pct}%",
              delta=f"Critical: {audit.severity_counts.get('critical', 0)}")
    c2.metric("Critical issues", audit.severity_counts.get("critical", 0))
    c3.metric("High issues", audit.severity_counts.get("high", 0))
    c4.metric("Rescue priorities", len(audit.rescue_priorities))

    if audit.hr_health_pct >= 80:
        st.success(f"✅ HR section healthy at {audit.hr_health_pct}%")
    elif audit.hr_health_pct >= 60:
        st.info(f"ℹ️ HR at {audit.hr_health_pct}% - improvements needed")
    else:
        st.error(f"🚨 HR at {audit.hr_health_pct}% - rescue required")

    # ── 1. Module placement
    mp = audit.module_placement
    with st.expander(
        f"🗺️ 1. Module Placement — "
        f"{len(mp.correctly_placed)} correct, "
        f"{len(mp.misplaced_in_hr)} misplaced, "
        f"{len(mp.should_be_in_hr_but_arent)} missing",
        expanded=len(mp.misplaced_in_hr) > 0,
    ):
        st.write(f"**Currently in HR:** {mp.pages_currently_in_hr}")
        st.write(f"**Correctly placed ({len(mp.correctly_placed)}):** {mp.correctly_placed}")
        if mp.misplaced_in_hr:
            st.warning(f"**Misplaced ({len(mp.misplaced_in_hr)}):**")
            import pandas as pd
            st.dataframe(pd.DataFrame(mp.misplaced_in_hr),
                        use_container_width=True, hide_index=True)
        if mp.should_be_in_hr_but_arent:
            st.info(f"**Should be in HR ({len(mp.should_be_in_hr_but_arent)}):**")
            for s in mp.should_be_in_hr_but_arent:
                st.write(f"  • {s}")

    # ── 2. Page completeness
    pc = audit.page_completeness
    with st.expander(
        f"📄 2. Page Completeness — "
        f"{pc.substantial_count} substantial, "
        f"{pc.stub_count} stubs",
        expanded=pc.stub_count > 0,
    ):
        st.write(f"**Avg lines/page:** {pc.avg_lines_per_page}")
        import pandas as pd
        rows = [{
            "file": p.file, "title": p.title,
            "lines": p.line_count, "tabs": p.tab_count,
            "engine_imports": len(p.engine_imports),
            "status": "STUB" if p.is_stub else "OK",
        } for p in pc.pages]
        st.dataframe(pd.DataFrame(rows),
                    use_container_width=True, hide_index=True)

    # ── 3. Engine wiring
    ew = audit.engine_wiring
    with st.expander(
        f"🔌 3. Engine Wiring — "
        f"{len(ew.wired_engines)}/{ew.total_hr_engines} wired "
        f"({ew.wiring_coverage_pct}%)",
        expanded=ew.wiring_coverage_pct < 100,
    ):
        st.write(f"**Wired ({len(ew.wired_engines)}):**")
        for w in ew.wired_engines:
            st.write(f"  ✓ {w['engine']:30} ({w['std']}) → {w['in_pages']}")
        if ew.unwired_engines:
            st.error(f"**Unwired ({len(ew.unwired_engines)}):**")
            import pandas as pd
            st.dataframe(pd.DataFrame(ew.unwired_engines),
                        use_container_width=True, hide_index=True)

    # ── 4. REACT readiness
    rr = audit.react_readiness
    with st.expander(
        f"⚛️ 4. REACT Readiness — "
        f"{rr.react_ready_count}/{rr.engines_checked} ready "
        f"({rr.react_readiness_pct}%)",
        expanded=rr.react_readiness_pct < 100,
    ):
        if rr.engines_with_streamlit:
            st.error(f"With streamlit imports: {rr.engines_with_streamlit}")
        if rr.engines_without_dataclasses:
            st.warning(f"Without @dataclass: {rr.engines_without_dataclasses}")
        if rr.react_readiness_pct == 100.0:
            st.success("All HR engines are React-ready ✓")

    # ── 5. API coverage
    api = audit.api_coverage
    with st.expander(
        f"🌐 5. API Coverage — "
        f"{len(api.engines_with_api)}/{api.total_engines} "
        f"({api.api_coverage_pct}%)",
        expanded=api.api_coverage_pct < 100,
    ):
        st.write(f"**With endpoints:** {api.engines_with_api}")
        if api.engines_without_api:
            st.error(f"**Missing endpoints ({len(api.engines_without_api)}):**")
            import pandas as pd
            st.dataframe(pd.DataFrame(api.engines_without_api),
                        use_container_width=True, hide_index=True)

    # ── 6. Data backing
    db = audit.data_backing
    with st.expander(
        f"💾 6. Data Backing — "
        f"PG: {db.pg_ready_count}, JSON: {db.json_only_count}, "
        f"Excel: {db.excel_dependent_count}",
        expanded=db.pg_ready_count == 0,
    ):
        import pandas as pd
        st.dataframe(pd.DataFrame(db.engines),
                    use_container_width=True, hide_index=True)

    # Rescue priorities
    st.divider()
    st.markdown("### 🛠️ Rescue Priorities")
    for i, p in enumerate(audit.rescue_priorities, 1):
        st.write(f"  **{i}.** {p}")
