"""pages/_admin_module_config.py — Module Configuration Centre.

Renders a single tab in the admin page that lets admins govern all 19 modules
from one place. For each module:
  - HARDCODED items shown as read-only (these are CBK-mandated or vendor-fixed)
  - CONFIGURABLE items shown as editable form fields, grouped by module
  - Save button per module, with audit log

Reads/writes data/module_config.json.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from utils.core import audit_log

DATA = Path(__file__).parent.parent / "data"

# Module metadata for nicer display — icons, page paths, departments, KPIs
MODULE_META = {
    # Phase 0 (existing modules)
    "clearing":              {"icon":"🏦","name":"Clearing & Settlement",      "page":"73_channels.py",        "dept":"Operations",            "kpis":["K055","K056","K057"]},
    "consent":               {"icon":"📜","name":"Consent Register",           "page":"75_data_protection.py", "dept":"Compliance",            "kpis":["K049"]},
    "retailer_finance":      {"icon":"💼","name":"Retailer Finance",           "page":"70_retailer_finance.py","dept":"Commercial & Corporate","kpis":["K022","K041"]},
    "bid_bond":              {"icon":"📋","name":"Bid Bonds & Guarantees",     "page":"71_bid_bond.py",        "dept":"Trade Finance",         "kpis":["K022","K023"]},
    "observability":         {"icon":"📡","name":"Observability",              "page":"72_observability.py",   "dept":"IT & Digital",          "kpis":["K066","K067","K068"]},
    "channels":              {"icon":"📲","name":"Channel Management",         "page":"73_channels.py",        "dept":"Digital Banking",       "kpis":["K069","K070","K071"]},

    # Phase 1 — CRITICAL Regulatory
    "cbk_returns":           {"icon":"📊","name":"CBK Returns Centre",         "page":"74_cbk_returns.py",     "dept":"Compliance",            "kpis":["K072","K073","K074"]},
    "data_protection":       {"icon":"🔒","name":"Data Protection Office",     "page":"75_data_protection.py", "dept":"Compliance",            "kpis":["K075","K076","K077"]},
    "sanctions_screening":   {"icon":"🚨","name":"Sanctions Screening",        "page":"76_sanctions.py",       "dept":"Compliance",            "kpis":["K078","K079"]},
    "regulatory_capital":    {"icon":"🏛️","name":"Capital & Liquidity",       "page":"77_capital.py",         "dept":"Treasury",              "kpis":["K080","K081","K082","K083"]},

    # Phase 2 — HIGH Business
    "customer_onboarding":   {"icon":"🎯","name":"Customer Onboarding",        "page":"78_onboarding.py",      "dept":"Retail Banking",        "kpis":["K084","K085","K086"]},
    "card_management":       {"icon":"💳","name":"Card Management",            "page":"79_cards.py",           "dept":"Retail Banking",        "kpis":["K087","K088","K089","K090"]},
    "merchant_acquiring":    {"icon":"🏪","name":"Merchant Acquiring",         "page":"80_merchant.py",        "dept":"Commercial & Corporate","kpis":["K091","K092","K093"]},
    "alm_liquidity":         {"icon":"💧","name":"ALM & Liquidity",            "page":"81_alm.py",             "dept":"Treasury",              "kpis":["K094","K095","K096","K097"]},
    "operational_risk":      {"icon":"⚠️","name":"Operational Risk Losses",   "page":"82_oprisk.py",          "dept":"Risk & Compliance",     "kpis":["K098","K099","K100"]},

    # Phase 3 — STRATEGIC
    "strategic_initiatives": {"icon":"🎯","name":"Strategic Initiatives",      "page":"83_strategy.py",        "dept":"Executive",             "kpis":["K101","K102","K103"]},
    "board_papers":          {"icon":"📋","name":"Board Pack & Papers",        "page":"84_board.py",           "dept":"Executive",             "kpis":["K104","K105"]},
    "esg_climate":           {"icon":"🌱","name":"ESG & Climate Risk",         "page":"85_esg.py",             "dept":"Risk & Compliance",     "kpis":["K106","K107","K108"]},

    # FLEXCUBE
    "flexcube_integration":  {"icon":"🔌","name":"FLEXCUBE Integration",       "page":"86_flexcube.py",        "dept":"IT & Digital",          "kpis":["K109","K110","K111"]},
}

# Group modules by phase for the UI
PHASES = {
    "📦 Phase 0 — Existing Modules":       ["clearing","consent","retailer_finance","bid_bond","observability","channels"],
    "🚨 Phase 1 — Regulatory Critical":   ["cbk_returns","data_protection","sanctions_screening","regulatory_capital"],
    "💼 Phase 2 — Business Critical":     ["customer_onboarding","card_management","merchant_acquiring","alm_liquidity","operational_risk"],
    "🎯 Phase 3 — Strategic":             ["strategic_initiatives","board_papers","esg_climate"],
    "🔌 FLEXCUBE Integration":            ["flexcube_integration"],
}

def _load_config():
    p = DATA / "module_config.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def _save_config(cfg):
    p = DATA / "module_config.json"
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def _format_value_for_display(val):
    """Pretty-print a config value for the read-only hardcoded section."""
    if isinstance(val, list):
        return ", ".join(str(x) for x in val) if val else "—"
    if isinstance(val, bool):
        return "✅ Yes" if val else "❌ No"
    if isinstance(val, dict):
        return ", ".join(f"{k}: {v}" for k,v in val.items())
    return str(val) if val is not None else "—"

def _safe_int_bounds(field_name, field_value):
    """Compute safe min/max bounds for an integer field.

    Bounds are computed from the actual stored value (not a brittle field-name
    heuristic) so a banking ratio like LCR=110% doesn't blow past a hardcoded
    cap of 100. We expand the range to give the admin headroom in both directions.
    """
    fname = field_name.lower()
    val = field_value if field_value is not None else 0
    abs_val = abs(val) if val else 1

    # Lower bound: zero by default, but allow negatives if the stored value is negative
    lo = 0 if val >= 0 else -10 * abs_val

    # Upper bound: at minimum allow 10× the current value, with sensible floors per category
    if "pct" in fname or "percent" in fname or "ratio" in fname:
        hi = max(200, val * 3)        # ratios often exceed 100 (LCR/NSFR)
    elif "days" in fname:
        hi = max(3650, val * 3)        # 10 years default, expand if stored higher
    elif "hours" in fname:
        hi = max(8760, val * 3)        # 1 year of hours
    elif "minutes" in fname:
        hi = max(10080, val * 3)       # 1 week of minutes
    elif "seconds" in fname:
        hi = max(3600, val * 3)        # 1 hour
    elif "kes" in fname or "amount" in fname or "limit" in fname:
        hi = max(10_000_000_000, val * 10)  # KES amounts can be huge
    elif "count" in fname or "target" in fname:
        hi = max(10_000, val * 10)
    else:
        hi = max(1_000_000, val * 10)

    return int(lo), int(hi)


def _render_configurable_field(field_name, field_value, key_prefix):
    """Render the right Streamlit input for a configurable value."""
    label = field_name.replace("_", " ").title()
    field_key = f"{key_prefix}__{field_name}"

    # bool → checkbox  (must be checked BEFORE int — Python: bool is subclass of int)
    if isinstance(field_value, bool):
        return st.checkbox(label, value=field_value, key=field_key)

    # int → number_input with dynamic bounds
    if isinstance(field_value, int):
        lo, hi = _safe_int_bounds(field_name, field_value)
        try:
            return st.number_input(label, min_value=lo, max_value=hi,
                                   value=field_value, key=field_key, step=1)
        except Exception:
            # Last-resort fallback: free-form number input with no bounds
            return st.number_input(label, value=field_value, key=field_key, step=1)

    # float → number_input with no rigid bounds (banking values vary widely)
    if isinstance(field_value, float):
        try:
            return st.number_input(label, value=field_value, key=field_key,
                                   step=0.1, format="%.4f")
        except Exception:
            return st.number_input(label, value=field_value, key=field_key, step=0.1)

    # list → multiselect / display
    if isinstance(field_value, list):
        text_val = ", ".join(str(x) for x in field_value)
        new_text = st.text_input(label + " (comma-separated)", value=text_val, key=field_key)
        return [x.strip() for x in new_text.split(",") if x.strip()]

    # dict → JSON-style text area
    if isinstance(field_value, dict):
        json_text = json.dumps(field_value, indent=2)
        new_json = st.text_area(label + " (JSON)", value=json_text, key=field_key, height=100)
        try:
            return json.loads(new_json)
        except Exception:
            return field_value

    # string → text_input (longer if email/URL)
    if isinstance(field_value, str):
        if "email" in field_name or "url" in field_name or "endpoint" in field_name:
            return st.text_input(label, value=field_value, key=field_key)
        if len(field_value) > 60:
            return st.text_area(label, value=field_value, key=field_key, height=80)
        return st.text_input(label, value=field_value, key=field_key)

    return st.text_input(label, value=str(field_value or ""), key=field_key)


def render_module_config_centre(tab, uname: str, is_admin: bool):
    """Main render function — called from pages/7_admin.py."""
    with tab:
        if not is_admin:
            st.warning("🔒 Module Configuration Centre is admin-only.")
            return

        st.markdown(
            "<div style='padding:16px 0 4px'>"
            "<span style='font-size:22px;font-weight:800'>🔧 Module Configuration Centre</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Govern all 19 modules from one place</span></div>",
            unsafe_allow_html=True,
        )

        cfg = _load_config()

        # ── Summary metrics ───────────────────────────────────────
        n_modules     = len(cfg)
        n_hardcoded   = sum(len(v.get("hardcoded",{}))    for v in cfg.values())
        n_configurable= sum(len(v.get("configurable",{})) for v in cfg.values())
        all_kpis = set()
        for k, m in MODULE_META.items():
            for kpi in m.get("kpis",[]): all_kpis.add(kpi)

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Modules governed",      n_modules)
        m2.metric("Hardcoded settings",    n_hardcoded, help="CBK-mandated or vendor-fixed — cannot be edited")
        m3.metric("Configurable settings", n_configurable, help="Bank-specific thresholds — editable here")
        m4.metric("KPIs covered",          len(all_kpis))

        st.caption(
            "ℹ️ **Hardcoded** items reflect CBK Prudential Guidelines, Basel III, "
            "Data Protection Act 2019, ISO 20022 standards, or Oracle FLEXCUBE specifications. "
            "They cannot be changed because doing so would breach regulation or void vendor warranty. "
            "**Configurable** items are bank-specific operational thresholds that the admin can tune."
        )
        st.markdown("---")

        # ── Search filter ─────────────────────────────────────────
        search = st.text_input("🔎 Filter modules (by name, dept, or KPI)", "", key="mc_search")
        search_lower = search.lower().strip()

        def _matches_search(mod_key):
            if not search_lower: return True
            meta = MODULE_META.get(mod_key, {})
            haystack = " ".join([
                mod_key,
                meta.get("name",""),
                meta.get("dept",""),
                " ".join(meta.get("kpis",[])),
            ]).lower()
            return search_lower in haystack

        # ── Phase-grouped sections ────────────────────────────────
        for phase_label, mod_keys in PHASES.items():
            visible_mods = [k for k in mod_keys if k in cfg and _matches_search(k)]
            if not visible_mods: continue

            with st.expander(f"{phase_label} ({len(visible_mods)} modules)", expanded=("Phase 1" in phase_label or "FLEXCUBE" in phase_label)):
                for mod_key in visible_mods:
                    meta     = MODULE_META.get(mod_key, {})
                    mod_cfg  = cfg.get(mod_key, {})
                    hardcoded     = mod_cfg.get("hardcoded",     {})
                    configurable  = mod_cfg.get("configurable", {})
                    bsc_kpis      = mod_cfg.get("bsc_kpis", meta.get("kpis",[]))

                    # Module header — built piece by piece to avoid f-string newline issues
                    icon = meta.get("icon","📁")
                    nm   = meta.get("name", mod_key)
                    dept = meta.get("dept","—")
                    page = meta.get("page","—")

                    header_html = (
                        f"### {icon} {nm}"
                        + chr(10)
                        + f"<small>"
                        + f"<b>Module key:</b> <code>{mod_key}</code> &nbsp;·&nbsp; "
                        + f"<b>Page:</b> <code>{page}</code> &nbsp;·&nbsp; "
                        + f"<b>Department:</b> {dept} &nbsp;·&nbsp; "
                        + f"<b>Drives KPIs:</b> {', '.join(bsc_kpis) if bsc_kpis else '—'}"
                        + f"</small>"
                    )
                    st.markdown(header_html, unsafe_allow_html=True)

                    col1, col2 = st.columns([1,1])

                    # ── Hardcoded (read-only) ──────────────────────
                    with col1:
                        st.markdown("**🔒 Hardcoded (read-only)**")
                        if hardcoded:
                            hc_rows = [
                                {"Setting": k.replace("_"," ").title(),
                                 "Value":   _format_value_for_display(v)[:80]}
                                for k, v in hardcoded.items()
                            ]
                            st.dataframe(pd.DataFrame(hc_rows), use_container_width=True, hide_index=True, height=min(35*(len(hc_rows)+1)+3, 250))
                            st.caption(f"{len(hardcoded)} regulatory/vendor-fixed settings")
                        else:
                            st.caption("No hardcoded settings.")

                    # ── Configurable (editable) ────────────────────
                    with col2:
                        st.markdown("**⚙️ Configurable**")
                        if configurable:
                            updated = {}
                            for field_name, field_value in configurable.items():
                                new_val = _render_configurable_field(
                                    field_name, field_value,
                                    key_prefix=f"mc_{mod_key}",
                                )
                                updated[field_name] = new_val

                            save_col1, save_col2 = st.columns([1,3])
                            if save_col1.button("💾 Save", key=f"mc_save_{mod_key}", type="primary"):
                                changes = {k: (configurable[k], updated[k])
                                           for k in updated if updated[k] != configurable.get(k)}
                                if changes:
                                    cfg[mod_key]["configurable"] = updated
                                    cfg[mod_key]["last_updated"]  = datetime.utcnow().isoformat() + "Z"
                                    cfg[mod_key]["last_updated_by"]= uname
                                    _save_config(cfg)
                                    audit_log("MODULE_CONFIG_UPDATED", uname,
                                             f"{mod_key}: {len(changes)} field(s) changed: " + ", ".join(changes.keys()))
                                    st.cache_data.clear()
                                    save_col2.success(f"✅ Saved {len(changes)} change(s)")
                                    st.rerun()
                                else:
                                    save_col2.info("No changes to save.")
                        else:
                            st.caption("No configurable settings.")

                    if mod_cfg.get("last_updated"):
                        st.caption(f"Last updated: {mod_cfg['last_updated'][:19]} by {mod_cfg.get('last_updated_by','—')}")

                    st.markdown("---")

        # ── Audit / Export footer ─────────────────────────────────
        st.markdown("### 📋 Configuration Export & Audit")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📥 Download full config as JSON", key="mc_export"):
                json_str = json.dumps(cfg, indent=2)
                st.download_button(
                    label="⬇️ Click to download module_config.json",
                    data=json_str,
                    file_name=f"module_config_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    key="mc_dl",
                )
        with c2:
            st.caption(
                f"Configuration last loaded at {datetime.now().strftime('%Y-%m-%d %H:%M')}. "
                f"All changes are audited in the Audit Log tab."
            )
