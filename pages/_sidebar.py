"""pages/_sidebar.py — Shared sidebar rendered on every page."""
import streamlit as st
import pandas as pd
import io
from utils.core import (audit_log, process_kpi_data, build_staff_scores,
                         build_staff_registry, ExecuteManager, cache_upload,
                         BRANCH_REGION, fmt_num)


def show_sidebar():
    ud    = st.session_state.get("user_data", {})
    uname = st.session_state.get("username", "")
    em    = st.session_state.get("execute_manager")

    with st.sidebar:
        # ── User identity ──────────────────────────────────────────
        st.markdown(
            f"<div style='padding:10px 12px;background:var(--color-background-secondary);"
            f"border-radius:8px;border:0.5px solid var(--color-border-tertiary);"
            f"margin-bottom:10px'>"
            f"<div style='font-weight:500;font-size:14px'>{ud.get('full_name', uname)}</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"{ud.get('role','')} · {ud.get('unit','')}</div>"
            f"</div>",
            unsafe_allow_html=True)

        # ── Execute role badges ────────────────────────────────────
        exec_roles = []
        if ud.get("is_sponsor"):          exec_roles.append("Sponsor")
        if ud.get("is_workstream_lead"):  exec_roles.append("WS Lead")
        if ud.get("is_finance_approver"): exec_roles.append("Finance")
        if exec_roles:
            st.caption("Execute: " + " · ".join(exec_roles))

        # ── Pending actions ────────────────────────────────────────
        if em:
            try:
                actions = em.get_my_actions(uname, ud.get("role", ""))
                if actions:
                    st.warning(f"⚡ {len(actions)} action(s) pending")
            except Exception:
                pass

        st.markdown("---")

        # ── File upload ────────────────────────────────────────────
        st.markdown("**BSC data**")
        uploaded = st.file_uploader(
            "A2Z Blueprint Data.xlsx",
            type=["xlsx","xls"], key="sidebar_upload",
            help="Upload once — data stays loaded until you logout")

        # Always extract bytes first; cache_upload persists them across reruns
        raw = cache_upload(uploaded, "_bsc_raw_bytes")

        if raw is not None:
            fname = (uploaded.name if uploaded is not None
                     else st.session_state.get("_last_upload","cached"))
            if st.session_state.get("_last_upload") != fname:
                _process_upload_bytes(raw)
                st.session_state["_last_upload"] = fname
                st.success(f"✅ Loaded: {fname}")
            else:
                n = len(st.session_state.get("staff_scores", []))
                st.caption(f"✅ {fname} — {n} staff")
        else:
            st.caption("Upload your BSC Excel to begin")

        st.markdown("---")

        # ── Logout ─────────────────────────────────────────────────
        if st.button("Logout", use_container_width=True):
            audit_log("LOGOUT", uname)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def _process_upload_bytes(raw_bytes: bytes):
    """Process raw Excel bytes — called with already-extracted bytes so reruns are safe."""
    if not raw_bytes:
        return
    try:
        xl        = pd.ExcelFile(io.BytesIO(raw_bytes))

        # Detect format — new format has 'KPI Data' sheet with header on row 1
        if 'KPI Data' in xl.sheet_names:
            df_raw = pd.read_excel(io.BytesIO(raw_bytes), sheet_name='KPI Data', header=1)
        elif 'System Build table 1' in xl.sheet_names:
            df_raw = pd.read_excel(io.BytesIO(raw_bytes), sheet_name='System Build table 1')
        else:
            df_raw = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=0, header=1)

        df_proc  = process_kpi_data(df_raw)
        scores   = build_staff_scores(df_proc)
        registry = build_staff_registry(raw_bytes)  # bytes — no hashing issue

        ud      = st.session_state.get("user_data", {})
        role_l  = str(ud.get("role", "")).lower()
        can_all = ud.get("can_view_all", False)

        if can_all or any(k in role_l for k in ("admin","director","md","ceo","chief")):
            filtered = scores.copy()
        elif "regional head" in role_l:
            region    = ud.get("region") or BRANCH_REGION.get(ud.get("unit",""), "North")
            reg_units = [u for u, r in BRANCH_REGION.items() if r == region]
            filtered  = scores[scores["Unit"].isin(reg_units)].copy()
        elif any(k in role_l for k in ("branch manager","head of","department head")):
            unit     = ud.get("unit", "")
            filtered = scores[scores["Unit"] == unit].copy() if unit else scores.copy()
        else:
            name     = ud.get("full_name", "")
            filtered = scores[scores["Staff Name"] == name].copy() if name else scores.copy()

        month_cols = [c for c in df_proc.columns
                      if any(m in str(c) for m in
                             ["Jan","Feb","Mar","Apr","May","Jun",
                              "Jul","Aug","Sep","Oct","Nov","Dec"])
                      and 'Target' not in str(c)]

        active_months = [c for c in month_cols
                         if df_proc[c].notna().any() and (df_proc[c] != 0).any()]

        st.session_state.update({
            "df_processed":    df_proc,
            "staff_scores":    scores,
            "filtered_staff":  filtered,
            "all_months":      month_cols,
            "active_months":   active_months,
            "staff_registry":  registry,
        })
    except Exception as exc:
        import traceback
        st.sidebar.error(f"Upload error: {exc}")
        st.sidebar.code(traceback.format_exc(), language="python")


def _process_upload(uploaded_file):
    """Alias — extracts bytes then calls _process_upload_bytes."""
    raw = cache_upload(uploaded_file, "_bsc_raw_bytes")
    if raw:
        _process_upload_bytes(raw)
