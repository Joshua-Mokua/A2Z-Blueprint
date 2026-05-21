# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_sidebar.py — Shared sidebar rendered on every page."""
import streamlit as st
import pandas as pd
import io
from utils.core_audit import audit_log
from utils.core import (process_kpi_data, build_staff_scores,
                         build_staff_registry, ExecuteManager, cache_upload,
                         BRANCH_REGION, fmt_num)
from pages._shared import safe_html



def _try_auto_load_cbs() -> bool:
    """
    Try to auto-load staff + KPI data from CBS-generated files.
    Returns True if data was loaded successfully.
    Looks for files in:
      1. cbs_data/ (CBS generator output)
      2. a2z/data/ (compute_actuals.py output)
    """
    import os, glob
    from pathlib import Path as _Path

    # Find project root (two levels up from pages/_sidebar.py)
    _here   = _Path(__file__).parent          # pages/
    _root   = _here.parent                    # a2z/
    _parent = _root.parent                    # project root (where cbs_data lives)
    _data   = _root / "data"

    # ── Look for actuals Excel in a2z/data/ or cbs_data/ ─────────────
    _actuals_file = None
    for _search in [_data, _parent/"cbs_data"]:
        _candidates = sorted(_search.glob("actuals_*.xlsx"), reverse=True)
        if not _candidates:
            _candidates = sorted(_search.glob("actuals_*.csv"), reverse=True)
        if _candidates:
            _actuals_file = _candidates[0]
            break

    if _actuals_file is None:
        return False   # no CBS actuals found — fall through to upload

    # ── Check if already loaded ────────────────────────────────────
    _cached_src = st.session_state.get("_cbs_loaded_file","")
    if _cached_src == str(_actuals_file) and len(st.session_state.get("staff_scores",[])) > 0:
        return True   # already loaded this file

    try:
        import pandas as _pd
        from utils.core import process_kpi_data, build_staff_scores, BRANCH_REGION

        # Load actuals file
        if str(_actuals_file).endswith(".xlsx"):
            # Try header=1 first (our format has row 1 as a title row)
            try:
                _df = _pd.read_excel(_actuals_file, header=1)
                if "KPI" not in _df.columns:
                    _df = _pd.read_excel(_actuals_file, header=0)
            except:
                _df = _pd.read_excel(_actuals_file, header=0)
        else:
            _df = _pd.read_csv(_actuals_file)

        _df.columns = [str(c).strip() for c in _df.columns]
        if len(_df) < 5:
            return False

        _df_proc = process_kpi_data(_df)
        _scores  = build_staff_scores(_df_proc)

        if "Region" not in _scores.columns and "Unit" in _scores.columns:
            _scores["Region"] = _scores["Unit"].map(BRANCH_REGION).fillna("Head Office")

        # Load staff register if available
        _sr_file = None
        for _search in [_parent/"cbs_data", _data]:
            _sr = _search / "staff_register.xlsx"
            if _sr.exists(): _sr_file = _sr; break
            _sr = _search / "staff_register.csv"
            if _sr.exists(): _sr_file = _sr; break

        _sr_df = _pd.DataFrame()
        if _sr_file:
            try:
                if str(_sr_file).endswith(".xlsx"):
                    _sr_df = _pd.read_excel(_sr_file)
                else:
                    _sr_df = _pd.read_csv(_sr_file)
            except: pass

        # Detect month columns
        from utils.core import detect_month_actual_columns as _dmc
        _month_cols   = _dmc(_df_proc)
        from datetime import datetime as _dt
        from utils.core import parse_month_column as _pmc
        _now = _dt.now()
        _active_months = [c for c in _month_cols
                          if (lambda d: d and (d.year < _now.year or
                              (d.year == _now.year and d.month <= _now.month)))(_pmc(c))]

        st.session_state.update({
            "df_processed":   _df_proc,
            "staff_scores":   _scores,
            "filtered_staff": _scores,
            "all_months":     _month_cols,
            "active_months":  _active_months,
            "staff_registry": _sr_df,
            "_cbs_loaded_file": str(_actuals_file),
            "_data_source":   f"CBS Auto ({_actuals_file.name})",
            "_last_upload":   _actuals_file.name,
        })

        # Wire cascade targets in
        _casc = st.session_state.get("cascade_manager")
        if _casc:
            try:
                _df_proc2 = _casc.write_targets_to_df(_df_proc)
                _scores2  = build_staff_scores(_df_proc2)
                st.session_state["df_processed"] = _df_proc2
                st.session_state["staff_scores"]  = _scores2
            except: pass

        return True

    except Exception as _e:
        # Silent fail — fall through to manual upload
        import traceback
        st.session_state["_cbs_load_error"] = str(_e)
        return False


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
            f"<div style='font-weight:500;font-size:14px'>{safe_html(ud.get('full_name', uname))}</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"{safe_html(ud.get('role',''))} · {safe_html(ud.get('unit',''))}</div>"
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

        # ── Data loading — CBS auto-load or manual upload ──────────
        _data_loaded = len(st.session_state.get("staff_scores", [])) > 0

        if not _data_loaded:
            _auto_loaded = _try_auto_load_cbs()
            _data_loaded = _auto_loaded

        if _data_loaded:
            _n = len(st.session_state.get("staff_scores",[]))
            _src = st.session_state.get("_data_source","CBS")
            st.markdown(
                f"<div style='padding:6px 10px;background:rgba(16,185,129,0.15);"
                f"border:1px solid rgba(16,185,129,0.3);border-radius:6px;"
                f"font-size:11px;color:#10B981;margin-bottom:6px'>"
                f"✅ <b>{_src}</b> — {_n} staff loaded</div>",
                unsafe_allow_html=True)
            # Still allow manual override upload
            with st.expander("📤 Override with Excel upload"):
                uploaded = st.file_uploader(
                    "A2Z Blueprint Data.xlsx",
                    type=["xlsx","xls"], key="sidebar_upload",
                    help="Overrides CBS auto-load with a custom Excel file")
                raw = cache_upload(uploaded, "_bsc_raw_bytes")
                if raw is not None:
                    fname = (uploaded.name if uploaded is not None
                             else st.session_state.get("_last_upload","cached"))
                    if st.session_state.get("_last_upload") != fname:
                        _process_upload_bytes(raw)
                        st.session_state["_last_upload"] = fname
                        st.session_state["_data_source"] = f"Excel: {fname}"
                        st.success(f"✅ Loaded: {fname}")
        else:
            # No CBS data — show upload
            st.markdown("**BSC data**")
            uploaded = st.file_uploader(
                "A2Z Blueprint Data.xlsx",
                type=["xlsx","xls"], key="sidebar_upload2",
                help="Upload once — data stays loaded until you logout")
            raw = cache_upload(uploaded, "_bsc_raw_bytes")
            if raw is not None:
                fname = (uploaded.name if uploaded is not None
                         else st.session_state.get("_last_upload","cached"))
                if st.session_state.get("_last_upload") != fname:
                    _process_upload_bytes(raw)
                    st.session_state["_last_upload"] = fname
                    st.success(f"✅ Loaded: {fname}")
            else:
                st.caption("⏳ Run generate_staff.py + compute_actuals.py to auto-load, or upload Excel above")

        # ── Always recompute filtered_staff for current user ─────────
        # Runs on every render — ensures a new login immediately gets
        # their own filtered view, not the previous user's cached view.
        _scores = st.session_state.get("staff_scores", pd.DataFrame())
        if len(_scores):
            _cur_ud  = st.session_state.get("user_data", {})
            _cur_uid = (_cur_ud.get("staff_code","") or
                        _cur_ud.get("full_name","") or
                        st.session_state.get("username",""))
            if st.session_state.get("_filtered_for") != _cur_uid:
                from utils.core_audit import get_visible_staff as _gvs
                _new_filtered = _gvs(_cur_ud, _scores)
                st.session_state["filtered_staff"] = _new_filtered
                st.session_state["_filtered_for"]  = _cur_uid

        st.markdown("---")

        # ── My profile photo ───────────────────────────────────────
        try:
            from utils.core import photo_avatar_html, save_profile_photo, get_photo_b64
            _my_sc  = ud.get("staff_code","") or uname
            _my_nm  = ud.get("full_name", uname)
            _my_av  = photo_avatar_html(_my_sc, _my_nm, size=40)
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:10px;padding:6px 0'>"
                f"{_my_av}"
                f"<div style='font-size:11px;color:rgba(255,255,255,0.7);flex:1'>"
                f"<b style='color:white'>{_my_nm}</b><br>{ud.get('role','')}</div>"
                f"</div>", unsafe_allow_html=True)
            new_photo = st.file_uploader(
                "📷 Update my photo",
                type=["jpg","jpeg","png","webp"],
                key="self_photo_upload",
                help="Square crop recommended · max 2MB · JPG or PNG")
            if new_photo is not None:
                # Guard: only process if this is a NEW file (different from last saved)
                _photo_hash = hash(new_photo.name + str(new_photo.size))
                if st.session_state.get("_last_photo_hash") != _photo_hash:
                    if new_photo.size <= 2_000_000:
                        ext = new_photo.name.split(".")[-1].lower()
                        save_profile_photo(_my_sc, new_photo.read(), ext)
                        st.session_state["_last_photo_hash"] = _photo_hash
                        st.session_state.pop(f"_photo_uri_{_my_sc}", None)
                        st.toast("✅ Photo saved", icon="📷")
                    else:
                        st.warning("File too large — max 2MB")
        except Exception: pass

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

        # Load Staff Register for regional head filtering
        if 'Staff Register' in xl.sheet_names:
            sr_raw = pd.read_excel(io.BytesIO(raw_bytes), sheet_name='Staff Register', header=1)
            sr_raw.columns = [str(c).strip() for c in sr_raw.columns]
            st.session_state["staff_register_df"] = sr_raw

        df_proc  = process_kpi_data(df_raw)
        scores   = build_staff_scores(df_proc)
        registry = build_staff_registry(raw_bytes)  # bytes — no hashing issue

        ud      = st.session_state.get("user_data", {})

        # ── Hierarchy-aware staff visibility ─────────────────────────
        from utils.core_audit import get_visible_staff
        filtered = get_visible_staff(ud, scores)

        month_cols = [c for c in df_proc.columns
                      if any(m in str(c) for m in
                             ["Jan","Feb","Mar","Apr","May","Jun",
                              "Jul","Aug","Sep","Oct","Nov","Dec"])
                      and 'Target' not in str(c)]

        active_months = [c for c in month_cols
                         if df_proc[c].notna().any() and (df_proc[c] != 0).any()]

        # ── Apply cascade targets for locked staff ──────────────────
        # If a staff member has accepted+locked their targets via the cascade,
        # their cascaded target overwrites whatever was in the upload file.
        try:
            from utils.core import CascadeManager
            casc_inst = st.session_state.get("cascade_manager")
            if casc_inst is None:
                casc_inst = CascadeManager()
                st.session_state["cascade_manager"] = casc_inst
            if hasattr(casc_inst, "write_targets_to_df"):
                df_proc = casc_inst.write_targets_to_df(df_proc, _gfy())
                # Rebuild scores after target update
                scores   = build_staff_scores(df_proc)
                # Recompute filtered view after cascade write-back
                filtered = get_visible_staff(ud, scores)
        except Exception as _ce:
            pass  # Cascade write-back is non-critical — don't block data load

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
