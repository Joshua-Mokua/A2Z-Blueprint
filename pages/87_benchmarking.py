"""pages/87_benchmarking.py — Tier-1 Bank Benchmarking.

Compares Ecobank against KCB, Equity, Co-op, NCBA across 15 financial metrics
over 4 quarters. Provides peer ranking, gap-to-leader, and strategic themes.

Data source: data/tier1_benchmarking.json
Updated: quarterly when CBK Bank Supervision reports are released.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
from pathlib import Path
from datetime import datetime

from pages._shared import load_shared_state
from pages._access import require_access, get_my_scope
from utils.core import audit_log

require_access("benchmarking")

DATA = Path(__file__).parent.parent / "data"

um, ud, uname, *_ = load_shared_state()[:12]


@st.cache_data(ttl=60)
def _load():
    return a2z_db.load_json(DATA / "tier1_benchmarking.json", default={})


bm = _load()
if not bm:
    st.error("Benchmarking data not found. Place tier1_benchmarking.json in data/.")
    st.stop()

quarters    = bm.get("quarters", [])
banks       = list(bm.get("quarterly_metrics", {}).keys())
metrics_md  = bm.get("metric_metadata", {})
our_bank    = bm.get("our_bank", "Ecobank")
themes      = bm.get("strategic_themes", [])
latest_q    = quarters[-1] if quarters else None

# ─── Header ──────────────────────────────────────────────────────────────
st.markdown("# 🏆 Tier-1 Bank Benchmarking")
st.caption(f"As at {bm.get('as_at','')}  ·  Source: {bm.get('data_source','')}")

# Quick context strip
qmetrics = bm.get("quarterly_metrics", {}).get(our_bank, {}).get(latest_q, {})

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Our assets", f"KES {qmetrics.get('assets_kes_b','—')}B")
c2.metric("ROE", f"{qmetrics.get('roe_pct','—')}%")
c3.metric("NPL", f"{qmetrics.get('npl_pct','—')}%")
c4.metric("Branches", qmetrics.get('branches','—'))
c5.metric("Digital customers", f"{qmetrics.get('digital_customers_m','—')}M")

st.markdown("---")

tabs = st.tabs([
    "📊 Dashboard",
    "📈 Quarterly Trends",
    "🔢 Comparison Matrix",
    "🎯 Gap-vs-Leader",
    "💡 Strategic Themes",
])

# ═══════════════════════════════════════════════════════════════════════════
# Tab 1 — DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown(f"### Where Ecobank ranks across {len(metrics_md)} metrics ({latest_q})")

    # Build a ranking table
    rank_rows = []
    for metric_key, meta in metrics_md.items():
        higher = meta.get("higher_better", True)
        bank_values = []
        for bank in banks:
            v = bm["quarterly_metrics"].get(bank, {}).get(latest_q, {}).get(metric_key)
            if v is not None:
                bank_values.append((bank, v))

        # Sort
        bank_values.sort(key=lambda x: x[1], reverse=higher)

        # Find our rank
        our_rank = "—"
        our_value = None
        for i, (bank, v) in enumerate(bank_values, 1):
            if bank == our_bank:
                our_rank = i
                our_value = v
                break

        leader_bank = bank_values[0][0] if bank_values else "—"
        leader_value = bank_values[0][1] if bank_values else None

        # RAG status
        if our_rank == 1:
            rag = "🟢 Leader"
        elif our_rank in (2, 3):
            rag = "🟡 Top 3"
        else:
            rag = "🔴 Behind"

        rank_rows.append({
            "Category": meta.get("category", ""),
            "Metric":   meta.get("label", metric_key),
            "Our value": f"{our_value:.1f}" if isinstance(our_value, (int, float)) else "—",
            "Rank":     f"#{our_rank} of {len(bank_values)}",
            "Leader":   leader_bank,
            "Leader value": f"{leader_value:.1f}" if isinstance(leader_value, (int, float)) else "—",
            "Status":   rag,
        })

    df = pd.DataFrame(rank_rows).sort_values(["Category", "Metric"])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Summary metrics
    leader_count = sum(1 for r in rank_rows if "Leader" in r["Status"])
    top3_count   = sum(1 for r in rank_rows if "Top 3" in r["Status"])
    behind_count = sum(1 for r in rank_rows if "Behind" in r["Status"])

    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("🟢 Where we lead", leader_count)
    m2.metric("🟡 Top-3 metrics", top3_count)
    m3.metric("🔴 Catching-up metrics", behind_count, delta_color="inverse")

# ═══════════════════════════════════════════════════════════════════════════
# Tab 2 — QUARTERLY TRENDS
# ═══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("### Quarterly trends across all Tier-1 banks")

    # Choose metric
    metric_options = [(k, v["label"]) for k, v in metrics_md.items()]
    chosen_label = st.selectbox(
        "Metric",
        [m[1] for m in metric_options],
        index=0,
        key="bm_metric_pick",
    )
    chosen_key = next(k for k, lbl in metric_options if lbl == chosen_label)

    # Build the trend chart
    trend_rows = []
    for bank in banks:
        for q in quarters:
            v = bm["quarterly_metrics"].get(bank, {}).get(q, {}).get(chosen_key)
            if v is not None:
                trend_rows.append({"Bank": bank, "Quarter": q, "Value": v})

    if trend_rows:
        df = pd.DataFrame(trend_rows)
        fig = px.line(
            df, x="Quarter", y="Value", color="Bank", markers=True,
            title=f"{chosen_label} — quarterly trend",
        )
        # Highlight Ecobank with thicker line
        fig.for_each_trace(lambda t: t.update(line=dict(width=4)) if t.name == our_bank else t.update(line=dict(width=2, dash="dot")))
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)

        # Q-over-Q growth table
        st.markdown(f"**Quarter-over-quarter change in {chosen_label}**")
        latest = df[df["Quarter"] == quarters[-1]].set_index("Bank")["Value"]
        prev   = df[df["Quarter"] == quarters[-2]].set_index("Bank")["Value"]
        qoq = ((latest - prev) / prev * 100).round(2).reset_index()
        qoq.columns = ["Bank", f"QoQ change (%)"]
        st.dataframe(qoq.sort_values(qoq.columns[1], ascending=False),
                      use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════════════════
# Tab 3 — COMPARISON MATRIX
# ═══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown(f"### Full peer comparison matrix ({latest_q})")
    st.caption("Latest quarter across all 5 banks · 15 metrics · grouped by category")

    chosen_q = st.selectbox("Quarter", quarters, index=len(quarters)-1, key="bm_q_pick")

    # Build the matrix
    matrix_rows = []
    for metric_key, meta in metrics_md.items():
        row = {"Category": meta.get("category", ""), "Metric": meta.get("label", metric_key)}
        for bank in banks:
            v = bm["quarterly_metrics"].get(bank, {}).get(chosen_q, {}).get(metric_key)
            row[bank] = v
        matrix_rows.append(row)

    df_matrix = pd.DataFrame(matrix_rows).sort_values(["Category", "Metric"])

    # Style with traffic lights — leader green, laggard red
    def style_row(row):
        styles = [""] * len(row)
        meta = next((m for m in metrics_md.values() if m.get("label") == row["Metric"]), {})
        higher = meta.get("higher_better", True)

        # Get bank columns
        bank_cols = [c for c in row.index if c in banks]
        bank_values = [(c, row[c]) for c in bank_cols if isinstance(row[c], (int, float))]
        if not bank_values:
            return styles

        bank_values.sort(key=lambda x: x[1], reverse=higher)
        leader_bank   = bank_values[0][0]
        laggard_bank  = bank_values[-1][0]

        for i, col in enumerate(row.index):
            if col == leader_bank:
                styles[i] = "background-color: #d4edda; color: #155724"
            elif col == laggard_bank:
                styles[i] = "background-color: #f8d7da; color: #721c24"
            elif col == our_bank:
                styles[i] = "background-color: #fff3cd; color: #856404; font-weight: 600"
        return styles

    styled = df_matrix.style.apply(style_row, axis=1).format(
        {b: "{:.1f}" for b in banks}
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.caption("🟢 Leader · 🔴 Laggard · 🟡 Ecobank (highlighted in yellow)")

# ═══════════════════════════════════════════════════════════════════════════
# Tab 4 — GAP-VS-LEADER
# ═══════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown(f"### Gap-vs-leader analysis ({latest_q})")
    st.caption("How far behind (or ahead of) the market leader on each metric")

    gap_rows = []
    for metric_key, meta in metrics_md.items():
        higher = meta.get("higher_better", True)
        bank_values = []
        for bank in banks:
            v = bm["quarterly_metrics"].get(bank, {}).get(latest_q, {}).get(metric_key)
            if v is not None:
                bank_values.append((bank, v))
        if not bank_values:
            continue

        bank_values.sort(key=lambda x: x[1], reverse=higher)
        leader_bank, leader_v = bank_values[0]

        our_v = next((v for b, v in bank_values if b == our_bank), None)
        if our_v is None:
            continue

        if leader_v == 0:
            gap_pct = 0
        elif higher:
            gap_pct = (leader_v - our_v) / leader_v * 100
        else:
            # For "lower is better", positive gap means we're worse
            gap_pct = (our_v - leader_v) / leader_v * 100

        gap_rows.append({
            "Category":   meta.get("category", ""),
            "Metric":     meta.get("label", metric_key),
            "Our value":  our_v,
            "Leader":     leader_bank,
            "Leader val": leader_v,
            "Gap %":      gap_pct,
            "Status":     "✅ Ahead" if gap_pct < 0 else ("🟡 Within 10%" if gap_pct <= 10 else ("🟠 10-30%" if gap_pct <= 30 else "🔴 >30%")),
        })

    df_gap = pd.DataFrame(gap_rows).sort_values("Gap %", ascending=False)

    st.dataframe(
        df_gap.style.format({"Our value": "{:.1f}", "Leader val": "{:.1f}", "Gap %": "{:+.1f}"}),
        use_container_width=True, hide_index=True,
    )

    # Visual
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_gap["Metric"],
        y=df_gap["Gap %"],
        marker_color=["#28a745" if g < 0 else "#ffc107" if g <= 10 else "#fd7e14" if g <= 30 else "#dc3545" for g in df_gap["Gap %"]],
        text=[f"{g:+.1f}%" for g in df_gap["Gap %"]],
        textposition="outside",
    ))
    fig.update_layout(
        title="Gap to Tier-1 leader (negative = ahead, positive = behind)",
        xaxis=dict(tickangle=-45),
        yaxis=dict(title="Gap %"),
        height=480,
    )
    st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════
# Tab 5 — STRATEGIC THEMES
# ═══════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("### Strategic themes from the benchmarking")
    st.caption("Where the gaps create or threaten competitive position")

    for theme in themes:
        is_strength = theme.get("our_value") == theme.get("leader_value")
        icon = "🏆" if is_strength else "🎯"

        with st.expander(f"{icon} **{theme['theme']}** — gap {theme.get('gap_pct',0):.1f}%", expanded=is_strength):
            c1, c2, c3 = st.columns(3)
            c1.metric("Leader",       theme.get("leader",""))
            c2.metric("Leader value", theme.get("leader_value",""))
            c3.metric("Our value",    theme.get("our_value",""))

            st.markdown(f"**Implication:** {theme.get('implication','')}")

# Audit page view
audit_log("BENCHMARKING_VIEWED", uname, f"Tier-1 benchmarking dashboard viewed at {datetime.utcnow().isoformat()}")
