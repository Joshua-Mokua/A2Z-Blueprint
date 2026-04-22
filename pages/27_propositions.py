"""pages/27_propositions.py — Proposition / Segment Overlay Performance.
Horizontal units (Women Banking, Diaspora, SME, Agri, Trade Finance, etc.)
track INFLUENCE KPIs, not portfolio volumes — zero double-counting.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from pages._shared import load_shared_state
from pages._access import require_access

require_access("propositions")

DATA = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()

@st.cache_data(ttl=60, show_spinner=False)
def _load_props():
    f = DATA / "proposition_performance.json"
    return json.loads(f.read_text()) if f.exists() else {}

@st.cache_data(ttl=60, show_spinner=False)
def _load_tags():
    f = DATA / "segment_tags.json"
    return json.loads(f.read_text()) if f.exists() else {}

@st.cache_data(ttl=30, show_spinner=False)
def _load_cfg():
    f = DATA / "proposition_config.json"
    return json.loads(f.read_text()) if f.exists() else {"propositions": {}}

props   = _load_props()
tags    = _load_tags()
pcfg    = _load_cfg()
# Merge live config into performance data so page always reflects current targets/names
for _tag, _pcfg_prop in pcfg.get("propositions", {}).items():
    if _tag in props:
        # Update name, icon, color, kpi targets from config (config is source of truth)
        props[_tag]["name"]        = _pcfg_prop.get("name",  props[_tag].get("name",""))
        props[_tag]["icon"]        = _pcfg_prop.get("icon",  props[_tag].get("icon",""))
        props[_tag]["color"]       = _pcfg_prop.get("color", props[_tag].get("color",""))
        props[_tag]["description"] = _pcfg_prop.get("description", props[_tag].get("description",""))
        props[_tag]["head_name"]   = ""
        # Update KPI targets from config
        cfg_kpi_tgts = {k["id"]: k["target"] for k in _pcfg_prop.get("kpis", [])}
        for kpi in props[_tag].get("kpis", []):
            if kpi["id"] in cfg_kpi_tgts:
                kpi["target"] = cfg_kpi_tgts[kpi["id"]]
# Filter to active only
props = {t: p for t, p in props.items()
         if pcfg.get("propositions", {}).get(t, {}).get("active", True)}
role  = ud.get("role",""); sc = str(ud.get("staff_code","") or "")
is_admin   = ud.get("is_admin",False)
is_exec    = any(x in role for x in ("Chief","Director","Head","Managing"))

# ── Header ─────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>🎯 Propositions</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Segment overlay scorecard · No double-counting · Influence metrics</span></div>",
    unsafe_allow_html=True)

# Explain the model
with st.expander("ℹ️ How proposition tracking works — no double-counting", expanded=False):
    st.markdown("""
**Two layers, different KPIs:**

| Layer | Who owns it | What is measured | Source |
|-------|-------------|-----------------|--------|
| **Primary Portfolio** | Branch RM / Corporate RM | Deposits, Loans, NFI, NPL, New Accounts | CBS (direct) |
| **Proposition Overlay** | Proposition Head / Specialist RM | Acquired customers, Penetration %, Wallet share, Events, NPS | Tagged customers |

**The key distinction:** A woman-owned business in Hassan's portfolio contributes to his
deposit and loan targets. The **Women Banking unit does NOT claim those deposits** —
instead they track *how many* women customers the bank has, *what share* of their wallet
is with us, and *how deeply* they are penetrated with products. These are **influence metrics**,
not volume metrics, so there is no double-counting.

**Segment tags** are applied to CIF records. A customer can carry multiple tags
(e.g. WB + SME). The proposition scorecard aggregates across all branches — it is a
**bank-wide cross-cutting view**, not a branch P&L view.
""")

if is_admin:
    st.markdown(
        "⚙️ [Configure propositions in Admin → Propositions tab](/Admin) — "
        "add/remove propositions, edit KPIs and targets, toggle active/inactive.",
        unsafe_allow_html=False)

if not props:
    st.info("No proposition data found. Run generate_propositions.py to initialise.")
    st.stop()

# ── Overview scorecard ─────────────────────────────────────────────
st.markdown("### Bank-wide proposition performance")
prop_list = list(props.values())
cols = st.columns(min(4, len(prop_list)))
for i, prop in enumerate(sorted(prop_list, key=lambda x:-x["proposition_score"])):
    col = cols[i % len(cols)]
    score = prop["proposition_score"]
    color = prop["color"]
    clr_score = "#16A34A" if score >= 3.5 else "#D97706" if score >= 2.5 else "#DC2626"
    col.markdown(
        f"<div style='background:{color}10;border:1.5px solid {color}40;"
        f"border-radius:12px;padding:14px;text-align:center;margin-bottom:10px'>"
        f"<div style='font-size:22px'>{prop['icon']}</div>"
        f"<div style='font-size:12px;font-weight:700;color:{color};margin:4px 0'>"
        f"{prop['name']}</div>"
        f"<div style='font-size:28px;font-weight:800;color:{clr_score}'>"
        f"{score:.2f}</div>"
        f"<div style='font-size:10px;color:var(--color-text-tertiary)'>"
        f"{prop['total_tagged_customers']:,} tagged customers</div>"
        f"</div>",
        unsafe_allow_html=True)
    if (i+1) % 4 == 0 and i+1 < len(prop_list):
        cols = st.columns(min(4, len(prop_list)-(i+1)))

st.markdown("---")

# ── Proposition detail tabs ────────────────────────────────────────
prop_names = [f"{p['icon']} {p['name']}" for p in prop_list]
sel_tab = st.selectbox("Select proposition to view:", prop_names, key="prop_sel")
sel_tag = next(t for t,p in props.items() if f"{p['icon']} {p['name']}" == sel_tab)
prop = props[sel_tag]

color = prop["color"]
st.markdown(
    f"<div style='background:{color}08;border:1px solid {color}30;"
    f"border-radius:12px;padding:16px;margin:8px 0'>"
    f"<span style='font-size:20px'>{prop['icon']}</span> "
    f"<b style='font-size:18px;color:{color}'>{prop['name']}</b> "
    f"<span style='color:var(--color-text-secondary);font-size:13px'>· {prop['description']}</span><br>"
    f"<span style='font-size:12px;color:var(--color-text-tertiary)'>"
    f"Head: {prop['head_name'] or 'Not assigned'} · "
    f"Tagged customers: {prop['total_tagged_customers']:,} · "
    f"Period: {prop['period']}</span>"
    f"</div>",
    unsafe_allow_html=True)

tabs = st.tabs(["📊 KPI Scorecard","📈 Trend","🌿 Branch Contribution","👥 RM Champions","📋 About"])

# ── TAB 1: KPI Scorecard ───────────────────────────────────────────
with tabs[0]:
    kpis = prop["kpis"]
    overall = prop["proposition_score"]
    score_color = "#16A34A" if overall>=3.5 else "#D97706" if overall>=2.5 else "#DC2626"
    score_label = ("Outstanding" if overall>=4.5 else "Exceeds Expectations" if overall>=3.5
                   else "Meets Expectations" if overall>=2.5 else "Needs Improvement" if overall>=2.0
                   else "Below Expectations")
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:20px;margin-bottom:16px'>"
        f"<div style='text-align:center'>"
        f"<div style='font-size:42px;font-weight:800;color:{score_color}'>{overall:.2f}</div>"
        f"<div style='font-size:12px;color:{score_color};font-weight:600'>{score_label}</div>"
        f"<div style='font-size:10px;color:var(--color-text-tertiary)'>/ 5.0</div>"
        f"</div>"
        f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
        f"Proposition BSC score based on {len(kpis)} influence KPIs.<br>"
        f"<b>These metrics do not overlap with portfolio BSC KPIs</b> — "
        f"no deposit or loan volumes are counted here unless explicitly proposition-specific."
        f"</div></div>",
        unsafe_allow_html=True)

    # KPI rows
    from utils.core import fmt_kpi_value
    for kpi in sorted(kpis, key=lambda x: -x["score"]):
        tgt = kpi["target"]; act = kpi["actual"]; ach = kpi["achievement"]
        score = kpi["score"]; wt = kpi["weight"]
        is_rev = kpi["direction"] == "lower"
        score_clr = "#16A34A" if score>=3.5 else "#D97706" if score>=2.5 else "#DC2626"
        ach_clr   = "#16A34A" if (ach>=100 and not is_rev) or (ach>=100 and is_rev) else "#DC2626"
        ach_lbl   = f"{ach:.1f}%"
        tgt_disp  = fmt_kpi_value(tgt, kpi["name"], short=True)
        act_disp  = fmt_kpi_value(act, kpi["name"], short=True)

        # Progress bar (capped at 130%)
        bar_pct = min(ach / 130 * 100, 100)
        bar_clr = "#16A34A" if ach >= 100 else "#D97706" if ach >= 80 else "#DC2626"

        st.markdown(
            f"<div style='background:var(--color-background-secondary);"
            f"border-radius:8px;padding:10px 14px;margin-bottom:6px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px'>"
            f"<div style='font-size:13px;font-weight:600'>{kpi['name']}</div>"
            f"<div style='display:flex;gap:12px;font-size:12px'>"
            f"<span style='color:var(--color-text-tertiary)'>Tgt: {tgt_disp}</span>"
            f"<span style='color:var(--color-text-secondary)'>Act: {act_disp}</span>"
            f"<span style='color:{ach_clr};font-weight:700'>{ach_lbl}</span>"
            f"<span style='background:{score_clr};color:white;border-radius:10px;"
            f"padding:1px 8px;font-weight:700'>{score:.1f}</span>"
            f"<span style='color:var(--color-text-tertiary)'>wt {wt:.0%}</span>"
            f"</div></div>"
            f"<div style='background:#F3F4F6;border-radius:3px;height:5px'>"
            f"<div style='width:{bar_pct:.0f}%;background:{bar_clr};"
            f"height:100%;border-radius:3px'></div>"
            f"</div></div>",
            unsafe_allow_html=True)

# ── TAB 2: Trend ──────────────────────────────────────────────────
with tabs[1]:
    st.markdown("**12-month trend** for each KPI")
    # Show trend for first 3 KPIs
    for kpi in kpis[:4]:
        trend = kpi.get("monthly_trend",[])
        if not trend: continue
        months = [t["month"] for t in trend]
        values = [t["value"] for t in trend]
        df_t = pd.DataFrame({"Month":months, kpi["name"]:values})
        st.markdown(f"**{kpi['name']}** (target: {fmt_kpi_value(kpi['target'],kpi['name'],True)})")
        st.line_chart(df_t.set_index("Month"))

# ── TAB 3: Branch Contribution ────────────────────────────────────
with tabs[2]:
    st.markdown(
        "**Branch contribution** — which branches have the most tagged customers "
        "for this proposition. Branches are ranked by tagged customer count.")
    bc = sorted(prop.get("branch_contributions",[]), key=lambda x:-x.get("tagged_customers",0))
    if bc:
        rows = [{
            "Branch": b["branch"][:30],
            "Tagged Customers": b["tagged_customers"],
            "Proposition Score": b["proposition_score"],
            "Champion RM": b.get("champion_rm","—"),
        } for b in bc]
        df_bc = pd.DataFrame(rows)
        st.dataframe(df_bc, use_container_width=True, hide_index=True)
        total_tagged = sum(b["tagged_customers"] for b in bc)
        st.caption(
            f"Total tagged customers across {len(bc)} branches: **{total_tagged:,}**. "
            f"Note: These customers also appear in branch RM portfolios — no double-counting "
            f"because proposition uses influence KPIs, not portfolio volumes.")
    else:
        st.info("No branch contribution data available.")

# ── TAB 4: RM Champions ───────────────────────────────────────────
with tabs[3]:
    st.markdown(
        "**Contributing RMs** — relationship managers whose portfolios include "
        "tagged customers for this proposition.")
    rm_codes = prop.get("contributing_rms",[])
    if rm_codes:
        rm_rows = []
        for rm_sc in rm_codes[:20]:
            rm_user = next(((u,d) for u,d in um.users.items()
                            if str(d.get("staff_code","")) == rm_sc), (None,{}))
            if rm_user[0]:
                rm_rows.append({
                    "Staff Code": rm_sc,
                    "Name": rm_user[1].get("full_name","")[:30],
                    "Role": rm_user[1].get("role","")[:35],
                    "Unit": rm_user[1].get("unit","")[:25],
                })
        if rm_rows:
            st.dataframe(pd.DataFrame(rm_rows), use_container_width=True, hide_index=True)
        st.info(
            f"💡 These RMs' portfolio customers are **tagged** with the "
            f"{prop['icon']} {prop['name']} segment code. Their portfolio BSC is unchanged "
            f"— only the proposition overlay benefits from the tagging.")
    else:
        st.info("No RM data for this proposition.")

# ── TAB 5: About ──────────────────────────────────────────────────
with tabs[4]:
    st.markdown(f"### {prop['icon']} {prop['name']} — Proposition Overview")
    st.markdown(f"**What this measures:** {prop['description']}")
    st.markdown("""
**Why it's different from the branch BSC:**
The branch BSC measures portfolio ownership — every deposit, loan and fee income
attributed to a relationship manager's CBS portfolio. That's the P&L view.

The proposition scorecard measures **market development** — how effectively the
bank is building this customer segment, regardless of which branch or RM holds
the customer. A Women Banking customer managed by Hassan in Thika branch still
contributes to the Women Banking proposition score, but Hassan's portfolio BSC
is not affected by the WB scoring.
""")
    st.markdown(f"**KPIs in this scorecard:** {len(prop['kpis'])}")
    _kpi_rows = ["| KPI | Target | Actual | Achievement | Weight |",
                 "|-----|--------|--------|-------------|--------|"]
    for k in prop['kpis']:
        _kpi_rows.append(
            f"| {k['name']} | {fmt_kpi_value(k['target'],k['name'],True)} | "
            f"{fmt_kpi_value(k['actual'],k['name'],True)} | "
            f"{k['achievement']:.1f}% | {k['weight']:.0%} |")
    st.markdown("\n".join(_kpi_rows))
    st.markdown(
        f"**Tagged customers:** {prop['total_tagged_customers']:,} CIFs carry the "
        f"`{sel_tag}` segment tag.  **Period:** {prop['period']} (Jan–Dec)")
