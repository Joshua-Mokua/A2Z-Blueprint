"""pages/99_integration_cockpit.py — Integration Layer cockpit (v10.127, extended v10.132).

Operator-facing single-page surface of the Phase 1D Integration Layer
(closed at v10.126 with G143 STRICT-READY (high) at 99/131 = 75.6%).
This is the "connect standards to the live Streamlit app" piece flagged
in the focus areas — the integration layer's 5 API endpoints have been
stable since v10.115, and v10.127 finally surfaces them in the cockpit.

Tabs:
  1. Coverage          — G143 strict-preview tier, covered / total /
                         tier transitions (preview→high crossing at 75%)
  2. Rules             — full registry of 100 active rules with
                         pattern, source_table, staff_field, period_field
  3. Preview actuals   — pick a period, see compute_actuals_from_
                         operational_tables() output per rule + sample
                         per-staff numbers
  4. Resolution metrics — name+role resolver hit rates from the live
                         resolver caches
  5. Run period         — admin-only trigger for the full pipeline;
                         requires role-gating-allowed role per v10.126
                         hard-flip default

Per Rule 7, the page surfaces — it never auto-fixes, never silently
mutates state. The "Run period" button is explicit: dry_run defaults
ON; admins must uncheck to write.

Caches: rule registry + library cached for 5 minutes via
@st.cache_data(ttl=300). Compute previews are NOT cached because
period selection drives them.

This page consumes the integration layer's utility functions directly
(same pattern as other cockpit pages) rather than going through HTTP —
identical results, simpler stack.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from pages._access import require_access
from utils.core_audit import audit_log

# ───── Page setup ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Integration Cockpit",
    page_icon="🧮",
    layout="wide")

if not require_access("integration_cockpit", silent=True):
    require_access("admin")

ud = st.session_state.get("user_data", {}) or {}
username = ud.get("username", "anonymous")
audit_log(
    "integration_cockpit_view",
    username,
    f"username={username}")


# ───── Helpers ─────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent


@st.cache_data(ttl=300)
def _load_rule_registry() -> List[Dict[str, Any]]:
    """Load the 100 active aggregation rules from JSON. Cached 5 min."""
    path = REPO_ROOT / "data" / "aggregation_rules.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    rules = data.get("rules", [])
    return [r for r in rules if r.get("active", True)]


@st.cache_data(ttl=300)
def _load_kpi_library() -> List[Dict[str, Any]]:
    path = REPO_ROOT / "data" / "kpi_library.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return data.get("kpis", [])


@st.cache_data(ttl=300)
def _load_security_config() -> Dict[str, Any]:
    """Read _security block from integration_layer_config.json."""
    path = REPO_ROOT / "data" / "integration_layer_config.json"
    if not path.exists():
        return {"role_gating_enabled": True,
                "allowed_roles_for_write": ["admin", "integration"]}
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return {"role_gating_enabled": True,
                "allowed_roles_for_write": ["admin", "integration"]}
    sec = cfg.get("_security", {})
    return {
        "role_gating_enabled": bool(sec.get("role_gating_enabled", True)),
        "allowed_roles_for_write":
            sec.get("allowed_roles_for_write", ["admin", "integration"]),
    }


def _compute_g143_summary() -> Dict[str, Any]:
    """Run G143 audit gate and return its strict-preview block. Not
    cached — operators expect this to reflect the current state."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        # Import is here rather than module-level so the cockpit page
        # stays loadable even if scripts/audit.py has issues.
        import importlib
        import audit as audit_module
        importlib.reload(audit_module)
        result = audit_module.gate_kpi_source_has_aggregator()
        return result
    except Exception as exc:
        return {"passed": False, "summary": f"G143 unavailable: {exc}",
                "strict_preview": {"tag": "ERROR", "covered": 0,
                                   "total_operational": 0,
                                   "coverage_pct": 0.0}}
    finally:
        if str(REPO_ROOT / "scripts") in sys.path:
            sys.path.remove(str(REPO_ROOT / "scripts"))


def _tier_emoji(tag: str) -> str:
    return {
        "STRICT-READY (high)":     "🟢",
        "STRICT-READY (preview)":  "🟡",
        "BELOW STRICT THRESHOLD":  "🔴",
    }.get(tag, "⚪")


def _user_role() -> str:
    """Return the current logged-in user's role (or empty)."""
    return ud.get("role") or ""


def _can_write() -> bool:
    """Check if the current user is allowed to trigger writes per
    v10.126's hard-flip role-gating default."""
    sec = _load_security_config()
    if not sec.get("role_gating_enabled"):
        return True   # JWT-only auth; any logged-in user passes
    role = _user_role()
    return role in sec.get("allowed_roles_for_write", [])


# ───── Header ──────────────────────────────────────────────────────────

st.title("🧮 Integration Layer Cockpit")
st.caption(
    "v10.127 — operator surface for the Phase 1D integration layer. "
    "Closed at v10.126 with G143 STRICT-READY (high) at 99/131 (75.6%). "
    "Connects the standards layer to the live Streamlit cockpit.")


# ───── Tabs ────────────────────────────────────────────────────────────

tab_coverage, tab_rules, tab_preview, tab_resolver, tab_run, tab_debug = st.tabs(
    ["📊 Coverage", "📋 Rules", "🔢 Preview Actuals",
     "🔎 Resolution Metrics", "▶️ Run Period", "🐛 Debug"])


# ───── Tab 1: Coverage ─────────────────────────────────────────────────

with tab_coverage:
    st.caption(
        "Equivalent to GET `/api/integration/coverage`. "
        "Refreshed live each visit.")
    g143 = _compute_g143_summary()
    sp = g143.get("strict_preview", {})

    col1, col2, col3 = st.columns(3)
    col1.metric(
        label="Strict-preview tier",
        value=f"{_tier_emoji(sp.get('tag','—'))} {sp.get('tag','—')}")
    col2.metric(
        label="Coverage",
        value=f"{sp.get('covered', 0)} / {sp.get('total_operational', 0)}",
        delta=f"{sp.get('coverage_pct', 0.0):.1f}%")
    col3.metric(
        label="Audit verdict",
        value="✅ PASS" if g143.get("passed") else "❌ FAIL")

    st.divider()

    # Tier-thresholds reference card
    st.markdown("**Tier thresholds** (defined in `scripts/audit.py`):")
    threshold_cols = st.columns(4)
    threshold_cols[0].markdown(
        f"🔴 **BELOW STRICT THRESHOLD**\n\n< 50% coverage")
    threshold_cols[1].markdown(
        f"🟡 **STRICT-READY (preview)**\n\n[50%, 75%) — v10.119 crossing")
    threshold_cols[2].markdown(
        f"🟢 **STRICT-READY (high)**\n\n≥ 75% — v10.125 crossing ✅")
    threshold_cols[3].markdown(
        f"⚫ **Strict-flip**\n\n100% — v10.130+ target")

    st.divider()

    with st.expander("Full G143 summary text", expanded=False):
        st.code(g143.get("summary", "—"))


# ───── Tab 2: Rules ────────────────────────────────────────────────────

with tab_rules:
    st.caption(
        "Equivalent to GET `/api/integration/rules`. "
        "Cached 5 minutes; restart the page to force a refresh.")
    rules = _load_rule_registry()
    library = _load_kpi_library()
    library_by_id = {k.get("id"): k for k in library}

    st.write(f"**{len(rules)} active aggregation rules** registered.")

    # Filters
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        all_patterns = sorted(set(r.get("pattern", "") for r in rules))
        pattern_filter = st.multiselect(
            "Filter by pattern", all_patterns, default=[])
    with fc2:
        all_tables = sorted(set(r.get("source_table", "") for r in rules))
        table_filter = st.multiselect(
            "Filter by source table", all_tables, default=[])
    with fc3:
        kpi_search = st.text_input("Search KPI ID / name", "")

    filtered = rules
    if pattern_filter:
        filtered = [r for r in filtered
                    if r.get("pattern") in pattern_filter]
    if table_filter:
        filtered = [r for r in filtered
                    if r.get("source_table") in table_filter]
    if kpi_search.strip():
        q = kpi_search.strip().lower()
        filtered = [r for r in filtered
                    if q in (r.get("kpi_id", "") or "").lower()
                    or q in (library_by_id.get(r.get("kpi_id"), {})
                             .get("name", "") or "").lower()]

    if not filtered:
        st.info("No rules match the current filters.")
    else:
        rows = []
        for r in filtered:
            kpi = library_by_id.get(r.get("kpi_id"), {})
            rows.append({
                "KPI ID": r.get("kpi_id", ""),
                "KPI Name": kpi.get("name", "—"),
                "Pattern": r.get("pattern", ""),
                "Source": r.get("source_table", ""),
                "Staff field":
                    r.get("staff_field", "(table default)"),
                "Period field": r.get("period_field", "—"),
                "Origin drop": r.get("_origin", "—"),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ───── Tab 3: Preview Actuals ──────────────────────────────────────────

with tab_preview:
    st.markdown(
        "Pick a period and compute per-staff actuals from the operational "
        "tables. **Read-only** — no writes happen on this tab. Equivalent "
        "to GET `/api/integration/actuals/{period}`.")

    period = st.text_input(
        "Period (YYYY-MM)", value="2026-04",
        help="Most rules use last_updated or operational date fields. "
             "Enter the YYYY-MM you want to filter on.")

    if st.button("Compute preview actuals", key="preview_actuals_btn"):
        try:
            from utils.actuals_engine import (
                compute_actuals_from_operational_tables)
            with st.spinner(f"Computing actuals for {period}…"):
                result = compute_actuals_from_operational_tables(period)
            st.success(f"Computed {len(result)} KPI groups.")

            # Summary metrics
            covered_kpis = sum(1 for kpi_id, by_staff in result.items()
                               if by_staff)
            total_staff_actuals = sum(len(by_staff)
                                       for by_staff in result.values())
            colA, colB = st.columns(2)
            colA.metric("KPIs producing actuals", covered_kpis)
            colB.metric("Total staff-rows emitted", total_staff_actuals)

            # Per-rule sample
            with st.expander("Per-rule sample (first 3 staff per KPI)",
                             expanded=False):
                preview_rows = []
                for kpi_id, by_staff in sorted(result.items()):
                    n = len(by_staff)
                    sample_items = list(by_staff.items())[:3]
                    sample_str = ", ".join(
                        f"{s}: {v:.2f}" if isinstance(v, (int, float))
                        else f"{s}: {v}"
                        for s, v in sample_items)
                    preview_rows.append({
                        "KPI ID": kpi_id,
                        "Staff covered": n,
                        "Sample (first 3)": sample_str or "—",
                    })
                st.dataframe(
                    preview_rows, use_container_width=True, hide_index=True)
        except ImportError as exc:
            st.error(
                f"compute_actuals_from_operational_tables not available: "
                f"{exc}")
        except Exception as exc:
            st.error(f"Compute failed: {exc}")


# ───── Tab 4: Resolution Metrics ───────────────────────────────────────

with tab_resolver:
    st.markdown(
        "Hit rates from the name-resolver and role-resolver caches. "
        "Equivalent to GET `/api/integration/resolution-metrics`.")

    try:
        from utils.staff_name_resolver import (
            refresh_cache as _refresh_name)
        from utils.staff_role_resolver import (
            refresh_cache as _refresh_role)
        # Try to introspect the resolvers if they expose metric APIs;
        # otherwise just confirm cache freshness via refresh.
        from utils.staff_name_resolver import name_to_code as _name_to_code

        # Refresh caches so the metric snapshot is current
        _refresh_name()
        try:
            _refresh_role()
        except Exception:
            pass

        st.success(
            "Name + role resolver caches refreshed. Detailed hit-rate "
            "metrics surface via the API endpoint; this tab confirms the "
            "resolvers are responsive.")

        # Show a probe
        probe = st.text_input(
            "Probe: full-name → staff_code lookup",
            value="William Mwanake")
        if probe.strip():
            try:
                code = _name_to_code(probe.strip())
                if code:
                    st.metric("Resolved staff_code", code)
                else:
                    st.warning(f"No staff_code for '{probe}'.")
            except Exception as exc:
                st.error(f"Resolver error: {exc}")

    except ImportError as exc:
        st.error(f"Resolvers not available: {exc}")


# ───── Tab 5: Run Period ───────────────────────────────────────────────

with tab_run:
    st.markdown(
        "Trigger the full integration-layer pipeline for a period. "
        "Equivalent to POST `/api/integration/run-period`.")

    sec = _load_security_config()
    if sec.get("role_gating_enabled"):
        st.info(
            f"🔒 **Role-gating ON** (v10.126 hard-flip default). "
            f"Allowed roles for write: "
            f"`{', '.join(sec.get('allowed_roles_for_write', []))}`.")
    else:
        st.warning(
            "⚠️ Role-gating DISABLED in config. JWT-only auth is in effect. "
            "Any logged-in user can trigger writes.")

    user_role = _user_role()
    user_can_write = _can_write()
    st.caption(f"Your role: `{user_role or 'unknown'}` — "
               f"{'✅ allowed to write' if user_can_write else '⛔ NOT allowed to write'}")

    period_run = st.text_input(
        "Period (YYYY-MM)", value="2026-04", key="run_period_input")
    dry_run = st.checkbox(
        "Dry run (do NOT write actuals; preview only)",
        value=True,
        help="Default ON. Uncheck to actually write actuals to the BSC "
             "engine. v10.116+ supports both modes.")

    btn_disabled = not user_can_write
    btn_label = ("Run period (dry-run)" if dry_run
                 else "Run period (WRITE)")

    if st.button(btn_label, key="run_period_btn", disabled=btn_disabled):
        if not user_can_write:
            st.error("Role check failed — operation refused.")
        else:
            try:
                from utils.actuals_engine import (
                    compute_actuals_from_operational_tables)
                with st.spinner(f"Running pipeline for {period_run}…"):
                    actuals = compute_actuals_from_operational_tables(
                        period_run)
                if dry_run:
                    st.success(
                        f"DRY RUN — would have written {len(actuals)} "
                        f"KPI groups for {period_run}. No writes "
                        f"performed.")
                else:
                    # Writing path is intentionally not implemented in
                    # this cockpit. Banks should call the API endpoint
                    # POST /api/integration/run-period with dry_run=false
                    # for the canonical write path. Surfacing it here
                    # would duplicate the contract.
                    st.warning(
                        "Cockpit only supports DRY RUN. For writes, call "
                        "POST /api/integration/run-period directly with "
                        "dry_run=false (uses the same auth + role check).")
                audit_log(
                    "integration_cockpit_run_period",
                    username,
                    f"username={username} period={period_run} "
                    f"dry_run={dry_run} kpi_groups={len(actuals)}")
            except Exception as exc:
                st.error(f"Pipeline run failed: {exc}")
                audit_log(
                    "integration_cockpit_run_period_error",
                    username,
                    f"username={username} error={exc}")
    elif btn_disabled:
        st.caption(
            "Button disabled because role-gating excludes your role. "
            "Contact admin to add your role to "
            "`_security.allowed_roles_for_write` in "
            "`integration_layer_config.json`.")


# ───── Tab 6: Debug (v10.132 — rule-explain) ───────────────────────────

with tab_debug:
    st.caption(
        "Equivalent to GET `/api/integration/rule-explain/{kpi_id}`. "
        "For any wired rule + period, shows the rule definition, input "
        "row counts at each filtering stage, sample matched rows, and "
        "the per-staff intermediate values that produce the actuals. "
        "When a number on a dashboard looks wrong, this is where you "
        "see the working.")

    try:
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule, _row_in_period,
        )
        from utils.staff_field_resolver import resolve_staff_field
    except Exception as e:
        st.error(f"Integration Layer unavailable: "
                 f"{type(e).__name__}: {e}")
    else:
        # Build picker from REGISTRY (active rules only)
        active = sorted(
            [r for r in REGISTRY],
            key=lambda r: (r.kpi_id, r.source_table))
        kpi_options = [f"{r.kpi_id} — {r.source_table} ({r.pattern})"
                       for r in active]

        col_a, col_b, col_c = st.columns([3, 2, 2])
        with col_a:
            picked = st.selectbox(
                "Rule",
                options=kpi_options,
                key="debug_rule_picker",
                help="All active aggregation rules (KPI — source table — "
                     "pattern). Library duplicates show the same KPI "
                     "twice; the first match is explained.")
        with col_b:
            period_input = st.text_input(
                "Period",
                value="2026-04",
                max_chars=7,
                key="debug_period",
                help="YYYY-MM format")
        with col_c:
            staff_filter = st.text_input(
                "Staff code (optional)",
                value="",
                key="debug_staff",
                help="Narrow the per-staff slice to one staff")
        sample_size = st.slider(
            "Sample rows to show", min_value=1, max_value=20, value=5,
            key="debug_sample_size")

        # Resolve picked rule
        idx = kpi_options.index(picked)
        rule = active[idx]

        # Validate period
        import re as _re
        if not _re.match(r"^\d{4}-(0[1-9]|1[0-2])$", period_input):
            st.warning(f"Invalid period {period_input!r}; "
                       f"expected YYYY-MM (e.g. 2026-04)")
        else:
            # Stage 1: read table
            from pathlib import Path as _P
            data_dir = _P(__file__).resolve().parent.parent / "data"
            tbl_path = data_dir / f"{rule.source_table}.json"
            if not tbl_path.exists():
                st.error(f"Operational table {rule.source_table!r} "
                         f"not found at {tbl_path}")
            else:
                import json as _j
                with open(tbl_path) as _f:
                    _d = _j.load(_f)
                rows = _d if isinstance(_d, list) else list(_d.values())

                # Stage 2: filter by period
                rows_in_period = [r for r in rows
                                  if _row_in_period(r, rule.period_field,
                                                    period_input)]

                # Stage 3: filter by primary predicate
                primary_pred = (rule.predicate
                                or rule.numerator_pred
                                or (lambda _r: True))
                try:
                    rows_matching = [r for r in rows_in_period
                                     if primary_pred(r)]
                except Exception:
                    rows_matching = rows_in_period

                # Stage 4: distinct staff
                sf = resolve_staff_field(rule.source_table,
                                         rule.staff_field)
                distinct = set()
                for r in rows_matching:
                    if rule.staff_field_extractor is not None:
                        try:
                            sc = rule.staff_field_extractor(r)
                        except Exception:
                            sc = None
                    else:
                        sc = r.get(sf)
                    if sc:
                        distinct.add(str(sc))

                # Stage 5: compute_rule
                try:
                    per_staff = compute_rule(rule, rows, period_input, sf)
                except Exception as _e:
                    st.error(f"compute_rule failed: "
                             f"{type(_e).__name__}: {_e}")
                    per_staff = {}

                # ── Display ──
                st.divider()

                # Row 1: rule definition
                with st.expander("Rule definition", expanded=False):
                    st.json({
                        "kpi_id":            rule.kpi_id,
                        "source_table":      rule.source_table,
                        "pattern":           rule.pattern,
                        "description":       rule.description or "",
                        "period_field":      rule.period_field,
                        "staff_field":       rule.staff_field,
                        "resolved_staff_field": sf,
                        "value_field":       rule.value_field,
                        "start_field":       rule.start_field,
                        "end_field":         rule.end_field,
                        "numerator_field":   rule.numerator_field,
                        "denominator_field": rule.denominator_field,
                        "bool_field":        rule.bool_field,
                        "decimals":          rule.decimals,
                        "invert":            rule.invert,
                        "uses_extractor":
                            rule.staff_field_extractor is not None,
                    })

                # Row 2: pipeline funnel
                st.subheader("Input funnel")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Rows in table", len(rows))
                m2.metric("In period", len(rows_in_period))
                m3.metric("Matching predicate", len(rows_matching))
                m4.metric("Distinct staff", len(distinct))

                # Row 3: sample rows
                st.subheader(f"Sample matched rows "
                             f"(top {min(sample_size, len(rows_matching))} "
                             f"of {len(rows_matching)})")
                if rows_matching:
                    import pandas as _pd
                    sample = []
                    for r in rows_matching[:sample_size]:
                        # truncate verbose values for display
                        display = {}
                        for k, v in r.items():
                            if isinstance(v, str) and len(v) > 80:
                                display[k] = v[:80] + "…"
                            elif isinstance(v, (list, dict)):
                                display[k] = _j.dumps(v)[:80] + "…" \
                                    if len(_j.dumps(v)) > 80 else v
                            else:
                                display[k] = v
                        sample.append(display)
                    st.dataframe(_pd.DataFrame(sample),
                                 use_container_width=True)
                else:
                    st.info("No rows match the rule's primary predicate "
                            "for this period. Verify period_field "
                            f"({rule.period_field!r}) is populated and "
                            "the predicate logic.")

                # Row 4: per-staff values
                st.subheader("Per-staff aggregated values")
                if not per_staff:
                    st.info("compute_rule returned no per-staff values.")
                else:
                    items = sorted(per_staff.items(),
                                   key=lambda kv: -float(kv[1])
                                       if isinstance(kv[1], (int, float))
                                       else 0)
                    if staff_filter:
                        items = [kv for kv in items if kv[0] == staff_filter]
                    if not items:
                        st.warning(f"No per-staff entry for "
                                   f"{staff_filter!r}.")
                    else:
                        df_rows = [{"staff_code": sc,
                                    "value": round(float(v), rule.decimals)
                                              if isinstance(v, (int, float))
                                              else v}
                                   for sc, v in items[:50]]
                        st.dataframe(_pd.DataFrame(df_rows),
                                     use_container_width=True)
                        if len(items) > 50:
                            st.caption(f"Showing top 50 of {len(items)} "
                                       f"staff. Filter by staff code to "
                                       "narrow.")


# ───── Footer ──────────────────────────────────────────────────────────

st.divider()
st.caption(
    "v10.132 · Integration cockpit consumes the same utility functions "
    "as `/api/integration/*` endpoints (read-only paths) — identical "
    "results, simpler stack. Debug tab mirrors GET "
    "`/api/integration/rule-explain/{kpi_id}` (added v10.132). "
    "Phase 1D retro at `docs/Phase_1D_Integration_Layer_Retro.md`.")
