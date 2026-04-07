"""pages/11_competitor.py — Competitor Intelligence: Kenya Banking Industry Analysis."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from utils.core import *
from pages._shared import load_shared_state

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

OUR_BANK = 'Ecobank'
ECO_GREEN = '#006B3F'; ECO_GOLD = '#F5A623'

# ── Metric definitions ────────────────────────────────────────────────
# Column names match the clean Industry_Financial_Review_Clean.xlsx
# Ratios are stored as percentages (e.g. 80.5 = 80.5%) in the clean file
METRICS = {
    'Assets':     ('Total Assets',                   'KES 000', False),
    'Deposits':   ('Customer Deposits',               'KES 000', False),
    'Loans':      ('Net Loans & Advances',            'KES 000', False),
    'NII':        ('Net Interest Income (NII)',        'KES 000', False),
    'NFI':        ('Non-Funded Income (NFI)',          'KES 000', False),
    'Revenue':    ('Total Operating Income',           'KES 000', False),
    'PBT':        ('Profit Before Tax (PBT)',          'KES 000', False),
    'PAT':        ('Profit After Tax (PAT)',            'KES 000', False),
    'Opex':       ('Total Operating Expenses',         'KES 000', False),
    'Staff Costs':('Staff Costs',                      'KES 000', False),
    'Gross NPL':  ('Gross NPL',                        'KES 000', False),
    'Equity':     ('Shareholders Funds',               'KES 000', False),
    'RWA':        ('Risk-Weighted Assets (RWA)',        'KES 000', False),
    'CIR':        ('Cost-to-Income Ratio (CIR)',        '%',       True),
    'ROE':        ('Return on Equity (ROE)',            '%',       False),
    'NIM':        ('Net Interest Margin (NIM)',          '%',       False),
    'NPL Ratio':  ('NPL Ratio',                         '%',       True),
    'LDR':        ('Loans-to-Deposit Ratio (LDR)',       '%',       False),
    'CAR':        ('Capital Adequacy Ratio (CAR)',       '%',       False),
    'Liquidity':  ('Liquidity Ratio',                   '%',       False),
    'CASA':       ('CASA Ratio',                        '%',       False),
    'NIM_raw':    ('Net Interest Margin (NIM)',          '%',       False),
}
RATIO_COLS = ['CIR','ROE','NIM','NPL Ratio','LDR','CAR','Liquidity','CASA']
SIZE_COLS  = ['Assets','Deposits','Loans','NII','NFI','Revenue','PBT','PAT','Opex',
              'Staff Costs','Gross NPL','Equity','RWA']

# ════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════
st.markdown(
    f"<div style='padding:16px 22px;background:{ECO_GREEN};border-radius:10px;"
    f"margin-bottom:16px'>"
    f"<div style='color:white;font-size:18px;font-weight:500'>"
    f"Kenya Banking Industry — Competitor Intelligence</div>"
    f"<div style='color:#9FE1CB;font-size:12px;margin-top:3px'>"
    f"Ecobank vs 39 peers · Quarterly data 2021–2025 · "
    f"Market position · Watch list · Strategic gaps</div></div>",
    unsafe_allow_html=True)

# ── File upload ───────────────────────────────────────────────────────
up = st.file_uploader(
    "Industry Financial Review Excel",
    type=["xlsx","xls"], key="industry_upload",
    help="Upload once — data persists until you logout or upload a new file")

# Bytes-first caching — file survives Streamlit reruns without re-uploading
raw = cache_upload(up, "_industry_raw_bytes")

if raw is None:
    st.markdown(
        "<div style='padding:32px;text-align:center;background:#E8F5EE;"
        "border-radius:12px;border:1px solid #006B3F44'>"
        "<div style='font-size:28px;margin-bottom:12px'>📊</div>"
        "<div style='font-size:16px;font-weight:500;color:#006B3F'>"
        "Upload the Industry Financial Review Excel to activate</div>"
        "<div style='color:#666;font-size:13px;margin-top:8px'>"
        "File: <code>Industry_Financial_Review_-_Main_.xlsx</code><br>"
        "The <b>Main</b> sheet will be read automatically.</div>"
        "</div>",
        unsafe_allow_html=True)
    st.stop()

# ── Load & process ────────────────────────────────────────────────────
# Inline (no function/cache) so bytecode can never serve a stale version

_df_raw = pd.DataFrame()
for _hdr in (2, 1, 0):
    try:
        _tmp = pd.read_excel(io.BytesIO(raw), sheet_name='Main', header=_hdr)
        _tmp = _tmp.dropna(axis=1, how='all').copy()
        _tmp.columns = _tmp.columns.str.strip()
        if 'Bank' in _tmp.columns:
            _df_raw = _tmp
            break
    except Exception:
        continue

if _df_raw.empty:
    st.error("Could not read the Main sheet. Check the file format.")
    st.stop()

_df_raw['Bank'] = _df_raw['Bank'].astype(str).str.strip()
_df_raw = _df_raw[~_df_raw['Bank'].isin(['nan','xx','NaN','None','']) & _df_raw['Bank'].notna()].copy()

# Period → Year
for _pc in ('Period', 'Year', 'Quarter'):
    if _pc in _df_raw.columns:
        _df_raw['Year'] = _df_raw[_pc].astype(str).str.strip()
        break
else:
    _df_raw['Year'] = 'Unknown'
_df_raw['Period_sort'] = _df_raw['Year'].str.replace(' ', '', regex=False)

# Build short-name numeric columns
_METRIC_MAP = [
    ('Assets',     'Total Assets',                 False),
    ('Deposits',   'Customer Deposits',             False),
    ('Loans',      'Net Loans & Advances',          False),
    ('NII',        'Net Interest Income (NII)',      False),
    ('NFI',        'Non-Funded Income (NFI)',        False),
    ('Revenue',    'Total Operating Income',         False),
    ('PBT',        'Profit Before Tax (PBT)',        False),
    ('PAT',        'Profit After Tax (PAT)',          False),
    ('Opex',       'Total Operating Expenses',       False),
    ('Staff Costs','Staff Costs',                   False),
    ('Gross NPL',  'Gross NPL',                     False),
    ('Equity',     'Shareholders Funds',             False),
    ('RWA',        'Risk-Weighted Assets (RWA)',      False),
    ('CIR',        'Cost-to-Income Ratio (CIR)',     True),
    ('ROE',        'Return on Equity (ROE)',         True),
    ('NIM',        'Net Interest Margin (NIM)',       True),
    ('NPL Ratio',  'NPL Ratio',                     True),
    ('LDR',        'Loans-to-Deposit Ratio (LDR)',   True),
    ('CAR',        'Capital Adequacy Ratio (CAR)',   True),
    ('Liquidity',  'Liquidity Ratio',               True),
    ('CASA',       'CASA Ratio',                    True),
]

for _short, _full, _is_ratio in _METRIC_MAP:
    if _full not in _df_raw.columns:
        _df_raw[_short] = np.nan
        continue
    _col = pd.to_numeric(_df_raw[_full], errors='coerce')
    if _is_ratio:
        _nz = _col[(_col.notna()) & (_col != 0)]
        if len(_nz) > 0 and _nz.abs().median() < 2:
            _col = _col * 100          # decimal → percent
        _col = _col.where(_col.abs() < 500)   # cap outliers
    _df_raw[_short] = _col

_rev = _df_raw['Revenue'].replace(0, np.nan)
_df_raw['CIR_calc'] = (_df_raw['Opex'].abs() / _rev * 100).where(_rev.notna())
_df_raw['ROA_calc'] = (_df_raw['PBT'] / _df_raw['Assets'].replace(0, np.nan) * 100)

df = _df_raw.copy()

# Latest period per bank
latest_p = df.groupby('Bank')['Period_sort'].max().reset_index()
latest_p.columns = ['Bank','MaxPeriod']
dfm = df.merge(latest_p, on='Bank')
dl  = dfm[dfm['Period_sort'] == dfm['MaxPeriod']].copy()

if OUR_BANK not in dl['Bank'].values:
    st.error(f"'{OUR_BANK}' not found in the data. Check bank name spelling.")
    st.stop()

eco = dl[dl['Bank'] == OUR_BANK].iloc[0]
eco_assets  = eco['Assets']
eco_period  = eco['Year']
n_banks     = dl['Bank'].nunique()

# Cluster banks
watch_list  = dl[(dl['Assets'] > eco_assets*0.5) &
                 (dl['Assets'] < eco_assets) &
                 (dl['Bank'] != OUR_BANK)].sort_values('Assets', ascending=False)
beat_list   = dl[(dl['Assets'] > eco_assets) &
                 (dl['Assets'] < eco_assets*2.5) &
                 (dl['Bank'] != OUR_BANK)].sort_values('Assets')
top_banks   = dl.nlargest(5, 'PBT')

# Market shares
mkt = {
    'Assets':  eco['Assets']  / dl['Assets'].sum()  * 100,
    'Deposits':eco['Deposits']/ dl['Deposits'].sum()* 100,
    'Loans':   eco['Loans']   / dl['Loans'].sum()   * 100,
    'Revenue': eco['Revenue'] / dl['Revenue'].sum() * 100,
    'PBT':     eco['PBT']     / dl['PBT'].sum()     * 100,
}

# Rankings
def rank_eco(col, lower_better=False):
    s = dl.sort_values(col, ascending=lower_better).reset_index(drop=True)
    r = s[s['Bank']==OUR_BANK].index
    return (r[0]+1, dl[col].notna().sum()) if len(r) else ('?', 0)

# ════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📍 Market position",
    "📊 Industry benchmarks",
    "🎯 Watch list & threats",
    "📈 Growth & trajectory",
    "🏆 Strategic gaps",
    "📋 MD & Board brief",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — MARKET POSITION
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown(f"#### Ecobank market position — {eco_period}")
    st.caption(f"Based on {n_banks} banks reporting in Kenya. All figures KES thousands.")

    # Top metric row
    mc = st.columns(5)
    for i,(label,val) in enumerate(mkt.items()):
        rk, tot = rank_eco(label)
        mc[i].markdown(
            f"<div style='padding:12px;background:var(--color-background-secondary);"
            f"border-radius:8px;border:0.5px solid var(--color-border-tertiary);text-align:center'>"
            f"<div style='font-size:10px;color:var(--color-text-tertiary);text-transform:uppercase'>{label}</div>"
            f"<div style='font-size:20px;font-weight:500;color:{ECO_GREEN}'>{val:.2f}%</div>"
            f"<div style='font-size:11px;color:var(--color-text-secondary)'>market share</div>"
            f"<div style='font-size:11px;color:{ECO_GOLD};font-weight:500'>#{rk} of {tot}</div>"
            f"</div>", unsafe_allow_html=True)

    st.markdown("---")
    pc1, pc2 = st.columns(2)

    with pc1:
        # Bubble chart — Assets vs Revenue, sized by PBT
        plot_df = dl[dl[['Assets','Revenue','PBT']].notna().all(axis=1)].copy()
        plot_df['Is Ecobank'] = plot_df['Bank'] == OUR_BANK
        plot_df['PBT_abs']   = plot_df['PBT'].abs().clip(lower=1e6)
        plot_df['Color']     = plot_df['Bank'].apply(
            lambda b: ECO_GREEN if b==OUR_BANK else
                      ('#E24B4A' if b in beat_list['Bank'].values else
                       ('#F5A623' if b in watch_list['Bank'].values else '#AAAAAA')))

        fig = go.Figure()
        for _, row in plot_df.iterrows():
            fig.add_scatter(
                x=[row['Assets']/1e6], y=[row['Revenue']/1e6],
                mode='markers+text',
                marker=dict(size=max(8, row['PBT_abs']/1e8),
                            color=row['Color'], opacity=0.8,
                            line=dict(width=1.5 if row['Bank']==OUR_BANK else 0.5,
                                      color='black' if row['Bank']==OUR_BANK else 'white')),
                text=[row['Bank']], textposition='top center',
                textfont=dict(size=9,
                              color='black' if row['Bank']==OUR_BANK else '#555'),
                name=row['Bank'], showlegend=False,
                hovertemplate=(f"<b>{row['Bank']}</b><br>"
                               f"Assets: {row['Assets']/1e6:.1f}B<br>"
                               f"Revenue: {row['Revenue']/1e6:.1f}B<br>"
                               f"PBT: {row['PBT']/1e6:.1f}B<extra></extra>"))

        # Legend markers
        for label, color in [('Ecobank',ECO_GREEN),('Beat list',ECO_GOLD),
                              ('Watch list','#E24B4A'),('Others','#AAAAAA')]:
            fig.add_scatter(x=[None], y=[None], mode='markers',
                            marker=dict(size=10, color=color),
                            name=label, showlegend=True)

        eco_x = eco['Assets']/1e6; eco_y = eco['Revenue']/1e6
        fig.add_vline(x=eco_x, line_dash='dot', line_color=ECO_GREEN, line_width=1)
        fig.add_hline(y=eco_y, line_dash='dot', line_color=ECO_GREEN, line_width=1)
        fig.update_layout(
            title='Market map — Assets vs Revenue (bubble = PBT)',
            xaxis_title='Total Assets (KES Billions)',
            yaxis_title='Operating Revenue (KES Billions)',
            height=440, plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation='h', y=-0.15))
        st.plotly_chart(fig, use_container_width=True)

    with pc2:
        # Rankings table
        rank_metrics = ['Assets','Deposits','Loans','Revenue','PBT','NIM','CIR','NPL Ratio','LDR','CAR']
        rank_rows = []
        for m in rank_metrics:
            lb = METRICS.get(m, ('','',' '))[2] if m in METRICS else False
            rk, tot = rank_eco(m, lb)
            v = eco.get(m, np.nan)
            ind_med = dl[m].median()
            if not np.isnan(v) and not np.isnan(ind_med):
                gap = v - ind_med
                pct = f"{v:.1f}%" if METRICS.get(m,('','',''))[1]=='%' else fmt_num(v, short=True)
                med = f"{ind_med:.1f}%" if METRICS.get(m,('','',''))[1]=='%' else fmt_num(ind_med, short=True)
                better = gap < 0 if lb else gap > 0
                rank_rows.append({
                    'Metric': m, 'Ecobank': pct,
                    'Industry median': med,
                    'Rank': f"#{rk}/{tot}",
                    'vs Median': '✅ Better' if better else '⚠️ Below',
                })
        if rank_rows:
            rank_df = pd.DataFrame(rank_rows)
            def hl_rank(v):
                if '✅' in str(v): return 'color:#006B3F;font-weight:500'
                if '⚠️' in str(v): return 'color:#BA7517'
                return ''
            st.markdown("**Ecobank rankings vs industry**")
            st.dataframe(rank_df.style.map(hl_rank, subset=['vs Median']),
                        use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 2 — INDUSTRY BENCHMARKS
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("#### Industry-wide benchmarks")

    sel_metric = st.selectbox("Select metric", RATIO_COLS + ['CIR_calc','ROA_calc'],
                              key="bench_metric")

    bench_df = dl[['Bank','Size', sel_metric]].dropna().sort_values(sel_metric)
    bench_df['Color'] = bench_df['Bank'].apply(
        lambda b: ECO_GREEN if b==OUR_BANK else
                  ('#E24B4A' if b in beat_list['Bank'].values else
                   ('#F5A623' if b in watch_list['Bank'].values else '#CCCCCC')))

    fig_b = go.Figure()
    eco_val = eco.get(sel_metric, np.nan)
    fig_b.add_bar(
        x=bench_df['Bank'], y=bench_df[sel_metric],
        marker_color=bench_df['Color'],
        text=[f"{v:.1f}%" for v in bench_df[sel_metric]],
        textposition='outside', textfont=dict(size=9))
    if not np.isnan(eco_val):
        fig_b.add_hline(y=bench_df[sel_metric].median(),
                        line_dash='dash', line_color='#185FA5', line_width=1.5,
                        annotation_text=f"Median: {bench_df[sel_metric].median():.1f}%")
    fig_b.update_layout(
        title=f"{sel_metric} — all 39 Kenya banks (latest period)",
        height=400, xaxis_tickangle=-45,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        yaxis_tickformat=',.1f')
    st.plotly_chart(fig_b, use_container_width=True)

    # Heatmap — key ratios all banks
    hm_metrics = [m for m in ['CIR','ROE','NIM','NPL Ratio','LDR','CAR','Liquidity']
                  if m in dl.columns]
    hm_banks   = [OUR_BANK] + beat_list['Bank'].tolist() + watch_list['Bank'].tolist()
    hm_banks   = [b for b in hm_banks if b in dl['Bank'].values][:18]
    hm_data    = dl[dl['Bank'].isin(hm_banks)].set_index('Bank')[hm_metrics]

    # Normalise each metric to 0-1 for heatmap (handling direction)
    hm_norm = hm_data.copy()
    for m in hm_metrics:
        col = hm_norm[m].dropna()
        if len(col) > 0:
            mn, mx = col.min(), col.max()
            if mx > mn:
                normalized = (hm_norm[m] - mn) / (mx - mn)
                # Invert for lower-is-better metrics
                if METRICS.get(m,('','',''))[2]:
                    normalized = 1 - normalized
                hm_norm[m] = normalized

    st.markdown("#### Performance heatmap — Ecobank + peer cluster")
    fig_hm = px.imshow(hm_norm.T,
        color_continuous_scale=[[0,'#E24B4A'],[0.5,'#F5A623'],[1,'#006B3F']],
        text_auto='.2f', aspect='auto',
        title='Relative performance (green=better, normalised per metric)')
    fig_hm.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig_hm, use_container_width=True)

    # Size-tier comparison
    st.markdown("#### Ecobank vs size-tier peers")
    tier_df = dl.groupby('Size')[hm_metrics].median()
    eco_tier = eco['Size']
    tier_rows = []
    for m in hm_metrics:
        eco_v = eco.get(m, np.nan)
        tier_v = tier_df.loc[eco_tier, m] if eco_tier in tier_df.index and m in tier_df.columns else np.nan
        all_v  = dl[m].median()
        if not np.isnan(eco_v):
            lb = METRICS.get(m,('','',''))[2]
            tier_rows.append({
                'Metric': m,
                'Ecobank': f"{eco_v:.1f}%",
                f'{eco_tier} tier median': f"{tier_v:.1f}%" if not np.isnan(tier_v) else '—',
                'All banks median': f"{all_v:.1f}%" if not np.isnan(all_v) else '—',
                'vs Tier': ('✅' if (eco_v < tier_v if lb else eco_v > tier_v) else '⚠️') if not np.isnan(tier_v) else '—',
            })
    if tier_rows:
        st.dataframe(pd.DataFrame(tier_rows), use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 3 — WATCH LIST & THREATS
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### 🎯 Competition to beat")
        st.caption("Banks just ahead of Ecobank — overtake these to move up the rankings.")
        for _, r in beat_list.iterrows():
            lead_b  = (r['Assets'] - eco_assets)/1e9
            cir_v   = r.get('CIR', np.nan)
            nim_v   = r.get('NIM', np.nan)
            npl_v   = r.get('NPL Ratio', np.nan)
            # Vulnerability score: high CIR or high NPL = exploitable weakness
            vuln    = (1 if not np.isnan(cir_v) and cir_v > 0.70 else 0) + \
                      (1 if not np.isnan(npl_v) and npl_v > 0.20 else 0)
            v_badge = {0:'🟢 Resilient',1:'🟡 Exploitable',2:'🔴 Vulnerable'}[vuln]
            gap_close = 'Assets close' if lead_b < 20 else ('Significant gap' if lead_b < 80 else 'Large gap')
            st.markdown(
                f"<div style='padding:12px 14px;background:var(--color-background-secondary);"
                f"border-radius:8px;border-left:4px solid {ECO_GOLD};"
                f"border-top:0.5px solid var(--color-border-tertiary);"
                f"border-right:0.5px solid var(--color-border-tertiary);"
                f"border-bottom:0.5px solid var(--color-border-tertiary);margin:4px 0'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                f"<b>{r['Bank']}</b><span style='font-size:11px'>{r.get('Size','')} | {r.get('Ownership','')}</span></div>"
                f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:6px;font-size:11px'>"
                f"<span>Assets: <b>{r['Assets']/1e9:.1f}B</b></span>"
                f"<span>Lead: <b>+{lead_b:.1f}B</b></span>"
                f"<span>CIR: <b>{cir_v:.1f}%" if not np.isnan(cir_v) else "<span>CIR: —"
                f"</b></span></div>"
                f"<div style='margin-top:6px;font-size:11px'>"
                f"NIM: {nim_v:.1f}% | NPL: {npl_v:.1f}%" if not np.isnan(nim_v) and not np.isnan(npl_v) else "NIM: — | NPL: —"
                f"</div>"
                f"<div style='margin-top:4px;font-size:10px;color:var(--color-text-tertiary)'>"
                f"{v_badge} &nbsp;|&nbsp; {gap_close}</div>"
                f"</div>", unsafe_allow_html=True)

    with c2:
        st.markdown("#### ⚠️ Watch list — can catch up")
        st.caption("Banks below Ecobank that could close the gap if Ecobank loses momentum.")
        for _, r in watch_list.iterrows():
            gap_b = (eco_assets - r['Assets'])/1e9
            # Growth proxy
            bank_ts = df[df['Bank']==r['Bank']].sort_values('Period_sort')['Assets']
            bank_ts = pd.to_numeric(bank_ts, errors='coerce').dropna()
            q_growth = bank_ts.pct_change().mean()*100 if len(bank_ts) > 1 else 0
            eco_ts   = df[df['Bank']==OUR_BANK].sort_values('Period_sort')['Assets']
            eco_ts   = pd.to_numeric(eco_ts, errors='coerce').dropna()
            eco_growth = eco_ts.pct_change().mean()*100 if len(eco_ts) > 1 else 0
            faster   = q_growth > eco_growth
            threat   = '🔴 Growing faster than Ecobank' if faster else '🟢 Slower growth'
            periods_to_close = gap_b / max(0.1, (r['Assets']*q_growth/100 - eco_assets*eco_growth/100)/1e9) if faster and q_growth != eco_growth else None

            st.markdown(
                f"<div style='padding:12px 14px;background:var(--color-background-secondary);"
                f"border-radius:8px;border-left:4px solid {'#E24B4A' if faster else '#1D9E75'};"
                f"border-top:0.5px solid var(--color-border-tertiary);"
                f"border-right:0.5px solid var(--color-border-tertiary);"
                f"border-bottom:0.5px solid var(--color-border-tertiary);margin:4px 0'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<b>{r['Bank']}</b><span style='font-size:11px'>{r.get('Size','')} | {r.get('Ownership','')}</span></div>"
                f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px;font-size:11px'>"
                f"<span>Assets: <b>{r['Assets']/1e9:.1f}B</b></span>"
                f"<span>Gap: <b>{gap_b:.1f}B</b></span>"
                f"<span>Qtly growth: <b>{q_growth:.1f}%</b></span>"
                f"<span>Eco growth: <b>{eco_growth:.1f}%</b></span></div>"
                f"<div style='margin-top:4px;font-size:10px;color:var(--color-text-tertiary)'>{threat}</div>"
                f"</div>", unsafe_allow_html=True)

    # Radar chart — Ecobank vs nearest rival
    st.markdown("---")
    st.markdown("#### Radar comparison — Ecobank vs selected peer")
    peer_options = [b for b in (beat_list['Bank'].tolist() + watch_list['Bank'].tolist())
                    if b in dl['Bank'].values]
    sel_peer = st.selectbox("Compare against", peer_options, key="radar_peer")
    radar_metrics = ['NIM','ROE','NPL Ratio','LDR','CAR','Liquidity']
    radar_metrics = [m for m in radar_metrics if m in dl.columns]

    if sel_peer and radar_metrics:
        peer_row = dl[dl['Bank']==sel_peer].iloc[0]
        radar_vals_eco  = []
        radar_vals_peer = []
        for m in radar_metrics:
            ev = eco.get(m, 0) or 0
            pv = peer_row.get(m, 0) or 0
            # Normalise to 0-1 within industry range
            col_all = dl[m].dropna()
            mn, mx  = col_all.min(), col_all.max()
            ev_n = (ev-mn)/(mx-mn) if mx>mn else 0
            pv_n = (pv-mn)/(mx-mn) if mx>mn else 0
            lb   = METRICS.get(m,('','',''))[2]
            radar_vals_eco.append(1-ev_n if lb else ev_n)
            radar_vals_peer.append(1-pv_n if lb else pv_n)

        fig_r = go.Figure()
        fig_r.add_scatterpolar(r=radar_vals_eco+[radar_vals_eco[0]],
                                theta=radar_metrics+[radar_metrics[0]],
                                fill='toself', name='Ecobank',
                                line_color=ECO_GREEN, fillcolor='rgba(0,107,63,0.15)')
        fig_r.add_scatterpolar(r=radar_vals_peer+[radar_vals_peer[0]],
                                theta=radar_metrics+[radar_metrics[0]],
                                fill='toself', name=sel_peer,
                                line_color=ECO_GOLD, fillcolor='rgba(245,166,35,0.15)')
        fig_r.update_layout(polar=dict(radialaxis=dict(visible=True,range=[0,1])),
                             height=380, title=f'Ecobank vs {sel_peer} (normalised, higher=better)',
                             legend=dict(orientation='h',y=-0.1))
        st.plotly_chart(fig_r, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 4 — GROWTH & TRAJECTORY
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown("#### Growth trajectories — Ecobank vs industry")

    growth_metric = st.selectbox(
        "Metric", ['Assets','Deposits','Loans','Revenue','PBT'], key="growth_metric")

    # Build time series for selected banks
    ts_banks = [OUR_BANK] + beat_list['Bank'].tolist()[:4] + watch_list['Bank'].tolist()[:3]
    ts_banks = [b for b in ts_banks if b in df['Bank'].values]

    ts_data = []
    for bank in ts_banks:
        # Year column is guaranteed by load_industry normalisation
        bdf = df[df['Bank']==bank].sort_values('Period_sort')
        bdf = bdf[['Year', growth_metric]].dropna() if growth_metric in bdf.columns else pd.DataFrame()
        for _, row in bdf.iterrows():
            ts_data.append({'Bank':bank, 'Period': row['Year'],
                            'Value':float(row[growth_metric])})
    ts_df = pd.DataFrame(ts_data)

    if len(ts_df):
        color_map = {OUR_BANK: ECO_GREEN}
        fig_ts = px.line(ts_df, x='Period', y='Value', color='Bank',
                         title=f'{growth_metric} trend — Ecobank vs peers (KES 000)',
                         color_discrete_map=color_map,
                         line_dash_map={OUR_BANK: 'solid'})
        fig_ts.update_traces(selector=dict(name=OUR_BANK), line_width=3)
        fig_ts.update_layout(height=380, xaxis_tickangle=-30,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_ts, use_container_width=True)

    # Growth rate comparison (YoY)
    st.markdown("#### Year-on-year growth rates — latest vs prior year")
    growth_rows = []
    for bank in ts_banks:
        bdf = df[df['Bank']==bank].sort_values('Period_sort')
        bdf[growth_metric] = pd.to_numeric(bdf[growth_metric], errors='coerce')
        vals = bdf[growth_metric].dropna()
        if len(vals) >= 5:
            yoy = float((vals.iloc[-1]/vals.iloc[-5]-1)*100)
            eco_yoy = float(growth_rows[0].get('_yoy', 0)) if growth_rows else 999.0
            growth_rows.append({
                'Bank':          bank,
                'Latest':        fmt_num(vals.iloc[-1], short=True),
                'YoY Growth %':  f"{yoy:+.1f}%",
                'vs Ecobank':    '✅ Faster' if bank == OUR_BANK else
                                 ('🔴 Faster than us' if yoy > eco_yoy else '✅ Slower'),
                '_yoy':          yoy,   # raw float for comparison — hidden from display
            })
    if growth_rows:
        g_df = pd.DataFrame(growth_rows).drop(columns=['_yoy'], errors='ignore')
        st.dataframe(g_df, use_container_width=True, hide_index=True)

    # Ecobank own trend — all key metrics
    st.markdown("#### Ecobank quarterly trend — all key metrics")
    eco_ts = df[df['Bank']==OUR_BANK].sort_values('Period_sort').copy()
    for m in ['Assets','Deposits','Loans','Revenue','PBT','NIM','CIR','NPL Ratio','LDR']:
        if m in eco_ts.columns:
            eco_ts[m] = pd.to_numeric(eco_ts[m], errors='coerce')

    trend_metrics = st.multiselect("Select metrics", ['NIM','CIR','NPL Ratio','LDR','CAR','ROE'],
                                    default=['NIM','CIR','LDR'], key="trend_sel")
    if trend_metrics:
        trend_data = []
        for m in trend_metrics:
            if m not in eco_ts.columns:
                continue
            for _, row in eco_ts[['Year', m]].dropna().iterrows():
                trend_data.append({'Period': row['Year'], 'Metric': m, 'Value': float(row[m])})
        if trend_data:
            tr_df = pd.DataFrame(trend_data)
            fig_tr = px.line(tr_df, x='Period', y='Value', color='Metric',
                             title='Ecobank ratio trends (own quarters)',
                             markers=True)
            fig_tr.update_layout(height=320, xaxis_tickangle=-30,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_tr, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 5 — STRATEGIC GAPS
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("#### What industry leaders do that Ecobank doesn't yet")

    # Calculate gaps
    top5_pbt = dl.nlargest(5,'PBT')
    top5_roe  = dl.nlargest(5,'ROE')
    top5_nim  = dl.nlargest(5,'NIM')
    top5_cir  = dl.nsmallest(5,'CIR')   # lower is better

    def gap_card(title, eco_val, leader_val, leader_name, metric, unit='%',
                 lower_better=False, insight='', color='#006B3F'):
        if np.isnan(eco_val) or np.isnan(leader_val): return
        gap   = leader_val - eco_val
        if lower_better: gap = -gap  # positive gap = leader is better
        fmt_v = lambda v: f"{v:.1f}%" if unit=='%' else fmt_num(v, short=True)
        clr   = '#006B3F' if gap > 0 else '#E24B4A'
        st.markdown(
            f"<div style='padding:14px;background:var(--color-background-secondary);"
            f"border-radius:8px;border-left:4px solid {color};"
            f"border-top:0.5px solid var(--color-border-tertiary);"
            f"border-right:0.5px solid var(--color-border-tertiary);"
            f"border-bottom:0.5px solid var(--color-border-tertiary);margin:6px 0'>"
            f"<div style='font-weight:500;margin-bottom:6px'>{title}</div>"
            f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px'>"
            f"<div><div style='color:var(--color-text-tertiary);font-size:10px'>Ecobank</div>"
            f"<div style='font-size:18px;font-weight:500'>{fmt_v(eco_val)}</div></div>"
            f"<div><div style='color:var(--color-text-tertiary);font-size:10px'>Best ({leader_name})</div>"
            f"<div style='font-size:18px;font-weight:500'>{fmt_v(leader_val)}</div></div>"
            f"<div><div style='color:var(--color-text-tertiary);font-size:10px'>Gap</div>"
            f"<div style='font-size:18px;font-weight:500;color:{clr}'>{fmt_v(abs(gap))}</div></div></div>"
            f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:8px;border-top:0.5px solid var(--color-border-tertiary);padding-top:6px'>"
            f"💡 {insight}</div></div>",
            unsafe_allow_html=True)

    sg1, sg2 = st.columns(2)
    with sg1:
        st.markdown("**Profitability gaps**")
        top_roe_bank  = top5_roe.iloc[0]
        top_nim_bank  = top5_nim.iloc[0]
        best_cir_bank = top5_cir.iloc[0]

        gap_card("ROE — Return on Equity",
                 eco['ROE'], top_roe_bank['ROE'], top_roe_bank['Bank'], 'ROE',
                 insight="Higher ROE signals better capital efficiency. Ecobank needs to grow PBT faster than equity to close this gap.",
                 color='#534AB7')
        gap_card("NIM — Net Interest Margin",
                 eco['NIM'], top_nim_bank['NIM'], top_nim_bank['Bank'], 'NIM',
                 insight="NIM improvement requires either repricing of loans upward or reducing cost of funds. Review CASA ratio and deposit mix.",
                 color='#185FA5')
        gap_card("CIR — Cost-to-Income",
                 eco['CIR'], best_cir_bank['CIR'], best_cir_bank['Bank'], 'CIR',
                 lower_better=True,
                 insight="High CIR means Ecobank is less operationally efficient. Target is below 65%. Every 1% CIR reduction = direct PBT uplift.",
                 color='#E24B4A')

    with sg2:
        st.markdown("**Balance sheet & risk gaps**")
        # LDR gap — Ecobank loans very low
        best_ldr_bank = dl[(dl['LDR'] < 0.80) & (dl['LDR'] > 0.50)].nlargest(1,'PBT')
        if len(best_ldr_bank):
            blb = best_ldr_bank.iloc[0]
            gap_card("LDR — Loans to Deposits",
                     eco['LDR'], blb['LDR'], blb['Bank'], 'LDR',
                     insight=f"Ecobank LDR at {eco['LDR']:.1f}% is critically low. Industry best practice: 60-75%. Excess liquidity is unutilised earning capacity — each 1% LDR increase on {eco['Deposits']/1e9:.0f}B deposits = ~{eco['Deposits']*0.01*0.13/1e6:.0f}M KES in NII.",
                     color='#006B3F')

        gap_card("NPL Ratio — Asset Quality",
                 eco['NPL Ratio'], top5_cir.iloc[0]['NPL Ratio'],
                 top5_cir.iloc[0]['Bank'], 'NPL Ratio',
                 lower_better=True,
                 insight="Lower NPL = better asset quality. Ecobank NPL is relatively controlled — leverage this as a strength in pricing.",
                 color='#1D9E75')

        # CASA gap
        ind_casa = dl['CASA'].median()
        if not np.isnan(eco.get('CASA', np.nan)) and not np.isnan(ind_casa):
            best_casa = dl.nlargest(1,'CASA').iloc[0]
            gap_card("CASA Ratio — Low-cost deposits",
                     eco['CASA'], best_casa['CASA'], best_casa['Bank'], 'CASA',
                     insight="Higher CASA = lower cost of funds = better NIM. Grow current and savings accounts through salary banking, SME current accounts, and agent banking.",
                     color=ECO_GOLD)

    # Strategic actions table
    st.markdown("---")
    st.markdown("#### Strategic action map — what to do")
    actions = [
        {'Priority':'🔴 URGENT', 'Area':'Loan book growth',
         'Gap':f"LDR {eco['LDR']:.1f}% vs industry {dl['LDR'].median():.1f}%",
         'Action':'Accelerate SME and retail lending. Excess liquidity sitting in government securities is leaving NII on the table.',
         'Impact':'Each 10% LDR improvement ≈ significant NII uplift'},
        {'Priority':'🔴 URGENT','Area':'Cost efficiency (CIR)',
         'Gap':f"CIR {eco['CIR']:.1f}% vs top performers {top5_cir['CIR'].mean():.1f}%",
         'Action':'Cost restructuring programme — target below 70% CIR. Review branch footprint, automate manual processes, reduce paper-based transactions.',
         'Impact':'Each 1% CIR reduction = direct PBT uplift proportional to revenue'},
        {'Priority':'🟡 HIGH','Area':'ROE improvement',
         'Gap':f"ROE {eco['ROE']:.1f}% vs top quartile {dl['ROE'].quantile(0.75):.1f}%",
         'Action':'Grow PBT faster than equity base — either through revenue growth or dividend distribution to reduce equity denominator.',
         'Impact':'Shareholder value and credit rating improvement'},
        {'Priority':'🟡 HIGH','Area':'CASA ratio & cost of funds',
         'Gap':f"CASA {eco.get('CASA',0):.1f}% — grow low-cost deposits",
         'Action':'Salary banking campaigns, SME current accounts, digital wallet activations. Lower cost of funds directly improves NIM.',
         'Impact':'100bps CASA improvement ≈ 20-30bps NIM improvement'},
        {'Priority':'🟢 MEDIUM','Area':'NFI diversification',
         'Gap':f"NFI as % of revenue: {eco['NFI']/eco['Revenue']:.1f}% vs industry {(dl['NFI']/dl['Revenue']).median():.1f}%",
         'Action':'Grow trade finance, FX income, digital transaction fees. Less reliance on NII reduces interest rate risk.',
         'Impact':'More resilient revenue mix, higher valuation multiple'},
        {'Priority':'🟢 MEDIUM','Area':'Digital & channels productivity',
         'Gap':'LDR and customer acquisition below peers',
         'Action':'Accelerate DFS customer acquisition, merchant banking, agency banking expansion — lower cost-to-serve than branch banking.',
         'Impact':'Customer base growth improves deposit gathering and cross-sell'},
    ]
    act_df = pd.DataFrame(actions)
    def hl_pri(v):
        if '🔴' in str(v): return 'color:#A32D2D;font-weight:500'
        if '🟡' in str(v): return 'color:#BA7517;font-weight:500'
        if '🟢' in str(v): return 'color:#006B3F'
        return ''
    st.dataframe(act_df.style.map(hl_pri, subset=['Priority']),
                use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 6 — MD & BOARD BRIEF
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown(f"#### Kenya Banking Industry — Board Brief")
    st.caption(f"Prepared: {datetime.now().strftime('%d %b %Y')} | Based on {eco_period} data | {n_banks} banks")

    # Executive summary
    ldr_gap = dl['LDR'].median() - eco['LDR']
    cir_gap = eco['CIR'] - top5_cir['CIR'].mean()
    roe_gap = dl['ROE'].quantile(0.75) - eco['ROE']

    st.markdown(
        f"<div style='padding:16px 20px;background:#E8F5EE;border-radius:10px;"
        f"border:1px solid #006B3F44;margin-bottom:16px'>"
        f"<div style='font-size:14px;font-weight:500;color:#006B3F;margin-bottom:10px'>"
        f"Executive summary</div>"
        f"<div style='font-size:13px;line-height:1.7'>"
        f"Ecobank Kenya ranks <b>#{rank_eco('Assets')[0]}</b> by assets in a 39-bank industry with "
        f"<b>{mkt['Assets']:.2f}% market share</b>. "
        f"The bank's deposit franchise is relatively stronger than its loan book — "
        f"<b>LDR of {eco['LDR']:.1f}%</b> compares unfavourably to the industry median of "
        f"<b>{dl['LDR'].median():.1f}%</b>, representing the single largest strategic opportunity. "
        f"Cost efficiency at <b>CIR {eco['CIR']:.1f}%</b> is a key vulnerability versus top performers at "
        f"<b>{top5_cir['CIR'].mean():.1f}%</b>. "
        f"Asset quality is a relative strength — NPL at {eco['NPL Ratio']:.1f}% is better than "
        f"the industry median of {dl['NPL Ratio'].median():.1f}%. "
        f"NIM at {eco['NIM']:.3f} is above the industry median of {dl['NIM'].median():.3f} "
        f"but below top performers at {top5_nim['NIM'].mean():.3f}."
        f"</div></div>",
        unsafe_allow_html=True)

    # Three sections
    b1, b2, b3 = st.columns(3)
    with b1:
        st.markdown("**Where we stand**")
        standings = [
            ('Market rank (assets)', f"#{rank_eco('Assets')[0]}/{n_banks}"),
            ('Market share (assets)', f"{mkt['Assets']:.2f}%"),
            ('Market share (deposits)', f"{mkt['Deposits']:.2f}%"),
            ('Market share (loans)', f"{mkt['Loans']:.2f}%"),
            ('Market share (PBT)', f"{mkt['PBT']:.2f}%"),
            ('NIM rank', f"#{rank_eco('NIM')[0]}/{n_banks}"),
            ('CIR rank', f"#{rank_eco('CIR', True)[0]}/{n_banks}"),
            ('NPL rank', f"#{rank_eco('NPL Ratio', True)[0]}/{n_banks}"),
        ]
        for label, val in standings:
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;font-size:12px;"
                f"padding:3px 0;border-bottom:0.5px solid var(--color-border-tertiary)'>"
                f"<span>{label}</span><b>{val}</b></div>",
                unsafe_allow_html=True)

    with b2:
        st.markdown("**Critical attention areas**")
        concerns = [
            ('CIR', eco['CIR'], 65.0, True, 'Industry target: below 65%'),
            ('LDR', eco['LDR'], 60.0, False, 'Industry median: 60%+'),
            ('ROE', eco['ROE'], 55.0, False, 'Top quartile: 55%+'),
            ('NIM', eco['NIM'], dl['NIM'].median(), False, 'Above median ✅'),
            ('NPL', eco['NPL Ratio'], 20.0, True, 'Within control ✅'),
            ('CAR', eco['CAR'], 14.0, False, 'Above minimum ✅'),
        ]
        for metric, val, bench, lb, note in concerns:
            ok  = val < bench if lb else val >= bench
            clr = '#006B3F' if ok else '#E24B4A'
            ico = '✅' if ok else '⚠️'
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"font-size:12px;padding:4px 0;border-bottom:0.5px solid var(--color-border-tertiary)'>"
                f"<span>{ico} {metric}</span>"
                f"<span style='color:{clr};font-weight:500'>{val:.1f}%</span>"
                f"<span style='color:var(--color-text-tertiary);font-size:10px'>{note}</span>"
                f"</div>", unsafe_allow_html=True)

    with b3:
        st.markdown("**Watch list & threats**")
        st.markdown(f"*Banks closing in:*")
        for _, r in watch_list.head(3).iterrows():
            bank_ts2 = df[df['Bank']==r['Bank']].sort_values('Period_sort')['Assets']
            bank_ts2 = pd.to_numeric(bank_ts2, errors='coerce').dropna()
            qg = bank_ts2.pct_change().mean()*100 if len(bank_ts2)>1 else 0
            st.markdown(
                f"<div style='font-size:11px;padding:3px 0'>"
                f"• <b>{r['Bank']}</b> — {r['Assets']/1e9:.1f}B assets, growing {qg:.1f}%/qtr"
                f"</div>", unsafe_allow_html=True)
        st.markdown(f"*Next to overtake:*")
        for _, r in beat_list.head(3).iterrows():
            st.markdown(
                f"<div style='font-size:11px;padding:3px 0'>"
                f"• <b>{r['Bank']}</b> — {r['Assets']/1e9:.1f}B assets, "
                f"CIR {r['CIR']:.0f}%, LDR {r['LDR']:.0f}%"
                f"</div>", unsafe_allow_html=True)

    # Board resolution items
    st.markdown("---")
    st.markdown("#### Proposed board resolution items")
    resolutions = [
        ("Loan book growth target", "Set quarterly LDR targets to reach 50% by end 2026 (from current 21.8%). Approve credit appetite expansion for SME and retail segments."),
        ("Cost efficiency programme", "Mandate CIR reduction to below 70% within 18 months. Approve opex restructuring budget and automation investment."),
        ("CASA mobilisation strategy", "Approve salary banking and merchant acquisition campaign. Target: grow CASA by 15% in 12 months to reduce cost of funds."),
        ("Competitive response", f"Note competitive pressure from {', '.join(watch_list['Bank'].tolist()[:3])} who are growing faster than Ecobank. Approve strategic response plan."),
        ("Capital deployment", f"CAR at {eco['CAR']:.1f}% provides buffer above regulatory minimum. Approve deployment strategy to improve ROE."),
    ]
    for i, (title, body) in enumerate(resolutions, 1):
        st.markdown(
            f"<div style='padding:10px 14px;background:var(--color-background-secondary);"
            f"border-left:4px solid {ECO_GREEN};border-radius:0 6px 6px 0;margin:4px 0'>"
            f"<b>{i}. {title}</b><div style='font-size:12px;margin-top:4px;color:var(--color-text-secondary)'>{body}</div>"
            f"</div>", unsafe_allow_html=True)
