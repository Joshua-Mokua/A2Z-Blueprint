"""pages/1_perform.py — Perform module."""
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *

from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access, get_my_scope
require_access("perform")


# Load session state
um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

# Shared data
staff_scores  = st.session_state.get("staff_scores", pd.DataFrame())
df_proc       = st.session_state.get("df_processed", pd.DataFrame())
filtered      = st.session_state.get("filtered_staff", pd.DataFrame())
all_months    = st.session_state.get("all_months", [])
active_months = st.session_state.get("active_months", all_months)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏆 Perform</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "BSC scorecard · KPI achievement · Pillar scores · Trend</span></div>",
    unsafe_allow_html=True)

# Guard — no file uploaded yet
if len(staff_scores) == 0:
    st.markdown(
        f"<div style='padding:40px;text-align:center;background:var(--brand-light,#E8F5EE);"
        f"border-radius:12px;border:1px solid var(--brand-primary,#006B3F)33'>"
        f"<div style='font-size:32px;margin-bottom:12px'>📊</div>"
        f"<div style='font-size:18px;font-weight:500;color:var(--brand-primary,#006B3F)'>Upload your BSC data to begin</div>"
        f"<div style='color:#666;margin-top:8px;font-size:14px'>"
        f"Use the file uploader in the sidebar to load the Excel file.</div>"
        f"</div>",
        unsafe_allow_html=True)
    st.stop()

# Safe access helpers
_has_role  = "Role" in filtered.columns
_has_name  = "Staff Name" in filtered.columns
_has_unit  = "Unit" in filtered.columns
_has_region = "Region" in filtered.columns

# ════════════════════════════════════════════════════════════════
# BSC SCORECARD SUMMARY — shown first before deep-dive
# ════════════════════════════════════════════════════════════════
def render_bsc_scorecard(staff_df, df_kpi):
    """Compact BSC scorecard table — pillar | KPI | weight | target | actual | ach% | monthly | score."""
    st.markdown(
        "<div style='padding:12px 18px;background:var(--brand-primary,#006B3F);border-radius:8px;margin-bottom:12px'>"
        "<div style='color:var(--color-background-primary);font-size:15px;font-weight:500'>BSC Scorecard</div>"
        "<div style='color:var(--brand-accent,#9FE1CB);font-size:11px'>"
        "All KPIs at a glance — Target · Achievement · Score</div>"
        "</div>", unsafe_allow_html=True)

    if staff_df.empty or len(staff_df) == 0:
        st.info("No staff data loaded.")
        return

    # ── Grouped searchable selector ───────────────────────────
    # ── Search box ───────────────────────────────────────────────────
    search_sc = st.text_input(
        "🔍 Search by name or role",
        placeholder="e.g. Grace Kamau  or  Teller  or  Westlands",
        key="sc_search"
    ).strip().lower()

    has_role_col = "Role" in staff_df.columns
    has_unit_col = "Unit" in staff_df.columns

    # ── Build the name list to show in the selectbox ─────────────────
    # Always a plain list of real staff names — no unit headers mixed in.
    # Unit headers caused the "no selection" bug when Streamlit tried to
    # match a header string back to a staff record.

    if search_sc:
        # Filter by name, role, or unit
        mask = staff_df["Staff Name"].str.lower().str.contains(search_sc, na=False)
        if has_role_col:
            mask |= staff_df["Role"].str.lower().str.contains(search_sc, na=False)
        if has_unit_col:
            mask |= staff_df["Unit"].str.lower().str.contains(search_sc, na=False)
        filtered = staff_df[mask]
        if filtered.empty:
            st.warning(f"No staff match '{search_sc}'. Try a surname, role or branch name.")
            return None
        # Sort filtered results: show best matches first
        name_list = sorted(filtered["Staff Name"].tolist())
        label = f"Select from {len(name_list)} result{'s' if len(name_list)!=1 else ''}"
    else:
        # ── Two-level dropdown: Unit → Staff ────────────────────────
        sorted_df  = staff_df.sort_values(["Unit","Role","Staff Name"]) if has_unit_col else staff_df.sort_values("Staff Name")
        name_list  = sorted_df["Staff Name"].tolist()
        _ud_i      = st.session_state.get("user_data",{})
        _my_name   = _ud_i.get("full_name","")
        _sel_key   = "sc_selected_name"
        # Always default to the logged-in user's own scorecard
        _full_names = staff_df["Staff Name"].tolist()
        if _my_name and _my_name not in name_list and _my_name in _full_names:
            name_list = [_my_name] + name_list  # prepend self to list
        # Force reset to self on fresh page load (not on every rerun)
        if _sel_key not in st.session_state:
            st.session_state[_sel_key] = _my_name if _my_name in name_list else (name_list[0] if name_list else "")
        elif st.session_state[_sel_key] not in name_list:
            st.session_state[_sel_key] = _my_name if _my_name in name_list else (name_list[0] if name_list else "")

        if has_unit_col:
            _cur_sel = st.session_state.get(_sel_key, "")

            # ── Determine Category (Branch vs Head Office) ────────────
            # Category column tells us directly; fallback to Unit
            if "Category" in sorted_df.columns:
                _categories = sorted(sorted_df["Category"].dropna().unique().tolist())
            else:
                _categories = sorted(sorted_df["Unit"].apply(
                    lambda u: "Head Office" if str(u).strip() in ("Head Office","HO","") else "Branch"
                ).unique().tolist())

            # Find current person's category
            _cur_rows = sorted_df[sorted_df["Staff Name"] == _cur_sel]
            if len(_cur_rows):
                _cur_cat = (_cur_rows["Category"].iloc[0] if "Category" in _cur_rows.columns
                            else ("Head Office" if _cur_rows["Unit"].iloc[0] in ("Head Office","HO") else "Branch"))
            else:
                _cur_cat = _categories[0] if _categories else "Branch"

            col_cat, col_u, col_s = st.columns([1, 1, 2])

            sel_cat = col_cat.selectbox(
                f"Category",
                _categories,
                index=_categories.index(_cur_cat) if _cur_cat in _categories else 0,
                key="sc_cat_sel")

            # ── Filter to selected category ───────────────────────────
            if "Category" in sorted_df.columns:
                cat_df = sorted_df[sorted_df["Category"] == sel_cat]
            else:
                if sel_cat == "Head Office":
                    cat_df = sorted_df[sorted_df["Unit"].isin(["Head Office","HO",""])]
                else:
                    cat_df = sorted_df[~sorted_df["Unit"].isin(["Head Office","HO",""])]

            # ── For Head Office: group by Department (from staff register); for Branch: by Unit ──
            if sel_cat in ("Head Office","Executive","HO"):
                # Try to load Department mapping from staff register
                _dept_map = {}
                try:
                    _sr_reg = st.session_state.get("staff_registry")
                    if _sr_reg is not None and hasattr(_sr_reg,'iterrows') and len(_sr_reg) and "Department" in _sr_reg.columns:
                        for _, _srrow in _sr_reg.iterrows():
                            _sn_key = str(_srrow["Staff Name"]) if "Staff Name" in _srrow.index else ""
                            _dp_val = str(_srrow["Department"]) if "Department" in _srrow.index else ""
                            if _sn_key and _dp_val and _dp_val != "nan":
                                _dept_map[_sn_key] = _dp_val
                except: pass

                if _dept_map:
                    # Add Department to cat_df temporarily
                    cat_df = cat_df.copy()
                    cat_df["_Dept"] = cat_df["Staff Name"].map(_dept_map).fillna("Other")
                    cat_df["_Dept"] = cat_df["_Dept"].replace("nan","Other")
                    _unit_col_use = "_Dept"
                    _unit_label   = "Department"
                    ho_units = sorted([d for d in cat_df["_Dept"].dropna().unique() if d and d!="nan"])
                    ho_units_display = ["All Departments"] + ho_units
                elif "Department" in cat_df.columns and cat_df["Department"].dropna().nunique() > 1:
                    _unit_col_use = "Department"
                    _unit_label   = "Department"
                    ho_units = sorted(cat_df["Department"].dropna().unique().tolist())
                    ho_units_display = ["All Departments"] + ho_units
                elif "Role" in cat_df.columns:
                    # Fallback: group HO by Role (meaningful — ICT/Credit/Finance)
                    _unit_col_use = "Role"
                    _unit_label   = "Function"
                    ho_units = sorted(cat_df["Role"].dropna().unique().tolist())
                    ho_units_display = ["All HO"] + ho_units
                else:
                    _unit_col_use = "Unit"
                    _unit_label   = "Unit"
                    ho_units = ["Head Office"]
                    ho_units_display = ["Head Office"]
            else:
                _unit_col_use = "Unit"
                _unit_label   = "Branch"
                ho_units = sorted(cat_df["Unit"].dropna().unique().tolist())
                ho_units_display = ho_units

            # Find the unit of the current selection within this category
            _cur_cat_rows = cat_df[cat_df["Staff Name"] == _cur_sel]
            if len(_cur_cat_rows):
                _cur_unit_val = str(_cur_cat_rows[_unit_col_use].iloc[0])
            else:
                _cur_unit_val = ho_units_display[0] if ho_units_display else ""

            _unit_idx = 0
            if _cur_unit_val in ho_units_display:
                _unit_idx = ho_units_display.index(_cur_unit_val)
            elif ho_units_display and ho_units_display[0] == "All HO":
                _unit_idx = 0

            sel_unit_val = col_u.selectbox(
                f"{_unit_label} ({len(ho_units)})",
                ho_units_display,
                index=_unit_idx,
                key="sc_unit_sel")

            # ── Filter staff to selected unit ─────────────────────────
            if sel_unit_val in ("All HO","All Departments"):
                unit_df = cat_df.copy()
            elif _unit_col_use in cat_df.columns:
                unit_df = cat_df[cat_df[_unit_col_use] == sel_unit_val]
            else:
                unit_df = cat_df.copy()

            unit_names = unit_df["Staff Name"].tolist()

            def _lbl(r):
                nm   = r["Staff Name"]
                role = str(r.get("Role",""))[:28]
                bsc  = r.get("Final_BSC_Score", 0)
                bsc_str = f"{bsc:.2f}" if bsc else "—"
                return f"{nm}  ·  {role}  [{bsc_str}]"

            unit_labels   = [_lbl(r) for _, r in unit_df.iterrows()]
            label_to_name = {_lbl(r): r["Staff Name"] for _, r in unit_df.iterrows()}

            cur_in_unit   = _cur_sel if _cur_sel in unit_names else (unit_names[0] if unit_names else "")
            cur_label_idx = 0
            for _i, _l in enumerate(unit_labels):
                if label_to_name.get(_l) == cur_in_unit:
                    cur_label_idx = _i
                    break

            _disp_unit = sel_unit_val if sel_unit_val not in ("All HO","All Departments") else (
                "All Departments" if sel_cat in ("Head Office","Executive","HO") else "Head Office")
            sel_label = col_s.selectbox(
                f"Staff — {_disp_unit} ({len(unit_names)})",
                unit_labels,
                index=cur_label_idx,
                key="sc_staff_sel")

            sel = label_to_name.get(sel_label, cur_in_unit)
            st.session_state[_sel_key] = sel
        else:
            idx = name_list.index(st.session_state.get(_sel_key,"")) if st.session_state.get(_sel_key,"") in name_list else 0
            sel = st.selectbox(f"{len(name_list)} staff", name_list, index=idx, key="sc_sel_fb")
            st.session_state[_sel_key] = sel

    if search_sc:
        if not name_list:
            return None
        _ud_s  = st.session_state.get("user_data",{})
        _my_s  = _ud_s.get("full_name","")
        _def   = name_list.index(_my_s) if _my_s in name_list else 0
        sel    = st.selectbox(f"{len(name_list)} results", name_list, index=_def, key="sc_select")
        st.session_state["sc_selected_name"] = sel

    sel = st.session_state.get("sc_selected_name","") if not search_sc else sel
    if not sel: return None

    staff_row = staff_df[staff_df['Staff Name'] == sel]
    if len(staff_row) == 0:
        return
    staff_row = staff_row.iloc[0]

    # ── Header summary cards ──────────────────────────────────────────
    bsc    = staff_row.get('Final_BSC_Score', 0)
    rank   = staff_row.get('Overall_Rank', '—')
    rem    = staff_row.get('Performance_Remark', '—')
    unit   = staff_row.get('Unit', '—')
    role   = staff_row.get('Role', '—')
    sc_code= str(staff_row.get('Staff Code', ''))
    # Performance band colors from org_config
    try:
        from utils.core import score_to_band as _s2b
        _band_info = _s2b(float(bsc) if bsc else 0)
        bsc_clr = _band_info.get("color", "#888")
        clr_map = {b["label"]: b["color"] for b in
                   (__import__("utils.core", fromlist=["get_performance_bands"])
                    .get_performance_bands() or [])}
        if not clr_map:
            raise ValueError
    except:
        clr_map = {
            'Exceeded By Far': 'var(--brand-primary,#006B3F)', 'Exceeded': 'var(--brand-mid,#1D9E75)',
            'Met': '#F5A623', 'Partially Met': '#E67E22', 'Unmet': '#E24B4A',
        }
        bsc_clr = clr_map.get(rem, '#888')

    # Branch league badge
    _league_badge = ""
    try:
        from utils.core import get_all_branches as _gab_p
        _binfo = next((b for b in _gab_p() if b["name"]==unit), None)
        if _binfo:
            _lg = _binfo.get("league","")
            _lc = {"Premier":"var(--brand-primary,#006B3F)","Large":"#185FA5","Medium":"#7C3AED","New":"#D97706"}
            if _lg:
                _rk = _binfo.get("feb_2026_rank",0)
                _rk_s = f" · Rank #{_rk}" if _rk else ""
                _league_badge = (
                    f" <span style='background:{_lc.get(_lg,'#6B7280')};color:var(--color-background-primary);"
                    f"padding:1px 8px;border-radius:10px;font-size:9px;font-weight:700'>"
                    f"{_lg}</span><span style='color:var(--color-text-tertiary);font-size:10px'>{_rk_s}</span>")
    except: pass

    # Profile photo — show left of metrics
    try:
        from utils.core import photo_avatar_html
        _avatar = photo_avatar_html(sc_code, sel, size=60)
    except:
        _avatar = ""

    # Photo + name card
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:14px;padding:12px 16px;"
        f"background:var(--color-background-secondary);border-radius:10px;margin-bottom:10px'>"
        f"{_avatar}"
        f"<div>"
        f"<div style='font-size:16px;font-weight:700;color:var(--color-text-primary)'>{sel}</div>"
        f"<div style='font-size:12px;color:var(--color-text-secondary);margin-top:2px'>{role}  ·  {unit}{_league_badge}</div>"
        f"</div>"
        f"<div style='margin-left:auto;text-align:right'>"
        f"<div style='font-size:24px;font-weight:800;color:{bsc_clr}'>{bsc:.2f}</div>"
        f"<div style='font-size:10px;color:var(--color-text-tertiary)'>BSC / 5.0</div>"
        f"</div>"
        f"</div>", unsafe_allow_html=True)

    # ── Proposition head banner ──────────────────────────────────
    _prop_tag_bsc = get_user_proposition()
    if _prop_tag_bsc and str(ud.get("staff_code","")) == str(sc if "sc" in dir() else ""):
        try:
            import json as _pj2; from pathlib import Path as _pp2
            _pcfg_bsc = _pj2.loads((_pp2(__file__).parent.parent/"data"/"proposition_config.json").read_text())
            _pperf_bsc= _pj2.loads((_pp2(__file__).parent.parent/"data"/"proposition_performance.json").read_text())
            _pdata = _pperf_bsc.get(_prop_tag_bsc, {})
            _pname = _pcfg_bsc["propositions"].get(_prop_tag_bsc,{}).get("name","")
            _picon = _pcfg_bsc["propositions"].get(_prop_tag_bsc,{}).get("icon","🎯")
            _pscore= _pdata.get("proposition_score", 0)
            _pcolor= _pcfg_bsc["propositions"].get(_prop_tag_bsc,{}).get("color","#006B3F")
            st.markdown(
                f"<div style='background:{_pcolor}10;border:1.5px solid {_pcolor}40;"
                f"border-radius:10px;padding:10px 16px;margin-bottom:12px;"
                f"display:flex;align-items:center;gap:16px'>"
                f"<div style='font-size:28px'>{_picon}</div>"
                f"<div><div style='font-size:13px;font-weight:700;color:{_pcolor}'>"
                f"{_pname} Proposition Score</div>"
                f"<div style='font-size:24px;font-weight:800'>{_pscore:.2f} / 5.0</div>"
                f"<div style='font-size:11px;color:var(--color-text-tertiary)'>"
                f"Based on {len(_pdata.get('kpis',[]))} influence KPIs · "
                f"{_pdata.get('total_tagged_customers',0):,} tagged customers</div></div>"
                f"<div style='margin-left:auto'>"
                f"<a href='/Propositions' style='font-size:12px;color:{_pcolor}'>View full scorecard →</a>"
                f"</div></div>",
                unsafe_allow_html=True)
        except Exception: pass

    hc1, hc2, hc3, hc4 = st.columns(4)
    hc1.markdown(
        f"<div style='padding:12px;background:var(--brand-light,#E8F5EE);border-radius:8px;text-align:center'>"
        f"<div style='font-size:28px;font-weight:700;color:{bsc_clr}'>{bsc:.2f}</div>"
        f"<div style='font-size:10px;color:#666;margin-top:2px'>BSC Score / 5.0</div></div>",
        unsafe_allow_html=True)
    hc2.markdown(
        f"<div style='padding:12px;background:var(--color-background-secondary);"
        f"border-radius:8px;text-align:center'>"
        f"<div style='font-size:22px;font-weight:600'>#{rank}</div>"
        f"<div style='font-size:10px;color:#666;margin-top:2px'>Overall rank</div></div>",
        unsafe_allow_html=True)
    hc3.markdown(
        f"<div style='padding:12px;background:var(--color-background-secondary);"
        f"border-radius:8px;text-align:center'>"
        f"<div style='font-size:14px;font-weight:600;color:{bsc_clr}'>{rem}</div>"
        f"<div style='font-size:10px;color:#666;margin-top:2px'>Performance band</div></div>",
        unsafe_allow_html=True)
    hc4.markdown(
        f"<div style='padding:12px;background:var(--color-background-secondary);"
        f"border-radius:8px;text-align:center'>"
        f"<div style='font-size:12px;font-weight:600'>{unit}</div>"
        f"<div style='font-size:10px;color:#666;margin-top:2px'>{role}</div></div>",
        unsafe_allow_html=True)

    st.markdown("<div style='margin:12px 0'></div>", unsafe_allow_html=True)

    # ── Score scale legend ────────────────────────────────────────────
    _scale_labels = [
        ("1.0–1.9", "Below Expectations",   "#DC2626", "#FEF2F2"),
        ("2.0–2.4", "Needs Improvement",     "#EA580C", "#FFF7ED"),
        ("2.5–3.4", "Meets Expectations",    "#D97706", "#FFFBEB"),
        ("3.5–4.4", "Exceeds Expectations",  "#16A34A", "#F0FDF4"),
        ("4.5–5.0", "Outstanding",           "#0891B2", "#EFF6FF"),
    ]
    _legend_html = "<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px'>"
    for _rng, _lbl, _clr, _bg in _scale_labels:
        _active = any(float(_rng.split("–")[0]) <= bsc <= float(_rng.split("–")[1]) for _ in [1])
        _border = f"2px solid {_clr}" if _active else f"1px solid {_clr}40"
        _fw = "700" if _active else "400"
        _legend_html += (
            f"<div style='background:{_bg};border:{_border};border-radius:16px;"
            f"padding:4px 12px;font-size:11px;font-weight:{_fw};color:{_clr}'>"
            f"<b>{_rng}</b> {_lbl}</div>")
    _legend_html += "</div>"
    st.markdown(_legend_html, unsafe_allow_html=True)

    # ── KPI rows — filter by KPI Library role assignment ─────────────
    kpi_rows = df_kpi[df_kpi['Staff Name'] == sel].copy()
    if kpi_rows.empty:
        st.info("No KPI data found for this staff member.")
        return

    # Apply KPI Library filter — only show KPIs assigned to this role
    try:
        from utils.core import get_kpi_library, DEFAULT_ROLE_KPIS, DEFAULT_KPI_LIBRARY
        _kpi_lib   = get_kpi_library()
        _lib_active = set(_kpi_lib.get("active_kpis", []))
        _role_kpi_ids = set(_kpi_lib.get("role_kpis", DEFAULT_ROLE_KPIS).get(role, []))
        _kpi_weights  = _kpi_lib.get("kpi_weights", {})
        _pillar_weights = _kpi_lib.get("pillar_weights", {
            "Financial":0.40,"Customer Focus":0.25,
            "Operational Excellence":0.25,"People & Learning":0.10})

        # Build ID→KPI name map from library
        _id_to_name = {}
        _name_to_id = {}
        _name_to_weight = {}
        for _pil, _kpis in _kpi_lib.get("pillars", DEFAULT_KPI_LIBRARY).items():
            for _k in _kpis:
                _id_to_name[_k["id"]] = _k["name"]
                _name_to_id[_k["name"]] = _k["id"]
                _name_to_weight[_k["name"]] = _kpi_weights.get(
                    _k["id"], _k.get("default_weight", 0.10))

        # Filter kpi_rows to only KPIs in this role's assignment
        if _role_kpi_ids:
            # Get KPI names assigned to this role
            _assigned_names = {_id_to_name[i] for i in _role_kpi_ids if i in _id_to_name}
            if _assigned_names:
                _mask = kpi_rows['KPI'].isin(_assigned_names)
                if _mask.any():
                    kpi_rows = kpi_rows[_mask].copy()
            # NOTE: Do NOT override weights from library — actuals file has
            # the correct role-specific weights (e.g. 2026 BSC 12% PBT for BM).
            # Library weights are defaults only; the uploaded actuals are authoritative.
    except Exception:
        pass  # fallback: show all KPIs from data file

    # Remove rows where KPI name is the same as the Pillar name (artefacts)
    kpi_rows = kpi_rows[
        kpi_rows['KPI'].astype(str).str.strip() !=
        kpi_rows['Pillar'].astype(str).str.strip()
    ]

    # ── Normalize weights so they ALWAYS sum to 1.0 ────────────────
    # Prevents BSC showing "80%" or "115%" total weight
    _wt_raw = pd.to_numeric(kpi_rows['Weight'], errors='coerce').fillna(0)
    _wt_sum = _wt_raw.sum()
    if _wt_sum > 0 and abs(_wt_sum - 1.0) > 0.01:
        kpi_rows = kpi_rows.copy()
        kpi_rows['Weight'] = (_wt_raw / _wt_sum).round(4)

    PILLAR_ORDER = {'Financial': 0, 'Customer Focus': 1,
                    'Operational Excellence': 2, 'People & Learning': 3}
    kpi_rows['_p_ord'] = kpi_rows['Pillar'].map(PILLAR_ORDER).fillna(99)
    kpi_rows = kpi_rows.sort_values(['_p_ord', 'Weight'], ascending=[True, False])

    # Detect monthly columns present in the data
    month_cols = [c for c in kpi_rows.columns
                  if any(c.startswith(m) for m in
                         ['Jan','Feb','Mar','Apr','May','Jun',
                          'Jul','Aug','Sep','Oct','Nov','Dec'])
                  and 'Target' not in str(c) and 'target' not in str(c)]

    # Count consecutive rows per pillar for rowspan
    pillar_counts = {}
    for _, r in kpi_rows.iterrows():
        p = str(r.get('Pillar', ''))
        pillar_counts[p] = pillar_counts.get(p, 0) + 1

    def score_clr(s):
        if s >= 3.5:   return 'var(--brand-primary,#006B3F)'
        if s >= 3.0:   return 'var(--brand-mid,#1D9E75)'
        if s >= 2.5:   return '#F5A623'
        return '#E24B4A'

    def ach_clr(p):
        # Aligned to real bank scale: met=91%+, unmet=61-90%, poor=<61%
        if p >= 101: return 'var(--brand-primary,#006B3F)'   # exceeded
        if p >= 91:  return 'var(--brand-mid,#1D9E75)'   # met
        if p >= 61:  return '#F5A623'   # unmet but acceptable
        if p >= 31:  return '#F97316'   # significantly below
        return '#E24B4A'

    # Build HTML rows
    rows_html  = ''
    prev_pillar = None
    total_wt   = 0.0
    total_ws   = 0.0

    # Cascade is single source of truth for targets
    _casc_inst   = st.session_state.get("cascade_manager")
    # Patch stale instance — add missing methods as safe no-ops
    if _casc_inst is not None:
        if not callable(getattr(_casc_inst, "get_fixed_kpis", None)):
            _casc_inst.get_fixed_kpis  = lambda period="": []
        if not callable(getattr(_casc_inst, "get_fixed_value", None)):
            _casc_inst.get_fixed_value = lambda kpi="", period="": 0.0
        if not callable(getattr(_casc_inst, "get_bank_target", None)):
            _casc_inst.get_bank_target = lambda kpi="", period="": None
        if not callable(getattr(_casc_inst, "targets_locked", None)):
            _casc_inst.targets_locked  = lambda *a, **k: False
        if not hasattr(_casc_inst, "bank_targets"):
            _casc_inst.bank_targets    = {}
    _sel_sc      = str(staff_row.get("Staff Code",""))
    _sel_name    = str(staff_row.get("Staff Name", sel))
    _targets_live= False   # targets locked and confirmed?
    _casc_targets= {}      # {kpi: cascaded_target_amount}

    _fixed_kpis_set = set()  # KPIs locked bank-wide — always show on BSC

    # Detect MD — MD has no line manager, adopts bank targets directly
    _viewer_role = str(st.session_state.get("user_data",{}).get("role","")).strip()
    _sel_role    = str(staff_row.get("Role","")).strip()
    # Check against actual root of hierarchy — not hardcoded "Managing Director"
    try:
        from utils.core import get_root_roles as _grr
        _root_roles  = set(_grr())
    except:
        _root_roles  = {"Managing Director","Chief Executive & Managing Director"}
    _is_md_view  = (_sel_role in _root_roles or _viewer_role in _root_roles or
                    _sel_role == "Managing Director" or _viewer_role == "Managing Director")

    if _casc_inst and _sel_sc:
        try:
            _targets_live = _casc_inst.targets_locked(_sel_sc, get_fiscal_year())
        except: _targets_live = False

        # Always reload from disk to get latest saves
        try:
            _casc_inst.fixed_kpis   = _casc_inst._load_fixed()
            _casc_inst.bank_targets = _casc_inst._load_bank()
        except: pass

        # ── MD: load directly from bank_targets (no cascade needed) ──
        if _is_md_view:
            _bt_all = getattr(_casc_inst, "bank_targets", {}) or {}
            for _btk, _btv in _bt_all.items():
                # key format: "KPI Name|2026"
                if "|" in _btk:
                    _kpi_name, _bper = _btk.rsplit("|",1)
                    if _bper in (get_fiscal_year(),"2025"):
                        _tgt = _btv.get("target",0) if isinstance(_btv,dict) else float(_btv or 0)
                        if _tgt:
                            _casc_targets[_kpi_name] = float(_tgt)
            # Fixed KPIs also load for MD — safe call in case of stale object
            for _per in (get_fiscal_year(),"2025"):
                try:
                    _fkpis_md = _casc_inst.get_fixed_kpis(_per)
                except AttributeError:
                    _fkpis_md = []
                for kpi_fp in (_fkpis_md or []):
                    _fixed_kpis_set.add(kpi_fp)
                    if kpi_fp not in _casc_targets:
                        try:
                            _fv = _casc_inst.get_fixed_value(kpi_fp, _per)
                            if _fv: _casc_targets[kpi_fp] = float(_fv)
                        except: pass
            # If bank_targets still empty — use actuals as proxy baseline
            if not _casc_targets:
                _targets_live = False  # show "Set bank targets" prompt
            else:
                _targets_live = True

        else:
            # ── All other roles: load from cascade allocations ────────
            try:
                _given = _casc_inst.get_what_i_was_given(_sel_sc, _gfy(), _sel_name)
                for g in (_given or []):
                    if g.get("kpi") and g.get("amount"):
                        _casc_targets[g["kpi"]] = float(g["amount"])
            except: pass

            # Fixed KPIs always show even without cascade
            try:
                for _per in (_gfy(),"2025"):
                    try:
                        _fkpis_other = _casc_inst.get_fixed_kpis(_per)
                    except AttributeError:
                        _fkpis_other = []
                    for kpi_fp in (_fkpis_other or []):
                        if kpi_fp in _fixed_kpis_set: continue
                        _fixed_kpis_set.add(kpi_fp)
                        try:
                            _fv = _casc_inst.get_fixed_value(kpi_fp, _per)
                            if _fv:
                                _casc_targets[kpi_fp] = float(_fv)
                                continue
                        except: pass
                        try:
                            bt = _casc_inst.get_bank_target(kpi_fp, _per)
                            if bt and bt.get("target"):
                                _casc_targets[kpi_fp] = float(bt["target"])
                        except: pass
            except: pass

    if _targets_live:
        st.markdown(
            "<div style='padding:8px 14px;background:#F0FDF4;border:1px solid #BBF7D0;"
            "border-radius:8px;margin-bottom:10px;font-size:12px;color:#166534;"
            "display:flex;align-items:center;gap:8px'>"
            "🔒 <b>Targets confirmed and locked.</b> "
            "Scores and achievement calculated against agreed cascade targets.</div>",
            unsafe_allow_html=True)
    elif _casc_targets:
        st.markdown(
            "<div style='padding:8px 14px;background:#EFF6FF;border:1px solid #BFDBFE;"
            "border-radius:8px;margin-bottom:10px;font-size:12px;color:#1E40AF;"
            "display:flex;align-items:center;gap:8px'>"
            "⏳ <b>Targets cascaded — awaiting confirmation.</b> "
            "Targets shown are from the cascade. Scores activate once confirmed.</div>",
            unsafe_allow_html=True)
    elif _fixed_kpis_set:
        st.markdown(
            "<div style='padding:8px 14px;background:#FFFBEB;border:1px solid #FDE68A;"
            "border-radius:8px;margin-bottom:10px;font-size:12px;color:#92400E;"
            "display:flex;align-items:center;gap:8px'>"
            "🔒 <b>Bank-fixed targets active.</b> "
            f"<b>{len(_fixed_kpis_set)}</b> KPI(s) are set bank-wide and show automatically. "
            "Personal cascade targets not yet received — contact your line manager.</div>",
            unsafe_allow_html=True)
    else:
        if _is_md_view:
            st.markdown(
                "<div style='padding:8px 14px;background:#FEF3C7;border:1px solid #FDE68A;"
                "border-radius:8px;margin-bottom:10px;font-size:12px;color:#92400E;"
                "display:flex;align-items:center;gap:8px'>"
                "⚠️ <b>Bank targets not yet set.</b> "
                "As MD, go to <b>Target Cascade → Bank Targets</b> to set the bank-wide "
                "KPI targets. These will cascade to your BSC automatically.</div>",
                unsafe_allow_html=True)
        else:
            st.markdown(
                "<div style='padding:8px 14px;background:#FEF3C7;border:1px solid #FDE68A;"
                "border-radius:8px;margin-bottom:10px;font-size:12px;color:#92400E;"
                "display:flex;align-items:center;gap:8px'>"
                "⚠️ <b>No targets set yet.</b> "
                "Your line manager has not yet cascaded targets to you. "
                "Contact them or check Target Cascade → My Targets.</div>",
                unsafe_allow_html=True)

    for _, r in kpi_rows.iterrows():
        kpi    = str(r.get('KPI', '—'))
        pillar = str(r.get('Pillar', '—'))
        # Target: cascade is single source of truth
        # Use cascaded target if available; blank otherwise (ignore uploaded Annual Target)
        casc_tgt = _casc_targets.get(kpi, None)
        tgt = float(casc_tgt) if casc_tgt is not None else None  # None = not yet set
        act = float(pd.to_numeric(r.get('YTD_Actual',
                        r.get('Annual Actual', 0)), errors='coerce') or 0)
        wt  = float(pd.to_numeric(r.get('Weight', 0), errors='coerce') or 0)
        # Fixed KPIs: always show target and achievement regardless of cascade status
        # Variable KPIs: only when targets are locked and confirmed
        _is_fixed_kpi = kpi in _fixed_kpis_set
        # Scoring scale from org_config — fully configurable per bank
        try:
            from utils.core import bsc_score_from_pct as _bsc_score_fn
        except:
            def _bsc_score_fn(p, reverse=False):
                if p is None: return None
                if p > 130: return 5.0
                if p > 120: return 4.5
                if p > 110: return 4.0
                if p > 100: return 3.5
                if p >= 91: return 3.0
                if p >= 61: return 2.5
                if p >= 51: return 2.0
                if p >= 31: return 1.5
                return 1.0
        def _real_bsc_score(pct):
            return _bsc_score_fn(pct) if pct is not None else None

        _is_reverse = any(k in kpi for k in ("NPL","PAR","Cost-to-Income","Dormancy","Loss","Write"))

        if _is_fixed_kpi and tgt:
            pct = round((tgt / act * 100 if _is_reverse else act / tgt * 100), 1) if tgt and act else 0.0
            sc  = _real_bsc_score(pct) if _targets_live else None
        elif _targets_live and tgt:
            pct = round((tgt / act * 100 if _is_reverse else act / tgt * 100), 1) if tgt else 0.0
            sc  = _real_bsc_score(pct)
        elif tgt:
            pct = round((tgt / act * 100 if _is_reverse else act / tgt * 100), 1) if tgt else 0.0
            sc  = None  # cascaded but not yet confirmed
        else:
            sc  = None
            pct = None

        total_wt += wt
        total_ws += (sc * wt) if sc is not None else 0.0

        # Monthly actuals string
        monthly_vals = []
        for mc in month_cols[:3]:
            v = pd.to_numeric(r.get(mc, 0), errors='coerce') or 0
            monthly_vals.append(fmt_kpi_value(v, kpi, short=True))
        monthly_str = ' · '.join(monthly_vals) if monthly_vals else '—'

        # Colour helpers — handle None (pending) gracefully
        sc_c  = score_clr(sc)  if sc  is not None else "#D1D5DB"
        ac_c  = ach_clr(pct)   if pct is not None else "#D1D5DB"
        bar_w = int(min(100, max(0, pct))) if pct is not None else 0

        # Pillar cell — only emit on first row of each pillar group
        if pillar != prev_pillar:
            cnt = pillar_counts.get(pillar, 1)
            _p_bg  = {"Financial":"var(--brand-light,#E8F5EE)","Customer Focus":"#EFF6FF",
                      "Operational Excellence":"#F3E8FF"}.get(pillar,"#F9FAFB")
            _p_clr = {"Financial":"var(--brand-primary,#006B3F)","Customer Focus":"#185FA5",
                      "Operational Excellence":"#6B21A8"}.get(pillar,"#374151")
            _p_ico = {"Financial":"💰","Customer Focus":"👥",
                      "Operational Excellence":"⚙️"}.get(pillar,"")
            _p_short = {"Financial":"Fin","Customer Focus":"Cust",
                        "Operational Excellence":"Ops"}.get(pillar,pillar[:4])
            # Full pillar name split across lines, no rotation needed
            _p_lines = {"Financial":["💰","Fin"],
                        "Customer Focus":["👥","Cust","Focus"],
                        "Operational Excellence":["⚙️","Ops","Excel"]}.get(pillar,[_p_ico,pillar[:6]])
            _p_inner = "<br>".join(f"<span>{ln}</span>" for ln in _p_lines)
            pillar_td = (
                f"<td rowspan='{cnt}' style='"
                f"background:{_p_bg};font-weight:700;color:{_p_clr};"
                f"font-size:9px;text-align:center;vertical-align:middle;"
                f"padding:6px 4px;border-right:3px solid {_p_clr};"
                f"min-width:44px;max-width:52px;"
                f"position:sticky;left:0;z-index:1;line-height:1.4'>"
                f"{_p_inner}"
                f"</td>"
            )
            prev_pillar = pillar
        else:
            pillar_td = ''


        # Achievement bar cell — build without nested f-string quotes
        bar_bg   = '#EEEEEE'
        if pct is not None:
            pct_label = f"{pct:.1f}%"
            pct_clr   = ac_c
        else:
            pct_label = "⏳"
            pct_clr   = "#D1D5DB"
        ach_html = (
            "<div style='display:flex;align-items:center;gap:5px'>"
            f"<div style='width:48px;height:5px;background:{bar_bg};border-radius:3px;flex-shrink:0'>"
            f"<div style='width:{bar_w}%;height:100%;background:{pct_clr};border-radius:3px'></div>"
            "</div>"
            f"<span style='color:{pct_clr};font-weight:600;font-size:11px'>{pct_label}</span>"
            "</div>"
        )

        # Target display — use kpi-aware formatter (count vs KES vs %)
        if tgt is not None and _is_fixed_kpi:
            tgt_disp = (
                f"<span style='color:#92400E;font-weight:700'>"
                f"🔒 {fmt_kpi_value(tgt, kpi, short=True)}</span>")
        elif tgt is not None:
            tgt_disp = fmt_kpi_value(tgt, kpi, short=True)
        else:
            tgt_disp = "<span style='color:#D1D5DB;font-size:10px'>—</span>"

        # Score display
        if sc is not None:
            sc_disp = f"{sc:.2f}"
        elif _is_fixed_kpi and tgt is not None:
            # Fixed KPI: show amber badge — target locked bank-wide, score pending cascade
            sc_disp = ("<span style='background:#FDE68A;color:#92400E;font-size:9px;"
                       "padding:1px 5px;border-radius:3px;font-weight:700'>🔒 Fixed</span>")
        else:
            sc_disp = "<span style='color:#D1D5DB;font-size:10px'>⏳</span>"

        # Row background — amber tint for fixed KPIs
        row_style = "background:#FFFBEB" if _is_fixed_kpi else ""
        _kpi_bg   = "#FFFBEB" if _is_fixed_kpi else "var(--color-background-primary)"

        # KPI name — badge for fixed
        kpi_name_cell = (
            f"<td style='font-size:12px;padding:5px 8px;{row_style};position:sticky;left:52px;z-index:1;background:{_kpi_bg}'>"
            + (f"<span style='background:#FDE68A;color:#92400E;font-size:8px;"
               f"font-weight:700;padding:1px 4px;border-radius:3px;margin-right:4px'>"
               f"FIXED</span>" if _is_fixed_kpi else "")
            + f"{kpi}</td>")

        # MD stretch score — score against stretch target
        _stretch_sc_disp = "—"
        _full_sc_disp    = "—"
        _ud_local  = st.session_state.get("user_data", {})
        _rl_local  = str(_ud_local.get("role","")).lower()
        is_md      = (_ud_local.get("is_admin", False) or
                      any(k in _rl_local for k in ("managing director","md","ceo")))
        if is_md and tgt is not None:
            try:
                _casc_inst2 = st.session_state.get("cascade_manager")
                _bt2 = _casc_inst2.get_bank_target(kpi,_gfy()) if _casc_inst2 else None
                _st2 = float(_bt2.get("stretch_target",0)) if _bt2 else 0.0
                if _st2 and act:
                    _spct = act / _st2 * 100
                    _ssc  = bsc_score(_spct) if "bsc_score" in dir() else sc
                    _stretch_sc_disp = f"{_ssc:.2f}" if _ssc else "—"
            except: pass

        _extra_cols = (
            f"<td style='text-align:center;font-weight:700;color:var(--brand-mid,#1D9E75);font-size:11px;"
            f"background:rgba(29,158,117,0.06)'>{_stretch_sc_disp}</td>"
            f"<td style='text-align:center;font-size:11px;color:var(--color-text-tertiary)'>{_full_sc_disp}</td>"
            if is_md else ""
        )

        rows_html += (
            f"<tr style='{row_style}'>"
            + pillar_td
            + kpi_name_cell
            + f"<td style='text-align:center;font-size:11px;color:#555;{row_style}'>{wt*100:.0f}%</td>"
            + f"<td style='text-align:right;font-size:12px;padding:5px 8px;{row_style}'>{tgt_disp}</td>"
            + f"<td style='text-align:right;font-size:12px;font-weight:600;padding:5px 8px'>{fmt_kpi_value(act, kpi, short=True)}</td>"
            + f"<td style='padding:4px 8px'>{ach_html}</td>"
            + f"<td style='font-size:10px;color:#888;text-align:center'>{monthly_str}</td>"
            + f"<td style='text-align:center;font-weight:700;color:{sc_c};font-size:12px'>{sc_disp}</td>"
            + _extra_cols
            + "</tr>"
        )

    # Totals row
    rows_html += (
        "<tr style='background:var(--brand-light,#E8F5EE);border-top:2px solid var(--brand-primary,#006B3F)'>"
        "<td colspan='2' style='padding:8px;font-size:12px;font-weight:700;"
        "color:var(--brand-primary,#006B3F)'>Weighted BSC total</td>"
        f"<td style='text-align:center;font-weight:600'>{total_wt*100:.0f}%</td>"
        "<td colspan='3'></td>"
        "<td></td>"
        f"<td style='text-align:center;font-weight:700;color:{score_clr(bsc)};font-size:15px'>{bsc:.2f}</td>"
        "</tr>"
    )

    month_label = ' · '.join(month_cols[:3]) if month_cols else 'Monthly'

    # MD status for 3-col score columns
    _ud_h = st.session_state.get("user_data", {})
    _rl_h = str(_ud_h.get("role","")).lower()
    is_md = (_ud_h.get("is_admin", False) or
             any(k in _rl_h for k in ("managing director","md","ceo")))

    _score_ths = (
        "<th style='padding:9px 6px;min-width:52px;text-align:center;"
        "background:var(--brand-primary,#006B3F)'>BSC</th>"
        "<th style='padding:9px 6px;min-width:52px;text-align:center;"
        "background:var(--brand-secondary,#0F7A4B)'>Stretch</th>"
        "<th style='padding:9px 6px;min-width:60px;text-align:center;"
        "background:#185FA5'>Full</th>"
        if is_md else
        "<th style='padding:9px 6px;text-align:center;min-width:56px'>Score</th>"
    )

    table_html = (
        "<div style='overflow-x:auto;border-radius:8px;border:0.5px solid var(--color-border-tertiary);"
        "box-shadow:0 1px 4px rgba(0,0,0,0.06)'>"
        "<table style='width:100%;border-collapse:collapse;font-size:12px'>"
        "<thead>"
        "<tr style='background:var(--brand-primary,#006B3F);color:var(--color-background-primary)'>"
        "<th style='padding:9px 6px;min-width:72px;text-align:center;"
        "position:sticky;left:0;background:var(--brand-primary,#006B3F);z-index:3'>Pillar</th>"
        "<th style='padding:9px 8px;text-align:left;min-width:155px;"
        "position:sticky;left:72px;background:var(--brand-primary,#006B3F);z-index:3'>KPI</th>"
        "<th style='padding:9px 6px;text-align:center'>Wt</th>"
        "<th style='padding:9px 8px;text-align:right;min-width:88px'>Target</th>"
        "<th style='padding:9px 8px;text-align:right;min-width:88px'>YTD Actual</th>"
        "<th style='padding:9px 8px;text-align:center;min-width:110px'>Achievement</th>"
        f"<th style='padding:9px 6px;text-align:center;min-width:110px'>{month_label}</th>"
        + _score_ths
        + "</tr></thead>"
        + f"<tbody>{rows_html}</tbody>"
        + "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# GROUPED STAFF SELECTOR — HELPER
# ════════════════════════════════════════════════════════════════
def build_staff_selector(df, key_prefix="main"):
    """Searchable + browsable staff selector. Always returns a real staff name or None."""
    if df is None or (hasattr(df,'empty') and df.empty) or "Staff Name" not in df.columns:
        return None

    has_unit = "Unit" in df.columns
    has_role = "Role" in df.columns

    search_q = st.text_input(
        "🔍 Search by name, role or branch",
        placeholder="e.g. Kamau  or  Teller  or  Westlands",
        key=f"{key_prefix}_search"
    ).strip().lower()

    # Always build a PLAIN list of names — never mix in unit headers.
    # Unit headers caused the selector to return None because Streamlit
    # matched the header string instead of a staff name.
    if search_q:
        mask = df["Staff Name"].str.lower().str.contains(search_q, na=False)
        if has_role:
            mask |= df["Role"].str.lower().str.contains(search_q, na=False)
        if has_unit:
            mask |= df["Unit"].str.lower().str.contains(search_q, na=False)
        results = df[mask]
        if results.empty:
            st.warning(f"No staff match '{search_q}'. Try a surname, role or branch name.")
            return None
        name_list = sorted(results["Staff Name"].tolist())
        label = f"Select from {len(name_list)} result{'s' if len(name_list)!=1 else ''}"
    else:
        if has_unit:
            name_list = df.sort_values(["Unit","Staff Name"])["Staff Name"].tolist()
        else:
            name_list = df.sort_values("Staff Name")["Staff Name"].tolist()
        label = f"Select staff member ({len(name_list)} total)"

    if not name_list:
        return None
    # Default to logged-in user
    _ud2        = st.session_state.get("user_data", {})
    _my_name2   = _ud2.get("full_name", "")
    _def_idx2   = name_list.index(_my_name2) if _my_name2 in name_list else 0
    return st.selectbox(label, name_list, index=_def_idx2, key=f"{key_prefix}_sel")

# ════════════════════════════════════════════════════════════════
# PAGE HEADER
# ════════════════════════════════════════════════════════════════
st.markdown(
    "<div style=\'padding:16px 22px;background:var(--brand-primary,#006B3F);border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>Perform — BSC Performance Management</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Scorecard · Rankings · Individual view · Validation · Analytics · Leave</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
    unsafe_allow_html=True)

# ── Region filter in sidebar ──────────────────────────────────
if _has_region and len(filtered) > 0:
    all_regions = sorted(filtered["Region"].dropna().unique().tolist())
    if len(all_regions) > 1:
        sel_reg = st.sidebar.selectbox("Region", ["All"] + all_regions, key="reg_f")
        if sel_reg != "All":
            filtered = filtered[filtered["Region"] == sel_reg].copy()

# ════════════════════════════════════════════════════════════════
# TABS — AT THE TOP, ALWAYS VISIBLE
# ════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📊 My Scorecard",
    "🏆 Rankings",
    "👤 Individual view",
    "✅ Validation",
    "📈 Analytics",
    "📋 Staff register",
    "🏖️ Leave",
    "💡 Team insights",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — BSC SCORECARD
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    st.caption("Select any staff member to view their full BSC scorecard — KPIs grouped by pillar with achievement and score.")
    render_bsc_scorecard(filtered, df_proc)

# ════════════════════════════════════════════════════════════════
# TAB 2 — RANKINGS
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    # Quick summary row
    if len(filtered):
        rc1,rc2,rc3,rc4,rc5 = st.columns(5)
        rc1.metric("Staff in view",     len(filtered))
        rc2.metric("Avg BSC",           fmt_score(filtered["Final_BSC_Score"].mean()))
        rc3.metric("Exceeded",          int((filtered["Final_BSC_Score"]>=3.1).sum()))
        rc4.metric("Met (3.0)",         int(((filtered["Final_BSC_Score"]>=2.95)&(filtered["Final_BSC_Score"]<3.1)).sum()))
        rc5.metric("At risk (<2.5)",    int((filtered["Final_BSC_Score"]<2.5).sum()),
                   delta_color="inverse")

    # Filters
    st.markdown("<div style='margin:8px 0'>", unsafe_allow_html=True)
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        roles_opts = ["All roles"] + sorted(filtered["Role"].unique().tolist()) if _has_role else ["All roles"]
        sel_role = st.selectbox("Role", roles_opts, key="rank_role")
    with fc2:
        units_opts = ["All units"] + (sorted(filtered["Unit"].unique().tolist()) if _has_unit else [])
        sel_unit = st.selectbox("Unit", units_opts, key="rank_unit")
    with fc3:
        perf_opts = ["All","Exceeded By Far","Exceeded","Met","Partially Met","Unmet"]
        sel_perf = st.selectbox("Performance band", perf_opts, key="rank_perf")

    view = filtered.copy()
    if sel_role != "All roles": view = view[view["Role"] == sel_role]
    if sel_unit != "All units" and _has_unit: view = view[view["Unit"] == sel_unit]
    if sel_perf != "All": view = view[view["Performance_Remark"] == sel_perf]

    show_cols = [c for c in ["Overall_Rank","Staff Name","Role","Unit","Staff Status",
                               "Final_BSC_Score","Avg_Achievement_Pct","Performance_Remark","Percentile"]
                 if c in view.columns]
    disp = view[show_cols].copy()
    if "Final_BSC_Score"     in disp.columns: disp["Final_BSC_Score"]     = disp["Final_BSC_Score"].apply(fmt_score)
    if "Avg_Achievement_Pct" in disp.columns: disp["Avg_Achievement_Pct"] = disp["Avg_Achievement_Pct"].apply(fmt_pct)
    if "Percentile"          in disp.columns: disp["Percentile"]          = disp["Percentile"].apply(fmt_pct)
    disp.columns = [c.replace("_"," ") for c in disp.columns]
    disp = disp.rename(columns={"Avg Achievement Pct":"Avg Achievement %","Final BSC Score":"BSC Score"})

    def highlight_performance(v):
        colors = {"Exceeded By Far":"background-color:#C6EFCE;color:#276221",
                  "Exceeded":        "background-color:#DDEBF7;color:#1F497D",
                  "Met":             "background-color:#FFEB9C;color:#9C5700",
                  "Partially Met":   "background-color:#FFDDB3;color:#974706",
                  "Unmet":           "background-color:#FFC7CE;color:#9C0006"}
        return colors.get(str(v), "")

    st.dataframe(disp.style.map(highlight_performance, subset=["Performance Remark"]),
                 use_container_width=True, hide_index=True, height=420)

    # Charts
    c1, c2 = st.columns(2)
    with c1:
        top10 = view.assign(_or=view["Overall_Rank"].astype(float)).nsmallest(10,"_or")
        fig = px.bar(top10, x="Staff Name", y="Final_BSC_Score", color="Performance_Remark",
                     title="Top 10 performers", text="Final_BSC_Score",
                     color_discrete_map={"Exceeded By Far":"var(--brand-primary,#006B3F)","Exceeded":"#1D9E75",
                                         "Met":"#F5A623","Partially Met":"#E67E22","Unmet":"#E24B4A"})
        fig.update_traces(textposition="outside", texttemplate="%{y:.2f}")
        fig.update_layout(showlegend=False, xaxis_tickangle=-30, height=320,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        dist = view["Performance_Remark"].value_counts().reset_index()
        dist.columns = ["Status","Count"]
        fig2 = px.pie(dist, names="Status", values="Count", title="Performance distribution",
                      color="Status",
                      color_discrete_map={"Exceeded By Far":"var(--brand-primary,#006B3F)","Exceeded":"#1D9E75",
                                          "Met":"#F5A623","Partially Met":"#E67E22","Unmet":"#E24B4A"})
        fig2.update_layout(height=320, legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig2, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 3 — INDIVIDUAL VIEW
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.caption("Grouped by unit · 🟢 Exceeded · 🟡 Met/Exceeded · 🔴 Below target")
    selected = build_staff_selector(filtered, "ind")

    if selected:
        sel_rows = filtered[filtered["Staff Name"] == selected]
        if sel_rows.empty:
            st.warning("Staff member not found in current view.")
            st.stop()
        row  = sel_rows.iloc[0]
        kpis = df_proc[df_proc["Staff Name"] == selected] if not df_proc.empty else pd.DataFrame()

        # ── Header card ──────────────────────────────────────
        status = row.get("Performance_Remark","—")
        bsc    = row.get("Final_BSC_Score", 0)
        clr_map = {"Exceeded By Far":"var(--brand-primary,#006B3F)","Exceeded":"var(--brand-mid,#1D9E75)",
                   "Met":"#F5A623","Partially Met":"#E67E22","Unmet":"#E24B4A"}
        bsc_clr = clr_map.get(status,"#888")
        remark_detail = {
            "Exceeded By Far":"Outstanding performance — significantly above target across most KPIs.",
            "Exceeded":       "Strong performance — above target in the majority of KPIs.",
            "Met":            "Performance on target — meeting expectations across all pillars.",
            "Partially Met":  "Below target in key areas — a focused improvement plan is recommended.",
            "Unmet":          "Significantly below target — immediate management intervention required.",
        }.get(status,"")

        st.markdown(
            f"<div style='padding:14px 18px;background:{bsc_clr}22;"
            f"border-left:5px solid {bsc_clr};border-radius:6px;margin-bottom:12px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<div><span style='font-size:22px;font-weight:700;color:{bsc_clr}'>{bsc:.2f}</span>"
            f"<span style='color:#666;font-size:13px;margin-left:8px'>/ 5.0  ·  {status}</span></div>"
            f"<div style='text-align:right;font-size:12px;color:#555'>"
            f"Rank #{row.get('Overall_Rank','—')}  ·  {row.get('Role','')}  ·  {row.get('Unit','')}"
            f"</div></div>"
            f"<div style='font-size:12px;color:#555;margin-top:4px'>{remark_detail}</div>"
            f"</div>", unsafe_allow_html=True)

        # ── 5 metrics ────────────────────────────────────────
        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("BSC Score",       fmt_score(bsc))
        m2.metric("Overall rank",    f"#{row.get('Overall_Rank','—')}")
        m3.metric("Role rank",       f"#{row.get('Role_Rank','—')} / {row.get('Role_Total','—')}")
        m4.metric("Avg achievement", fmt_pct(row.get("Avg_Achievement_Pct",0)))
        m5.metric("Percentile",      f"{row.get('Percentile',0):.0f}th")

        if row.get("Staff Status","") in ("New","New 2026"):
            st.info("🆕 New staff — may be on probation. Confirm status in Staff Register tab.")

        # ── Validation badge ──────────────────────────────────
        period = datetime.now().strftime("%b %Y")
        if vm:
            existing_val = vm.get(selected, period)
            if existing_val:
                st.success(f"✅ Validated by **{existing_val['manager']}** on "
                           f"{existing_val['validated_at'][:10]} — {existing_val['status']}")

        st.markdown("---")
        col_a, col_b = st.columns(2)

        # ── Monthly trend ─────────────────────────────────────
        with col_a:
            if not kpis.empty and active_months:
                monthly_trend = []
                for col in active_months:
                    if col in kpis.columns:
                        dt = parse_month_column(col)
                        label = dt.strftime("%b %Y") if dt else str(col)
                        month_rows = kpis.copy()
                        month_rows["_m_actual"] = month_rows[col]
                        month_ws = []
                        for _, kr in month_rows.iterrows():
                            t = kr.get("Annual Target", np.nan)
                            a = kr.get("_m_actual", 0)
                            w = kr.get("Weight", 0)
                            kpi_name = str(kr.get("KPI","")).upper()
                            rev = any(x in kpi_name for x in ["PAR","NPL","DELINQUENCY","COST","EXPENSE"])
                            if pd.isna(t) or t == 0: ach = np.nan
                            elif rev: ach = max(0, min(1.5, t/a)) if a > 0 else 0
                            else: ach = max(0, min(1.5, a/t))
                            if pd.isna(ach): s = np.nan
                            elif ach < 0.30: s=1.0
                            elif ach<=0.50:  s=1.5
                            elif ach<=0.60:  s=2.0
                            elif ach<=0.90:  s=2.5
                            elif ach<=1.00:  s=3.0
                            elif ach<=1.10:  s=3.5
                            elif ach<=1.20:  s=4.0
                            elif ach<=1.30:  s=4.5
                            else:            s=5.0
                            month_ws.append(s * w if pd.notna(s) else 0)
                        monthly_trend.append({"Month": label, "Weighted Score": round(sum(month_ws),2)})

                if monthly_trend:
                    mdf = pd.DataFrame(monthly_trend)
                    fig_line = px.line(mdf, x="Month", y="Weighted Score",
                                       title="Monthly BSC trend", markers=True,
                                       color_discrete_sequence=["var(--brand-primary,#006B3F)"])
                    fig_line.add_hline(y=3.0, line_dash="dash", line_color="#F5A623",
                                       annotation_text="Target 3.0")
                    fig_line.update_traces(marker=dict(size=10))
                    fig_line.update_layout(height=260, yaxis_range=[0,5.5],
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_line, use_container_width=True)

        # ── Pillar radar ──────────────────────────────────────
        with col_b:
            if not kpis.empty and "Pillar" in kpis.columns and kpis["Pillar"].nunique() > 1:
                ps = kpis.groupby("Pillar")["Weighted_Score"].sum().reset_index()
                fig_r = go.Figure(go.Scatterpolar(
                    r=ps["Weighted_Score"], theta=ps["Pillar"],
                    fill="toself", fillcolor="rgba(0,107,63,0.15)",
                    line=dict(color="var(--brand-primary,#006B3F)", width=2)))
                fig_r.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0,2])),
                    title="Pillar scores", height=260,
                    paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_r, use_container_width=True)

        # ── Performance insights ──────────────────────────────
        if not kpis.empty:
            st.markdown("#### Performance insights")
            insights = get_kpi_insights(kpis)
            render_insight_card(insights)

            # ── KPI breakdown ────────────────────────────────
            st.markdown("#### KPI detail")
            pillar_opts = ["All pillars"] + (sorted(kpis["Pillar"].unique().tolist()) if "Pillar" in kpis.columns else [])
            sel_pillar = st.selectbox("Filter by pillar", pillar_opts, key="kpi_pillar_ind")
            kpi_view = kpis if sel_pillar == "All pillars" else kpis[kpis["Pillar"] == sel_pillar]

            kpi_disp = kpi_view[["KPI","Pillar","Annual Target","YTD_Actual",
                                  "Percent_Achieved","Score","Weight","Weighted_Score"]].copy()
            kpi_disp["Annual Target"]    = kpi_disp["Annual Target"].apply(fmt_num)
            kpi_disp["YTD_Actual"]       = kpi_disp["YTD_Actual"].apply(fmt_num)
            kpi_disp["Percent_Achieved"] = kpi_disp["Percent_Achieved"].apply(fmt_pct)
            kpi_disp["Weight"]           = kpi_disp["Weight"].apply(lambda x: f"{x*100:.0f}%")
            kpi_disp["Score"]            = kpi_disp["Score"].apply(fmt_score)
            kpi_disp.columns = ["KPI","Pillar","Annual Target","YTD Actual","Achievement %","Score","Weight","Wtd Score"]

            # Export scorecard
            try:
                import io as _io
                _exp_buf = _io.BytesIO()
                with __import__("pandas").ExcelWriter(_exp_buf, engine="openpyxl") as _xw:
                    kpi_disp.to_excel(_xw, sheet_name="Scorecard", index=False)
                _exp_buf.seek(0)
                st.download_button(
                    "📥 Export scorecard",
                    data=_exp_buf.getvalue(),
                    file_name=f"BSC_{_sel_name.replace(' ','_')}_{get_fiscal_year()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="scorecard_export_btn")
            except Exception: pass

            def color_score_cell(v):
                try:
                    s = float(v)
                    if s >= 4:   return "background-color:#C6EFCE;color:#276221"
                    elif s >= 3: return "background-color:#FFEB9C;color:#9C5700"
                    elif s >= 2: return "background-color:#FFDDB3;color:#974706"
                    else:        return "background-color:#FFC7CE;color:#9C0006"
                except: return ""

            st.dataframe(kpi_disp.style.map(color_score_cell, subset=["Score"]),
                         use_container_width=True, hide_index=True)
    else:
        st.info("Use the search box above or select a staff member from the grouped dropdown.")

# ════════════════════════════════════════════════════════════════
# TAB 4 — VALIDATION
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Performance validation")
    st.caption("Managers review and sign off on staff performance for each period.")

    val_role = str(ud.get('role','')).lower()
    if val_role not in ('admin','director','manager','branch manager','department head'):
        st.info("Validation is available to managers and above. Contact your manager to validate your performance.")
    else:
        period = datetime.now().strftime("%b %Y")
        val_staff = sorted(filtered["Staff Name"].tolist()) if len(filtered) > 0 and "Staff Name" in filtered.columns else [] if len(filtered) > 0 and "Staff Name" in filtered.columns else []
        val_sel = st.selectbox("Select staff to validate", val_staff, key="val_sel")

        if val_sel:
            vrow = filtered[filtered['Staff Name'] == val_sel].iloc[0]
            existing = vm.get(val_sel, period)

            c1, c2, c3 = st.columns(3)
            c1.metric("BSC Score",   fmt_score(vrow['Final_BSC_Score']))
            c2.metric("Performance", vrow['Performance_Remark'])
            c3.metric("Percentile",  f"{vrow['Percentile']:.0f}th")

            if existing and not st.session_state.get('revalidate'):
                st.success(f"Already validated: **{existing['status']}** by {existing['manager']} on {existing['validated_at'][:10]}")
                st.write("**Action plan:**", existing.get('action_plan','—'))
                st.write("**Comments:**",    existing.get('comments','—'))
                if st.button("Re-validate", key="reval_btn"):
                    st.session_state['revalidate'] = True
                    st.cache_data.clear()
                    st.rerun()
            else:
                with st.form("validation_form"):
                    vstatus = st.selectbox("Validation status",
                        ["Confirmed","Partially Confirmed","Requires Review","Disputed"])
                    action_plan = st.text_area("Action plan / next steps",
                        value=existing.get('action_plan','') if existing else '')
                    comments = st.text_area("Comments",
                        value=existing.get('comments','') if existing else '')
                    if st.form_submit_button("Submit validation", type="primary"):
                        vm.validate(uname, val_sel, period, vstatus, action_plan, comments)
                        audit_log("VALIDATE", uname, f"{val_sel} | {period} | {vstatus}")
                        st.success(f"Validation submitted for {val_sel}!")
                        st.session_state.pop('revalidate', None)
                        st.cache_data.clear()
                        st.rerun()

        st.markdown("---")
        st.subheader(f"Validation summary — {period}")
        val_rows = []
        for name in sorted(filtered["Staff Name"].tolist()) if len(filtered) > 0 and "Staff Name" in filtered.columns else [] if len(filtered) > 0 and "Staff Name" in filtered.columns else []:
            v = vm.get(name, period)
            sc = filtered[filtered['Staff Name']==name]['Final_BSC_Score'].values[0]
            val_rows.append({
                "Staff": name,
                "BSC Score": fmt_score(sc),
                "Status": v['status'] if v else "⏳ Pending",
                "Validated by": v['manager'] if v else "—",
                "Date": v['validated_at'][:10] if v else "—",
            })
        if val_rows:
            vdf = pd.DataFrame(val_rows)
            def hl_val(v):
                if 'Confirmed' in str(v): return 'background-color:#C1E1C1'
                if 'Pending'   in str(v): return 'background-color:#FFE4B5'
                if 'Disputed'  in str(v): return 'background-color:#FFB6C1'
                return ''
            st.dataframe(vdf.style.map(hl_val, subset=['Status']),
                         use_container_width=True, hide_index=True)
            done  = sum(1 for r in val_rows if '⏳' not in r['Status'])
            total = len(val_rows)
            st.progress(done/total if total else 0, text=f"Validated: {done}/{total}")

# ════════════════════════════════════════════════════════════════
# TAB 5 — ANALYTICS
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Analytics dashboard")
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Staff in view",     len(filtered))
    m2.metric("Avg BSC score",     fmt_score(filtered['Final_BSC_Score'].mean()))
    m3.metric("High performers",   int((filtered['Final_BSC_Score'] >= 3.5).sum()))
    m4.metric("Needs improvement", int((filtered['Final_BSC_Score'] < 2.5).sum()))

    c1, c2 = st.columns(2)
    with c1:
        fig_h = px.histogram(filtered, x='Final_BSC_Score', nbins=20,
                             title='Score distribution', color_discrete_sequence=['#2980B9'])
        fig_h.add_vline(x=3.0, line_dash='dash', line_color='orange', annotation_text='Target (3.0)')
        fig_h.update_layout(height=320)
        st.plotly_chart(fig_h, use_container_width=True)
    with c2:
        if 'Unit' in filtered.columns and filtered['Unit'].nunique() > 1:
            ua = filtered.groupby('Unit')['Final_BSC_Score'].mean().sort_values(ascending=False).reset_index()
            fig_u = px.bar(ua, x='Final_BSC_Score', y='Unit', orientation='h',
                           title='Average score by unit', color='Final_BSC_Score',
                           color_continuous_scale='RdYlGn', range_color=[1,5])
            fig_u.update_layout(height=320, showlegend=False)
            st.plotly_chart(fig_u, use_container_width=True)

    # Score spread by role, split by Head Office vs Branch
    if 'Role' in filtered.columns and filtered['Role'].nunique() > 1:
        cat_col = 'Category' if 'Category' in filtered.columns else None
        has_cats = cat_col and filtered[cat_col].nunique() > 1

        if has_cats:
            categories = sorted(filtered[cat_col].unique().tolist())
            cat_tabs = st.tabs([f"📍 {c}" for c in categories])
            for ct, cat in zip(cat_tabs, categories):
                with ct:
                    cat_data = filtered[filtered[cat_col] == cat]
                    if cat_data['Role'].nunique() > 1:
                        fig_box = px.box(cat_data, x='Role', y='Final_BSC_Score',
                                         title=f'Score spread by role — {cat}', color='Role')
                        fig_box.add_hline(y=3.0, line_dash='dash', line_color='orange',
                                          annotation_text='Target')
                        fig_box.update_layout(showlegend=False, xaxis_tickangle=-25, height=360)
                        st.plotly_chart(fig_box, use_container_width=True)

                        role_avg = cat_data.groupby('Role')['Final_BSC_Score'].agg(
                            ['mean','count','min','max']).round(2).reset_index()
                        role_avg.columns = ['Role','Avg Score','# Staff','Min','Max']
                        st.dataframe(role_avg, use_container_width=True, hide_index=True)
                    else:
                        st.info(f"Only one role in {cat} — no spread chart needed.")
        else:
            fig_box = px.box(filtered, x='Role', y='Final_BSC_Score',
                             title='Score spread by role', color='Role')
            fig_box.add_hline(y=3.0, line_dash='dash', line_color='orange', annotation_text='Target')
            fig_box.update_layout(showlegend=False, xaxis_tickangle=-20, height=320)
            st.plotly_chart(fig_box, use_container_width=True)

    if 'Pillar' in df_proc.columns:
        pa = df_proc.groupby('Pillar')['Weighted_Score'].mean().reset_index()
        fig_p = px.bar(pa, x='Pillar', y='Weighted_Score',
                       title='Average weighted score by pillar', color='Pillar')
        fig_p.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig_p, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 6 — STAFF REGISTER
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Staff register")
    st.caption("Live view of all staff in the system — probation, transfers, and employment status.")

    reg = st.session_state.get('staff_registry', pd.DataFrame())

    if reg is None or (hasattr(reg,'empty') and reg.empty) or (isinstance(reg,dict) and not reg):
        st.info("No staff registry data found. Upload a file that includes 'Hire Date', 'Staff Status', and 'Email' columns (e.g. your Sheet1).")
    else:
        # Build display table
        # staff_registry is a DataFrame (from pd.read_excel in app.py)
        if isinstance(reg, dict):
            reg_df = pd.DataFrame(reg.values()) if reg else pd.DataFrame()
        else:
            reg_df = reg.copy()

        # Add BSC score column from staff_scores
        if "Staff Code" not in reg_df.columns and "Staff Name" in reg_df.columns:
            reg_df["Staff Code"] = ""
        if "Staff Code" in reg_df.columns:
            sc_map = {}
            rm_map = {}
            for _, _sr in staff_scores.iterrows():
                _sc = str(_sr.get("Staff Code",""))
                sc_map[_sc] = fmt_score(_sr.get("Final_BSC_Score",0))
                rm_map[_sc] = _sr.get("Performance_Remark","—")
            reg_df["BSC Score"]   = reg_df["Staff Code"].astype(str).map(sc_map).fillna("—")
            reg_df["Performance"] = reg_df["Staff Code"].astype(str).map(rm_map).fillna("—")

        # Normalise column names for display
        _rename = {"Staff Name":"Name","Employment Status":"Status",
                   "Hire Date Str":"Hire Date","Date of Employment":"Hire Date"}
        reg_df = reg_df.rename(columns={k:v for k,v in _rename.items() if k in reg_df.columns})
        if "Status" not in reg_df.columns:
            reg_df["Status"] = "Existing"

        # Filters
        fr1, fr2, fr3 = st.columns(3)
        with fr1:
            status_opts = ['All statuses'] + sorted(reg_df['Status'].unique().tolist())
            sel_status = st.selectbox("Employment status", status_opts, key="reg_status")
        with fr2:
            unit_opts = ['All units'] + sorted(reg_df['Unit'].dropna().unique().tolist())
            sel_runit = st.selectbox("Unit / Branch", unit_opts, key="reg_unit")
        with fr3:
            search = st.text_input("Search name or code", key="reg_search", placeholder="Type to search...")

        reg_view = reg_df.copy()
        if sel_status != 'All statuses': reg_view = reg_view[reg_view['Status'] == sel_status]
        if sel_runit  != 'All units':    reg_view = reg_view[reg_view['Unit']   == sel_runit]
        if search.strip():
            s = search.strip().lower()
            reg_view = reg_view[
                reg_view['Name'].str.lower().str.contains(s, na=False) |
                reg_view['Staff Code'].str.lower().str.contains(s, na=False)]

        # Colour status column
        def hl_status(v):
            if 'Probation' in str(v): return 'background-color:#FFF3CD;color:#856404'
            if v == 'Confirmed':      return 'background-color:#D4EDDA;color:#155724'
            if v == 'New':            return 'background-color:#CCE5FF;color:#004085'
            return ''
        def hl_perf(v):
            return highlight_performance(v)

        st.dataframe(
            reg_view.style
                .map(hl_status,   subset=['Status'])
                .map(hl_perf,     subset=['Performance']),
            use_container_width=True, hide_index=True)

        # Summary cards
        st.markdown("---")
        probation_count  = reg_df['Status'].str.contains('Probation', na=False).sum()
        confirmed_count  = (reg_df['Status'] == 'Confirmed').sum()
        new_count        = (reg_df['Status'] == 'New').sum()
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total staff", len(reg_df))
        sc2.metric("On probation", int(probation_count))
        sc3.metric("Confirmed", int(confirmed_count))
        sc4.metric("New (no hire date)", int(new_count))

        # ── TRANSFERS ────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Record a transfer")
        st.caption("When a staff member moves between branches or units, record it here. This updates their unit and logs the movement.")

        transfer_file = DATA_DIR / "transfers.json"
        if not transfer_file.exists(): transfer_file.write_text("[]")
        try:
            transfers = json.loads(transfer_file.read_text())
            if not isinstance(transfers, list): transfers = []
        except: transfers = []

        with st.form("transfer_form"):
            tc1, tc2 = st.columns(2)
            with tc1:
                t_code = st.text_input("Staff code", placeholder="e.g. 300130")
                # Auto-show name
                t_name = reg.get(t_code.strip(), {}).get('Staff Name', '') if t_code.strip() in reg else ''
                if t_name: st.caption(f"Staff: **{t_name}**")
                t_from = st.text_input("Transferring FROM (current unit)",
                    value=reg.get(clean_code(t_code), {}).get('Unit','') if clean_code(t_code) in reg else '')
            with tc2:
                t_to   = st.text_input("Transferring TO (new unit)")
                t_date: date = st.date_input("Effective date", value=datetime.now().date())  # type: ignore[assignment]
                t_reason = st.selectbox("Reason", ["Branch Transfer","Department Transfer",
                                                     "Promotion","Role Change","Secondment","Other"])
            t_notes = st.text_area("Notes (optional)", height=70)
            if st.form_submit_button("📋 Record transfer", type="primary"):
                if t_code.strip() and t_to.strip():
                    entry = {
                        "staff_code": t_code.strip(), "staff_name": t_name,
                        "from_unit": t_from, "to_unit": t_to,
                        "effective_date": str(t_date), "reason": t_reason,
                        "notes": t_notes,
                        "recorded_by": st.session_state.get('username',''),
                        "recorded_at": datetime.now().isoformat(),
                    }
                    transfers.append(entry)
                    transfer_file.write_text(json.dumps(transfers, indent=2))
                    audit_log("TRANSFER", st.session_state.get('username',''),
                              f"{t_code} from {t_from} to {t_to} ({t_reason})")
                    st.success(f"Transfer recorded for {t_name or t_code}!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Staff code and destination unit are required.")

        # Transfer history
        if transfers:
            st.markdown("#### Transfer history")
            t_df = pd.DataFrame(reversed(transfers))
            st.dataframe(t_df, use_container_width=True, hide_index=True)

        # ── PROBATION TRACKER ────────────────────────────────────────────
        prob_staff = reg_df[reg_df['Status'].str.contains('Probation', na=False)].copy()
        if len(prob_staff):
            st.markdown("---")
            st.subheader(f"⚠️ Probation tracker ({len(prob_staff)} staff)")
            st.caption("Staff currently within their 6-month probation window.")
            st.dataframe(
                prob_staff[['Staff Code','Name','Role','Unit','Hire Date','Status','BSC Score','Performance']]
                    .style.map(hl_status, subset=['Status']),
                use_container_width=True, hide_index=True)
            st.info("💡 Probation sign-off: Go to the Validation tab to formally confirm or flag any probationary staff.")

# ════════════════════════════════════════════════════════════════
# TAB 7 — LEAVE
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Leave management")
    st.caption("Record staff leave, suppress notifications, and apply performance compensation for extended absences.")

    leave_role  = str(ud.get('role','')).lower()
    can_approve = leave_role in ('admin','director','manager','branch manager',
                                  'department head','head','chief','area manager')
    # Everyone can apply for their own leave; managers can also record others'
    my_staff_code = str(ud.get('staff_code',''))
    my_full_name  = str(ud.get('full_name',''))

    # ── On leave right now — always visible at top ─────────────────
    active_now = lm.get_active_leave()
    if active_now:
        st.error(f"🔴 **{len(active_now)} staff currently on leave** — notifications suppressed")
        for r in active_now:
            end_d = datetime.strptime(r['end_date'], "%Y-%m-%d").date()
            days_left = (end_d - datetime.now().date()).days
            col1, col2, col3 = st.columns([2,2,1])
            col1.markdown(f"**{r['staff_name']}** — {r['leave_type']}")
            col2.markdown(f"Returns: {r['end_date']}  ({days_left}d remaining)")
            col3.markdown(f"{'⚠️ Affects score' if r['affects_perf'] else '✅ No impact'}")
        st.markdown("---")

    # ── Two sub-sections ───────────────────────────────────────────
    lv1, lv2, lv3 = st.tabs(["📋 Record Leave", "📊 Leave Overview", "⚖️ Performance Compensation"])

    with lv1:
        _lv_subtabs = st.tabs(["📝 Apply for leave", "👔 Record for staff"] if can_approve else ["📝 Apply for leave"])

        # ── Self-service leave application (all staff) ────────────
        with _lv_subtabs[0]:
            st.markdown(
                f"<div style='background:var(--color-background-secondary);"
                f"border-radius:10px;padding:12px 16px;margin-bottom:14px'>"
                f"<div style='font-size:13px;font-weight:500;color:var(--color-text-primary)'>"
                f"Applying as: {my_full_name}</div>"
                f"<div style='font-size:11px;color:var(--color-text-secondary)'>"
                f"Staff code: {my_staff_code}</div></div>",
                unsafe_allow_html=True)

            # Show own active leave
            if my_staff_code and lm.is_on_leave(my_staff_code):
                _my_active = lm.get_active_leave(my_staff_code)
                if _my_active:
                    st.warning(f"⚠️ You are currently on **{_my_active[0]['leave_type']}** "
                               f"until {_my_active[0]['end_date']}")

            with st.form("self_leave_form"):
                _sl1, _sl2 = st.columns(2)
                with _sl1:
                    _s_ltype = st.selectbox("Leave type", list(LEAVE_TYPES.keys()), key="sl_type")
                    _s_start: date = st.date_input("Start date", value=datetime.now().date(), key="sl_start")  # type: ignore
                with _sl2:
                    _default_days = LEAVE_TYPES.get(_s_ltype, {}).get('days_entitled', 21) or 21
                    _s_end  = st.date_input("End date",
                        value=datetime.now().date() + timedelta(days=_default_days), key="sl_end")
                    _s_rsn  = st.text_area("Reason / notes", height=68, key="sl_reason")

                # Live impact preview
                _lt_info = LEAVE_TYPES.get(_s_ltype, {})
                _comp_lbl= COMPENSATION_LABELS.get(_lt_info.get('compensation'), '')
                if _lt_info.get('affects_performance'):
                    st.warning(f"⚠️ Performance impact: {_comp_lbl}")
                else:
                    st.success(f"✅ No performance impact")

                if st.form_submit_button("📨 Submit leave request", type="primary"):
                    if not my_staff_code:
                        st.error("Could not identify your staff code. Please contact HR.")
                    elif _s_start > _s_end:
                        st.error("End date must be after start date.")
                    else:
                        _rec = lm.add_leave(
                            my_staff_code, my_full_name, _s_ltype,
                            _s_start, _s_end, _s_rsn,
                            approved_by="Self-applied", notify_suppress=True)
                        audit_log("LEAVE_APPLIED", uname,
                                  f"{my_full_name} | {_s_ltype} | {_s_start} to {_s_end}")
                        st.success(f"✅ Leave request submitted — {_rec['days']} days. "
                                   f"Your manager will be notified.")
                        st.cache_data.clear()
                        st.rerun()

        # ── Manager: record leave for any staff ───────────────────
        if can_approve:
            with _lv_subtabs[1]:
                _sr_reg = st.session_state.get('staff_registry')

                lv_code = st.text_input("Staff code", placeholder="e.g. 300130", key="lv_code")
                lv_clean = clean_code(lv_code) if lv_code.strip() else ""

                # Lookup from DataFrame registry
                lv_name = ""
                lv_role = ""
                lv_unit = ""
                if lv_clean and _sr_reg is not None and hasattr(_sr_reg,'iterrows'):
                    _match = _sr_reg[_sr_reg["Staff Code"].astype(str).apply(clean_code) == lv_clean]
                    if len(_match):
                        lv_name = str(_match.iloc[0].get("Staff Name",""))
                        lv_role = str(_match.iloc[0].get("Role",""))
                        lv_unit = str(_match.iloc[0].get("Unit",""))

                if lv_clean and lv_name:
                    st.success(f"✅ {lv_name} — {lv_role} | {lv_unit}")
                    if lm.is_on_leave(lv_clean):
                        _ea = lm.get_active_leave(lv_clean)
                        if _ea:
                            st.warning(f"⚠️ Already on {_ea[0]['leave_type']} until {_ea[0]['end_date']}")
                elif lv_clean:
                    lv_name = st.text_input("Staff name (manual)", key="lv_name_manual")

                with st.form("leave_form"):
                    lc1, lc2 = st.columns(2)
                    with lc1:
                        leave_type = st.selectbox("Leave type", list(LEAVE_TYPES.keys()))
                        start_date: date = st.date_input("Start date", value=datetime.now().date())  # type: ignore
                        suppress   = st.checkbox("Suppress email notifications", value=True)
                    with lc2:
                        end_date  = st.date_input("End date",
                            value=datetime.now().date() + timedelta(
                                days=LEAVE_TYPES.get(leave_type,{}).get('days_entitled',21) or 21))
                        reason    = st.text_area("Reason / notes", height=68)

                    lt_info  = LEAVE_TYPES.get(leave_type, {})
                    comp_lbl = COMPENSATION_LABELS.get(lt_info.get('compensation'),'')
                    if lt_info.get('affects_performance'):
                        st.warning(f"⚠️ Performance impact: {comp_lbl}")
                    else:
                        st.success(f"✅ No performance impact")

                    if st.form_submit_button("✅ Submit leave record", type="primary"):
                        name_to_save = lv_name or "Unknown"
                        if not lv_clean:
                            st.error("Staff code required.")
                        elif start_date > end_date:
                            st.error("End date must be after start date.")
                        else:
                            record = lm.add_leave(
                                lv_clean, name_to_save, leave_type,
                                start_date, end_date, reason,
                                approved_by=uname, notify_suppress=suppress)
                            audit_log("LEAVE_RECORDED", uname,
                                      f"{name_to_save} | {leave_type} | {start_date} to {end_date}")
                            st.success(f"Leave recorded: {name_to_save} — {record['days']} days")
                            st.cache_data.clear()
                            st.rerun()

    with lv2:
        st.subheader("Leave overview")
        all_records = lm.records
        if not all_records:
            st.info("No leave records yet.")
        else:
            lv_df = pd.DataFrame(all_records)
            # Filters
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                status_f = st.selectbox("Status", ['All','Active','Upcoming','Completed'], key="lvf_status")
            with fc2:
                type_f = st.selectbox("Leave type", ['All'] + list(LEAVE_TYPES.keys()), key="lvf_type")
            with fc3:
                name_f = st.text_input("Search name", key="lvf_name")

            lv_view = lv_df.copy()
            if status_f != 'All': lv_view = lv_view[lv_view['status'] == status_f]
            if type_f  != 'All':  lv_view = lv_view[lv_view['leave_type'] == type_f]
            if name_f.strip():    lv_view = lv_view[lv_view['staff_name'].str.lower().str.contains(name_f.lower(), na=False)]

            def hl_leave(v):
                if v == 'Active':    return 'background-color:#FFE4B5;color:#856404'
                if v == 'Upcoming':  return 'background-color:#CCE5FF;color:#004085'
                if v == 'Completed': return 'background-color:#D4EDDA;color:#155724'
                return ''
            def hl_perf_impact(v):
                if v == True: return 'background-color:#FFB6C1'
                return ''

            show_cols = ['staff_name','leave_type','start_date','end_date','days',
                         'status','affects_perf','compensation','notify_suppress','approved_by']
            show_cols = [c for c in show_cols if c in lv_view.columns]
            display_lv = lv_view[show_cols].copy()
            display_lv.columns = [c.replace('_',' ').title() for c in show_cols]

            st.dataframe(
                display_lv.style
                    .map(hl_leave, subset=['Status'])
                    .map(hl_perf_impact, subset=['Affects Perf'] if 'Affects Perf' in display_lv.columns else []),
                use_container_width=True, hide_index=True)

            # Summary stats
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Total records", len(lv_df))
            sc2.metric("Currently active", len(lv_df[lv_df['status']=='Active']))
            sc3.metric("Upcoming", len(lv_df[lv_df['status']=='Upcoming']))
            sc4.metric("Affects performance", int(lv_df['affects_perf'].sum()))

    with lv3:
        st.subheader("Performance compensation rules")
        st.caption("How BSC scores are adjusted when staff take extended or statutory leave.")

        for lt, rules in LEAVE_TYPES.items():
            comp = rules['compensation']
            affects = rules['affects_performance']
            icon = "⚠️" if affects else "✅"
            colour = "#FFF3CD" if affects else "#D4EDDA"
            border = "#F0AD4E" if affects else "#28A745"
            st.markdown(
                f"<div style='padding:10px 14px;background:{colour};border-left:4px solid {border};"
                f"border-radius:4px;margin:4px 0'>"
                f"{icon} <strong>{lt}</strong> (max {rules.get('days_entitled',0)} days) — "
                f"{COMPENSATION_LABELS.get(comp)}</div>",
                unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### Check a staff member's adjusted score")
        chk_code = st.text_input("Staff code", key="comp_check_code")
        chk_clean = clean_code(chk_code) if chk_code.strip() else ""
        if chk_clean:
            staff_leave = lm.get_staff_leave(chk_clean)
            if not staff_leave:
                st.info("No leave records for this staff member — full score applies.")
            else:
                aff = [r for r in staff_leave if r['affects_perf']]
                if not aff:
                    st.success("Leave on record but none affects performance score.")
                else:
                    for r in aff:
                        st.warning(
                            f"**{r['leave_type']}** — {r['start_date']} to {r['end_date']} "
                            f"({r['days']} days) | Adjustment: {COMPENSATION_LABELS.get(r['compensation'])}")

                # If we have their score data
                sc_row = staff_scores[staff_scores['Staff Code'].astype(str).apply(clean_code) == chk_clean]
                if len(sc_row):
                    reg = st.session_state.get('staff_registry',{})
                    name = reg.get(chk_clean,{}).get('Staff Name', chk_clean)
                    raw_score = sc_row['Final_BSC_Score'].values[0]
                    st.metric(f"{name} — current BSC score", fmt_score(raw_score))
                    st.caption("Note: Automatic monthly pro-rata compensation is applied when you have monthly-level scores per staff. Contact admin to manually adjust if needed.")

# ════════════════════════════════════════════════════════════════
# TAB 8 — TEAM INSIGHTS
# ════════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("Team insights")
    st.caption("Pillar heatmap, role distribution, and team performance patterns.")

    # ── Team Leaderboard ─────────────────────────────────────────
    if len(filtered) > 1 and "Final_BSC_Score" in filtered.columns:
        with st.expander("🏅 Team leaderboard — ranked by BSC score", expanded=True):
            _lb = (filtered[["Staff Name","Role","Unit","Final_BSC_Score","Performance_Remark"]]
                   .dropna(subset=["Final_BSC_Score"])
                   .sort_values("Final_BSC_Score", ascending=False)
                   .reset_index(drop=True)
                   .copy())
            _lb.index = _lb.index + 1
            _lb["Rank"] = _lb.index
            _lb["BSC Score"] = _lb["Final_BSC_Score"].apply(lambda x: f"{x:.2f}")
            _lb["Remark"] = _lb["Performance_Remark"]
            _lb_disp = _lb[["Rank","Staff Name","Role","Unit","BSC Score","Remark"]]

            def _lb_clr_row(row):
                try:
                    s = float(row["BSC Score"])
                    clr = ("var(--brand-light,#E8F5EE)" if s>=4.0 else "#F0FDF4" if s>=3.5
                           else "#FFFBEB" if s>=2.5 else "#FEF2F2")
                    return [f"background:{clr}"]*len(row)
                except: return [""]*len(row)

            st.dataframe(
                _lb_disp.style.apply(_lb_clr_row, axis=1),
                use_container_width=True, hide_index=True, height=320)

            # Summary row
            _lbc1,_lbc2,_lbc3,_lbc4 = st.columns(4)
            _lbc1.metric("Team avg BSC", f"{_lb['Final_BSC_Score'].mean():.2f}")
            _lbc2.metric("🏆 Exceeded (≥3.5)", int((_lb['Final_BSC_Score']>=3.5).sum()))
            _lbc3.metric("✅ On track (2.5–3.5)", int(((_lb['Final_BSC_Score']>=2.5)&(_lb['Final_BSC_Score']<3.5)).sum()))
            _lbc4.metric("⚠️ Needs support (<2.5)", int((_lb['Final_BSC_Score']<2.5).sum()))

    if not df_proc.empty and "Pillar" in df_proc.columns:
        _ti_c1, _ti_c2 = st.columns(2)
        with _ti_c1:
            pa = df_proc.groupby("Pillar")["Weighted_Score"].mean().reset_index()
            fig_p = px.bar(pa, x="Pillar", y="Weighted_Score",
                           title="Average weighted score by pillar",
                           color="Pillar",
                           color_discrete_map={"Financial":"var(--brand-primary,#006B3F)",
                                               "Customer Focus":"#185FA5",
                                               "Operational Excellence":"#F5A623"})
            fig_p.update_layout(showlegend=False, height=280,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_p, use_container_width=True)

        with _ti_c2:
            # Monthly trend — average weighted score per month
            _m_cols = active_months[:6] if active_months else []
            if _m_cols and "Staff Name" in filtered.columns:
                _trend_rows = []
                for _mc in _m_cols:
                    if _mc in df_proc.columns:
                        _mc_avg = df_proc[_mc].mean()
                        _trend_rows.append({"Month": _mc.replace(" Actual","").replace("-26","'26").replace("-25","'25"),
                                            "Avg Actual": _mc_avg})
                if _trend_rows:
                    _tr_df = pd.DataFrame(_trend_rows)
                    fig_tr = px.line(_tr_df, x="Month", y="Avg Actual",
                                     title="Monthly actuals trend (all KPIs)",
                                     markers=True,
                                     color_discrete_sequence=["var(--brand-primary,#006B3F)"])
                    fig_tr.update_layout(height=280,
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_tr, use_container_width=True)

    if len(filtered):
        ic1, ic2 = st.columns(2)
        with ic1:
            if "Role" in filtered.columns and filtered["Role"].nunique() > 1:
                role_avg = filtered.groupby("Role")["Final_BSC_Score"].agg(
                    ["mean","count"]).round(2).reset_index()
                role_avg.columns = ["Role","Avg BSC","Count"]
                role_avg = role_avg.sort_values("Avg BSC", ascending=False)
                fig_ra = px.bar(role_avg, x="Avg BSC", y="Role",
                                orientation="h", title="Avg BSC by role",
                                color="Avg BSC", color_continuous_scale="RdYlGn",
                                range_color=[1,5], text="Avg BSC")
                fig_ra.update_traces(texttemplate="%{x:.2f}", textposition="outside")
                fig_ra.update_layout(height=max(300, len(role_avg)*28),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ra, use_container_width=True)

        with ic2:
            if "Category" in filtered.columns and filtered["Category"].nunique() > 1:
                cat = filtered.groupby("Category")["Final_BSC_Score"].mean().reset_index()
                cat.columns = ["Category","Avg BSC"]
                fig_c = px.bar(cat, x="Category", y="Avg BSC",
                               title="Avg BSC — Branch vs Head Office",
                               color="Category",
                               color_discrete_sequence=["var(--brand-primary,#006B3F)","#185FA5"])
                fig_c.add_hline(y=3.0, line_dash="dash", line_color="#F5A623")
                fig_c.update_layout(showlegend=False, height=300,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_c, use_container_width=True)

        # Performance band table by role
        if "Role" in filtered.columns and "Performance_Remark" in filtered.columns:
            st.markdown("#### Performance bands by role")
            band_df = filtered.groupby(["Role","Performance_Remark"]).size().reset_index(name="Count")
            band_pivot = band_df.pivot(index="Role", columns="Performance_Remark",
                                       values="Count").fillna(0).astype(int)
            st.dataframe(band_pivot, use_container_width=True)
    else:
        st.info("Upload BSC data to see team insights.")
