"""pages/100_md_cockpit.py — MD/CEO Executive Cockpit (v10.214).

Single-page executive surface aggregating the MD's primary modules
into 7 tabs:
  1. Command Centre Snapshot — top-level cross-module health
  2. BSC Summary — strategic balanced scorecard at a glance
  3. Strategic Initiatives RAG — portfolio status by pillar
  4. Board Papers — committee submission tracker
  5. Tier-1 Benchmarking — peer position vs KCB/Equity/Co-op/NCBA
  6. Financial Snapshot — Management Accounts highlights + SBU + RA
  7. Capital & Treasury — capital adequacy + liquidity + ALM

Design intent:
- This page does NOT replicate the underlying functionality. It
  surfaces top-level metrics + provides direct deep-link navigation
  to the canonical dashboard for each domain.
- Read-only by design. No write operations originate here. Operators
  who need to act drill down to the canonical dashboard.
- Department: strategy_performance (where MD-level views live alongside
  BSC, Board Papers, Benchmarking, Strategic Initiatives).
- Access key: "md_cockpit" — admin + MD/CEO/Director roles.

Mirrors the design discipline of 91_systems_view.py (panoramic page
that pulls from many sources without owning any data).
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from pages._access import require_access
from pages._shared import load_shared_state
from utils.core_audit import audit_log
from utils.config import currency_symbol, regulator, bank_name
from utils.db import db as a2z_db

# ──────────────────────────────────────────────────────────────────────
# Access + setup
# ──────────────────────────────────────────────────────────────────────

require_access("strategy_performance.md_cockpit")

DATA = Path(__file__).parent.parent / "data"
TODAY = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
role = str(ud.get("role", "")).lower()
is_admin = ud.get("is_admin", False)
is_md = any(x in role for x in ("md", "ceo", "director", "chief"))

audit_log(
    action="md_cockpit.view",
    username=uname,
    detail=f"role={role} is_admin={is_admin} is_md={is_md}",
    module="md_cockpit",
)


# ──────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────

st.markdown(
    "<div style='padding:24px;background:linear-gradient(135deg,"
    "#0F172A 0%,#1E40AF 50%,#0EA5E9 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>"
    "MD / CEO · EXECUTIVE COCKPIT · v10.214</div>"
    "<div style='font-size:30px;font-weight:800;margin-top:6px'>"
    "🎯 MD Cockpit</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px;max-width:780px'>"
    "Single-page executive surface. Each tab pulls top-level metrics "
    "from the canonical dashboard for that domain and provides direct "
    "deep-link navigation. Read-only — drill into the canonical pages "
    "to act. Department: strategy_performance.</div>"
    "</div>",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────
# Cached loaders (TTL 60s — executive surface, not a tactical tool)
# ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def _load_json_or_default(filename, default):
    """Load a JSON file from data/, return default if missing."""
    p = DATA / filename
    if not p.exists():
        return default
    try:
        return a2z_db.load_json(p)
    except Exception:
        return default


@st.cache_data(ttl=60, show_spinner=False)
def _load_list(filename):
    """Load a JSON list, returning [] if missing or malformed."""
    d = _load_json_or_default(filename, [])
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        # Some files store the list under a key like 'watchlist' or 'items'
        for v in d.values():
            if isinstance(v, list):
                return v
        return list(d.values())
    return []


def _kpi_box(label, value, delta=None, help_text=None):
    """Render a compact KPI box with optional delta + tooltip."""
    st.metric(label, value, delta=delta, help=help_text)


# ──────────────────────────────────────────────────────────────────────
# 7 Tabs (within G4's 7-tab cap — exactly at the ceiling)
# ──────────────────────────────────────────────────────────────────────

tabs = st.tabs([
    "📊 Command Centre",
    "🎯 BSC Summary",
    "🚀 Initiatives RAG",
    "📋 Board Papers",
    "🏆 Tier-1 Benchmarking",
    "💰 Financial Snapshot",
    "🏛️ Capital & Treasury",
])


# ══════════════════════════════════════════════════════════════════════
# TAB 1: Command Centre Snapshot
# ══════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("📊 Command Centre Snapshot")
    st.caption(
        "Cross-module health at a glance. Pulls from the same sources "
        "as `6_integrate.py` (the canonical Command Centre).")

    apps = _load_list("loan_applications.json")
    pipe = _load_list("pipeline.json")
    fd = _load_list("treasury_fd.json")
    legal = _load_list("legal_matters.json")
    comp = _load_list("compliance_cases.json")
    alerts = _load_list("smart_alerts.json")
    targets = _load_list("bank_targets.json")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        _kpi_box(
            "Loan Applications",
            f"{len(apps):,}",
            help_text="Total loan applications in flight")

    with c2:
        active_pipe = sum(1 for p in pipe
                           if p.get("status") not in ("Closed", "Lost"))
        _kpi_box(
            "Active Pipeline",
            f"{active_pipe:,}",
            help_text="Open opportunities in sales pipeline")

    with c3:
        critical_alerts = sum(
            1 for a in alerts
            if a.get("severity", "").lower() in ("critical", "high"))
        _kpi_box(
            "Critical Alerts",
            f"{critical_alerts:,}",
            help_text="High/critical-severity smart alerts")

    with c4:
        # Legal: count anything not in a final-completed state
        FINAL = {"completed", "closed", "settled", "withdrawn", "dismissed"}
        open_legal = sum(
            1 for m in legal
            if (m.get("status", "") or "").lower() not in FINAL)
        _kpi_box(
            "Open Legal Matters",
            f"{open_legal:,}",
            help_text="Active legal cases (any status that isn't completed/closed)")

    st.divider()

    c5, c6, c7, c8 = st.columns(4)

    with c5:
        open_comp = sum(
            1 for c in comp
            if c.get("status", "").lower() in ("open", "under_review"))
        _kpi_box(
            "Compliance Cases",
            f"{open_comp:,}",
            help_text="Cases under review or open")

    with c6:
        total_fd = sum(
            float(f.get("amount_kes", 0) or 0) for f in fd)
        _kpi_box(
            "Treasury FDs",
            f"{currency_symbol()} {total_fd / 1_000_000:.1f}M",
            help_text=f"Fixed deposits outstanding ({currency_symbol()} millions)")

    with c7:
        n_targets = len(targets)
        _kpi_box(
            "Active Targets",
            f"{n_targets:,}",
            help_text="Bank-level targets being tracked")

    with c8:
        _kpi_box(
            "Last Refresh",
            TODAY.strftime("%d %b %Y"),
            help_text="MD Cockpit data freshness (60s cache)")

    st.divider()
    st.info(
        "🔗 **Drill in:** Open the canonical Command Centre at "
        "**🔗 Integrate** (page 6) for the full cross-module view "
        "with break-downs by SBU, branch, RM, and region.")


# ══════════════════════════════════════════════════════════════════════
# TAB 2: BSC Summary
# ══════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("🎯 Balanced Scorecard — Strategic Summary")
    st.caption(
        "Top-level BSC perspective scores. Pulls the same data as "
        "`1_perform.py` (the canonical BSC).")

    bsc = _load_json_or_default("bsc_data.json", {})
    perspectives = bsc.get("perspectives", {}) if isinstance(bsc, dict) else {}

    if not perspectives:
        st.warning(
            "No BSC data available yet. Run the BSC integration "
            "engine via the canonical 🏆 Perform page.")
    else:
        cols = st.columns(min(4, len(perspectives)))
        for i, (pname, pdata) in enumerate(perspectives.items()):
            col = cols[i % len(cols)]
            with col:
                if isinstance(pdata, dict):
                    score = pdata.get("score", pdata.get("composite_score"))
                    target = pdata.get("target", 100)
                    if score is not None:
                        try:
                            score_v = float(score)
                            target_v = float(target) if target else 100.0
                            pct = (score_v / target_v * 100.0
                                    if target_v else 0.0)
                            _kpi_box(
                                pname,
                                f"{score_v:.1f}",
                                delta=f"{pct - 100:.1f}% vs target"
                                if pct != 100 else "on target",
                                help_text=f"Target: {target_v:.1f}")
                        except (TypeError, ValueError):
                            _kpi_box(pname, str(score))
                    else:
                        _kpi_box(pname, "—",
                                  help_text="No score yet")
                else:
                    _kpi_box(pname, str(pdata)[:20])

    st.divider()
    st.info(
        "🔗 **Drill in:** Open **🏆 Perform** (page 1) for the full "
        "BSC with KPI-level detail, cascade tracking, and historical "
        "trend by perspective.")

    # ──────────────────────────────────────────────────────────────────
    # v10.376 — Canonical PBT Performance Management bridge
    # First integration of canonical profitability (v10.370 G256/G257 +
    # v10.372 G253 ENFORCING) with Target Cascade (v10.371 G258). Read-only
    # join so the MD sees ONE authoritative number for PBT with full lineage
    # and 12-way drill into direct reports.
    # ──────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("##### 🧭 Canonical PBT — Cross-Module Integration (v10.376)")
    try:
        from utils.canonical_pbt_bsc_view import (
            get_md_pbt_summary, format_md_pbt_card,
        )
        _summary = get_md_pbt_summary(cbs_dir=None, period="2026")
        _c1, _c2, _c3, _c4 = st.columns(4)
        with _c1:
            _kpi_box(
                "Canonical PBT",
                f"KES {_summary.actual/1e9:,.2f}B",
                help_text="From compute_pbt_from_cbs (G250) — same number across all paths (G253)",
            )
        with _c2:
            _kpi_box(
                "Cascade Target",
                f"KES {_summary.target/1e9:,.2f}B",
                help_text=f"From target_cascade.json::300001|PBT|2026 (G258); 12 allocations",
            )
        with _c3:
            _kpi_box(
                "Achievement",
                f"{_summary.achievement_pct:.1f}%",
                delta=f"on track" if _summary.is_on_track() else "at risk (<90%)",
                help_text=f"Δ KES {_summary.delta/1e9:+,.2f}B",
            )
        with _c4:
            _kpi_box(
                "Cascaded",
                f"{len(_summary.allocations)} reports",
                help_text="MD's 12 direct reports with cascaded PBT allocations",
            )
        if _summary.note:
            st.warning(_summary.note)
        with st.expander(
            "📚 Lineage + body-system axes (Joshua's 'one body' framing)",
            expanded=False,
        ):
            st.markdown("**Canonical engine status (read-only join):**")
            for _gate, _desc in _summary.canonical_engine_status.items():
                st.markdown(f"- **{_gate}** — {_desc}")
            st.markdown("")
            st.markdown("**Body-system axes (this is one organ; PM framework is the body):**")
            for _axis, _desc in _summary.body_system_axes.items():
                st.markdown(f"- **{_axis.capitalize()}** — {_desc}")
        if _summary.allocations:
            with st.expander(
                f"📊 12 cascade allocations — drill into direct reports",
                expanded=False,
            ):
                import pandas as _pd
                _df = _pd.DataFrame(_summary.allocations)
                _df["amount_KES_B"] = _df["amount"].apply(lambda v: f"{v/1e9:,.3f}")
                _show = _df[["to_code", "to_name", "role", "profitability_tier",
                              "amount_KES_B"]]
                st.dataframe(_show, use_container_width=True, hide_index=True)
        st.caption(
            "Drill: open **🏆 Branch Ranking** (page 113, G255), "
            "**🎯 SBU Drill-down** (page 114, G254), "
            "**👥 Staff PBT (Role-Aware)** (page 120, v10.375 G261), or "
            "**🌳 Target Cascade** (page 12). Every path reconciles to the "
            "canonical PBT shown above (Σ identity locked by G256/G257)."
        )
    except Exception as _exc:
        st.warning(
            f"Canonical PBT bridge not available: "
            f"{type(_exc).__name__}: {_exc}. "
            f"The full BSC scores above are still authoritative — "
            f"this section is a v10.376 enhancement showing the integration."
        )


# ══════════════════════════════════════════════════════════════════════
# TAB 3: Strategic Initiatives RAG
# ══════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("🚀 Strategic Initiatives — Portfolio RAG")
    st.caption(
        "Status of strategic initiatives by pillar. Pulls from the "
        "same source as `83_strategy.py`.")

    initiatives = _load_list("strategic_initiatives.json")

    if not initiatives:
        st.warning(
            "No strategic initiatives logged yet. Add them via the "
            "canonical 🚀 Strategic Initiatives page.")
    else:
        # Aggregate by pillar + RAG (handle both `rag` and `rag_status` field names)
        by_pillar = {}
        for ini in initiatives:
            pillar = ini.get("pillar", "Uncategorized")
            rag = (
                ini.get("rag")
                or ini.get("rag_status")
                or ini.get("status", "")
                or ""
            ).lower()
            if pillar not in by_pillar:
                by_pillar[pillar] = {"R": 0, "A": 0, "G": 0,
                                       "total": 0}
            by_pillar[pillar]["total"] += 1
            if "red" in rag or rag == "r":
                by_pillar[pillar]["R"] += 1
            elif "amber" in rag or rag == "a" or "yellow" in rag:
                by_pillar[pillar]["A"] += 1
            elif "green" in rag or rag == "g":
                by_pillar[pillar]["G"] += 1

        if by_pillar:
            df = pd.DataFrame([
                {
                    "Pillar": p,
                    "🔴 Red": d["R"],
                    "🟡 Amber": d["A"],
                    "🟢 Green": d["G"],
                    "Total": d["total"],
                }
                for p, d in by_pillar.items()
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Aggregate counts
        total_r = sum(d["R"] for d in by_pillar.values())
        total_a = sum(d["A"] for d in by_pillar.values())
        total_g = sum(d["G"] for d in by_pillar.values())
        total = sum(d["total"] for d in by_pillar.values())

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _kpi_box("🔴 Red", f"{total_r}",
                      help_text="Off-track initiatives")
        with c2:
            _kpi_box("🟡 Amber", f"{total_a}",
                      help_text="At-risk initiatives")
        with c3:
            _kpi_box("🟢 Green", f"{total_g}",
                      help_text="On-track initiatives")
        with c4:
            _kpi_box("Total", f"{total}",
                      help_text="Total initiatives in portfolio")

    st.divider()
    st.info(
        "🔗 **Drill in:** Open **🚀 Strategic Initiatives** (page 83) "
        "for full portfolio with timelines, dependencies, KPI cascade, "
        "and Strategy Arc Engines.")


# ══════════════════════════════════════════════════════════════════════
# TAB 4: Board Papers
# ══════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("📋 Board Papers — Submission Tracker")
    st.caption(
        "Board paper status by committee. Pulls from `84_board.py`.")

    board_papers = _load_list("board_papers.json")

    if not board_papers:
        st.warning(
            "No board papers logged yet. Submit via the canonical "
            "📋 Board Papers page.")
    else:
        # Aggregate by committee + status
        from collections import Counter
        by_committee = Counter(
            p.get("committee", "Unspecified") for p in board_papers)
        by_status = Counter(
            (p.get("status", "Unknown") or "Unknown")
            for p in board_papers)

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**By Committee**")
            df_c = pd.DataFrame([
                {"Committee": k, "Papers": v}
                for k, v in sorted(by_committee.items(),
                                     key=lambda x: -x[1])
            ])
            st.dataframe(df_c, use_container_width=True,
                          hide_index=True)

        with c2:
            st.markdown("**By Status**")
            df_s = pd.DataFrame([
                {"Status": k, "Count": v}
                for k, v in sorted(by_status.items(),
                                     key=lambda x: -x[1])
            ])
            st.dataframe(df_s, use_container_width=True,
                          hide_index=True)

        # Action items overdue — actual data stores counts as top-level int fields
        # (action_items=int, actions_closed=int, actions_overdue=int per paper)
        overdue = sum(
            int(p.get("actions_overdue", 0) or 0)
            for p in board_papers
            if isinstance(p, dict)
        )
        closed = sum(
            int(p.get("actions_closed", 0) or 0)
            for p in board_papers
            if isinstance(p, dict)
        )

        st.divider()
        c3, c4, c5, c6 = st.columns(4)
        with c3:
            _kpi_box("Total Papers", f"{len(board_papers)}")
        with c4:
            _kpi_box("Committees Active",
                      f"{len(by_committee)}")
        with c5:
            _kpi_box(
                "Actions Closed",
                f"{closed}",
                help_text="Action items closed across all papers")
        with c6:
            _kpi_box(
                "Overdue Actions",
                f"{overdue}",
                delta="needs attention" if overdue else None,
                help_text="Action items past due date and not closed")

    st.divider()
    st.info(
        "🔗 **Drill in:** Open **📋 Board Papers** (page 84) for "
        "full submission history, action item follow-through, and "
        "committee-level filtering.")


# ══════════════════════════════════════════════════════════════════════
# TAB 5: Tier-1 Benchmarking
# ══════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("🏆 Tier-1 Benchmarking — Peer Position")
    st.caption(
        f"{bank_name()} vs Tier-1 peers (KCB, Equity, Co-op, NCBA) on "
        "key financial metrics. Pulls from `87_benchmarking.py`.")

    bench = _load_json_or_default("tier1_benchmarking.json", {})

    if not bench:
        st.warning(
            "No benchmarking data loaded. Refresh from the canonical "
            "🏆 Tier-1 Benchmarking page (data updated quarterly when "
            f"{regulator()} Bank Supervision reports release).")
    else:
        quarters = bench.get("quarters", []) or []
        our_bank = bench.get("our_bank") or bank_name()
        tier1_banks = bench.get("tier1_banks", []) or []
        quarterly = bench.get("quarterly_metrics", {}) or {}

        latest = quarters[-1] if quarters else None
        if latest:
            st.markdown(f"**Latest quarter:** `{latest}`  ·  "
                         f"**Our bank:** `{our_bank}`")

        if latest and quarterly:
            # Build a comparison table for the latest quarter across
            # selected key metrics. Each row = metric; columns = banks.
            key_metrics = [
                ("pbt_kes_b", f"PBT ({currency_symbol()} bn)", lambda v: f"{v:.1f}"),
                ("npl_pct", "NPL %", lambda v: f"{v:.1f}%"),
                ("car_pct", "CAR %", lambda v: f"{v:.1f}%"),
                ("lcr_pct", "LCR %", lambda v: f"{v:.0f}%"),
                ("nim_pct", "NIM %", lambda v: f"{v:.2f}%"),
                ("cir_pct", "CIR %", lambda v: f"{v:.1f}%"),
                ("roe_pct", "ROE %", lambda v: f"{v:.1f}%"),
            ]

            all_banks = [our_bank] + [
                b for b in tier1_banks if b != our_bank]

            rows = []
            for key, label, fmt in key_metrics:
                row = {"Metric": label}
                for bank in all_banks:
                    bank_data = quarterly.get(bank, {})
                    q_data = bank_data.get(latest, {}) if isinstance(
                        bank_data, dict) else {}
                    val = q_data.get(key) if isinstance(q_data, dict) else None
                    if val is not None:
                        try:
                            row[bank] = fmt(float(val))
                        except (TypeError, ValueError):
                            row[bank] = "—"
                    else:
                        row[bank] = "—"
                rows.append(row)

            if rows:
                df_bench = pd.DataFrame(rows)
                st.dataframe(df_bench, use_container_width=True,
                              hide_index=True)

            # Compute our bank's rank for PBT this quarter
            our_data = (quarterly.get(our_bank, {}) or {}).get(latest, {})
            if isinstance(our_data, dict) and "pbt_kes_b" in our_data:
                try:
                    our_pbt = float(our_data["pbt_kes_b"])
                    peer_pbts = []
                    for b in tier1_banks:
                        b_data = (quarterly.get(b, {}) or {}).get(latest, {})
                        if isinstance(b_data, dict) and "pbt_kes_b" in b_data:
                            peer_pbts.append(
                                (b, float(b_data["pbt_kes_b"])))
                    all_pbts = sorted(
                        [(our_bank, our_pbt)] + peer_pbts,
                        key=lambda x: -x[1])
                    rank = next(
                        (i + 1 for i, (bn, _) in enumerate(all_pbts)
                         if bn == our_bank), None)
                    leader = all_pbts[0][0] if all_pbts else "—"

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        _kpi_box(
                            "Our PBT Rank",
                            f"#{rank} of {len(all_pbts)}"
                            if rank else "—",
                            help_text=f"PBT ranking among tier-1 peers in {latest}")
                    with c2:
                        _kpi_box(
                            "Our PBT",
                            f"{currency_symbol()} {our_pbt:.1f}B")
                    with c3:
                        _kpi_box(
                            "PBT Leader",
                            leader,
                            help_text="Bank with highest PBT this quarter")
                except (TypeError, ValueError):
                    pass

    st.divider()
    st.info(
        "🔗 **Drill in:** Open **🏆 Tier-1 Benchmarking** (page 87) "
        "for full peer comparison across 15 metrics × 4 quarters, "
        "gap-to-leader analysis, and strategic theme tagging.")


# ══════════════════════════════════════════════════════════════════════
# TAB 6: Financial Snapshot (Mgmt Accounts + SBU + Revenue Assurance)
# ══════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("💰 Financial Snapshot")
    st.caption(
        "Top-level financial position. Pulls from `52_mgmt_accounts.py` "
        "(P&L + BS), `9_sbu.py` (SBU profitability), and "
        "`29_revenue_assurance.py` (leakage detection). All three are "
        "in the finance department per v10.210 reorganization.")

    mgmt_accounts = _load_json_or_default("mgmt_accounts.json", {})
    sbu_data = _load_list("sbu_pnl.json")
    leakage_log = _load_list("revenue_leakage.json")

    c1, c2, c3 = st.columns(3)

    with c1:
        # PBT (Profit Before Tax) — pulled from income_statement.pbt
        pbt_actual = None
        pbt_budget = None
        if mgmt_accounts and isinstance(mgmt_accounts, dict):
            inc = mgmt_accounts.get("income_statement", {}) or {}
            pbt_block = inc.get("pbt", {}) if isinstance(inc, dict) else {}
            if isinstance(pbt_block, dict):
                pbt_actual = pbt_block.get("actual_m")
                pbt_budget = pbt_block.get("budget_m")
        if pbt_actual is not None:
            try:
                pbt_v = float(pbt_actual)
                if pbt_budget is not None:
                    delta_m = pbt_v - float(pbt_budget)
                    delta_str = (f"+{currency_symbol()} {delta_m:.0f}M vs budget"
                                  if delta_m >= 0
                                  else f"{currency_symbol()} {delta_m:.0f}M vs budget")
                    _kpi_box("PBT (current period)",
                              f"{currency_symbol()} {pbt_v:.0f}M",
                              delta=delta_str,
                              help_text="Profit Before Tax — actual vs budget")
                else:
                    _kpi_box("PBT (current period)",
                              f"{currency_symbol()} {pbt_v:.0f}M",
                              help_text="Profit Before Tax")
            except (TypeError, ValueError):
                _kpi_box("PBT", str(pbt_actual))
        else:
            _kpi_box("PBT", "—",
                      help_text="No mgmt accounts P&L data yet")

    with c2:
        # SBU count
        n_sbus = len(sbu_data)
        if n_sbus:
            profitable = sum(
                1 for s in sbu_data
                if isinstance(s, dict)
                and float(s.get("net_profit",
                                 s.get("profit", 0)) or 0) > 0)
            _kpi_box(
                "SBUs Profitable",
                f"{profitable} / {n_sbus}",
                help_text="SBUs with positive net profit")
        else:
            _kpi_box("SBUs Profitable", "—",
                      help_text="No SBU P&L data yet")

    with c3:
        # Revenue leakage
        n_leakages = len(leakage_log)
        if n_leakages:
            total_leak = sum(
                float(l.get("amount", 0) or 0)
                for l in leakage_log
                if isinstance(l, dict))
            _kpi_box(
                "Revenue Leakage",
                f"{currency_symbol()} {total_leak / 1_000_000:.1f}M"
                if total_leak else f"{n_leakages} cases",
                delta=f"{n_leakages} cases",
                help_text="Detected revenue leakage YTD")
        else:
            _kpi_box("Revenue Leakage", "—",
                      help_text="No leakage data yet")

    st.divider()

    # SBU table preview
    if sbu_data:
        st.markdown("**SBU Profitability — Top 10 by net contribution**")
        df_sbu_rows = []
        for s in sbu_data[:50]:
            if isinstance(s, dict):
                df_sbu_rows.append({
                    "SBU": s.get("name", s.get("sbu", "—")),
                    f"Revenue ({currency_symbol()} M)":
                        round(float(s.get("revenue", 0) or 0)
                                / 1_000_000, 2),
                    f"Net Profit ({currency_symbol()} M)":
                        round(float(s.get("net_profit",
                                            s.get("profit", 0)) or 0)
                                / 1_000_000, 2),
                })
        if df_sbu_rows:
            df_sbu = pd.DataFrame(df_sbu_rows)
            df_sbu = df_sbu.sort_values(
                f"Net Profit ({currency_symbol()} M)", ascending=False).head(10)
            st.dataframe(df_sbu, use_container_width=True,
                          hide_index=True)

    st.info(
        "🔗 **Drill in:** Open **💰 Management Accounts** (page 52) for "
        "full P&L + Balance Sheet + Trend + Ratios + Finance Arc Engines. "
        "Open **📊 SBU P&L** (page 9) for per-SBU detail. "
        "Open **🛡️ Revenue Assurance** (page 29) for leakage register "
        "+ Revenue Assurance Arc Engines.")


# ══════════════════════════════════════════════════════════════════════
# TAB 7: Capital & Treasury
# ══════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("🏛️ Capital Adequacy & Treasury Position")
    st.caption(
        "Capital ratios + liquidity position. Pulls from "
        "`25_treasury.py` (Treasury dashboard) and capital data files.")

    capital = _load_json_or_default("capital_adequacy.json", {})
    liquidity = _load_json_or_default("liquidity_metrics.json", {})

    c1, c2, c3, c4 = st.columns(4)

    def _ratio_box(col, label, value, target=None, help_text=None):
        with col:
            if value is None:
                _kpi_box(label, "—", help_text=help_text)
                return
            try:
                v = float(value)
                if target is not None:
                    delta_str = (
                        f"+{v - float(target):.1f}pp vs target"
                        if v >= float(target)
                        else f"{v - float(target):.1f}pp vs target")
                    _kpi_box(label, f"{v:.1f}%",
                              delta=delta_str, help_text=help_text)
                else:
                    _kpi_box(label, f"{v:.1f}%",
                              help_text=help_text)
            except (TypeError, ValueError):
                _kpi_box(label, str(value), help_text=help_text)

    if capital:
        car = capital.get("total_capital_ratio",
                            capital.get("car"))
        cet1 = capital.get("cet1_ratio")
        tier1 = capital.get("tier1_ratio")

        _ratio_box(c1, "Total CAR", car, target=14.5,
                    help_text=f"{regulator()} minimum: 14.5%")
        _ratio_box(c2, "Tier 1", tier1, target=10.5,
                    help_text=f"{regulator()} minimum: 10.5%")
        _ratio_box(c3, "CET1", cet1, target=8.0,
                    help_text="Internal target: 8.0%")
    else:
        with c1:
            _kpi_box("Total CAR", "—",
                      help_text="No capital data yet")
        with c2:
            _kpi_box("Tier 1", "—")
        with c3:
            _kpi_box("CET1", "—")

    if liquidity:
        lcr = liquidity.get("lcr",
                             liquidity.get("liquidity_coverage"))
        _ratio_box(c4, "LCR", lcr, target=100.0,
                    help_text=f"{regulator()} minimum: 100%")
    else:
        with c4:
            _kpi_box("LCR", "—",
                      help_text="No liquidity data yet")

    st.divider()

    # Treasury holdings summary
    fd_data = _load_list("treasury_fd.json")
    if fd_data:
        n_fd = len(fd_data)
        total_fd = sum(
            float(f.get("amount_kes", 0) or 0) for f in fd_data
            if isinstance(f, dict))
        c5, c6 = st.columns(2)
        with c5:
            _kpi_box(
                "Active FD Count",
                f"{n_fd:,}",
                help_text="Fixed deposits outstanding")
        with c6:
            _kpi_box(
                "FD Total Value",
                f"{currency_symbol()} {total_fd / 1_000_000_000:.2f}B",
                help_text="Total fixed deposit book")

    st.info(
        "🔗 **Drill in:** Open **🏛️ Treasury** (page 25) for full ALM "
        "+ Capital + Liquidity + Treasury Arc Engines. Open **📐 Stress "
        "Testing** (page 35) for Risk Arc Engines (VaR, IRB, SMA, "
        "Stressed LCR).")


# ──────────────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "📖 **MD Cockpit design notes:** Read-only by design — drill into "
    "the canonical pages to act. Department: strategy_performance "
    "(alongside BSC, Board Papers, Tier-1 Benchmarking, and Strategic "
    "Initiatives). Each tab pulls from the same data sources as its "
    "canonical page; no replicated logic. v10.214 introduced. "
    f"Last viewed: {datetime.now().strftime('%H:%M:%S')}.")

# v10.465 — Phase 4 WF4 operational output (admin re-homed page)
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()



# v10.468 — MD Chief Review Drill-Down (Joshua doctrine: "MD can review
# actuals and same down" — drill from MD → chiefs → managers → officers
# via reports_to hierarchy)

import json as _v468_json
from pathlib import Path as _v468_Path

with st.expander("👁️ MD Chief Review — drill into each chief's BSC + cascade",
                 expanded=False):
    st.caption(
        "Per Joshua mantra: MD reviews each chief's BSC actuals; same "
        "drill-down works through Chief → Manager → Officer via "
        "reports_to hierarchy."
    )

    _v468_data = _v468_Path(__file__).parent.parent / "data"
    try:
        _v468_users = _v468_json.loads(
            (_v468_data / "users.json").read_text(encoding="utf-8")
        )
        if isinstance(_v468_users, dict):
            _v468_users = _v468_users.get(
                "users", list(_v468_users.values())
            )
        _v468_bsc = _v468_json.loads(
            (_v468_data / "bsc_scores.json").read_text(encoding="utf-8")
        )

        # Find chiefs reporting to MD (300001)
        _v468_chiefs = [
            u for u in _v468_users
            if isinstance(u, dict)
            and u.get("reports_to") == "300001"
            and u.get("active", True)
        ]
        st.write(f"**Chiefs reporting to MD: {len(_v468_chiefs)}**")

        # Build BSC lookup
        _v468_latest_bsc = {}
        for r in _v468_bsc:
            if not isinstance(r, dict):
                continue
            sc = str(r.get("staff_code", ""))
            q = r.get("quarter", "")
            if sc and q:
                existing = _v468_latest_bsc.get(sc)
                if existing is None or q > existing.get("quarter", ""):
                    _v468_latest_bsc[sc] = r

        # Show each chief with their latest BSC
        import pandas as _v468_pd
        _v468_chief_rows = []
        for c in _v468_chiefs:
            sc = str(c.get("staff_code", ""))
            bsc = _v468_latest_bsc.get(sc, {})
            # Count direct reports
            _v468_direct_reports = sum(
                1 for u in _v468_users
                if isinstance(u, dict)
                and str(u.get("reports_to", "")) == sc
            )
            _v468_chief_rows.append({
                "Chief": c.get("full_name", "?"),
                "Role": c.get("role", "?")[:38],
                "Latest BSC": (f"{bsc.get('total_score', 0):.2f}"
                              if bsc else "—"),
                "Quarter": bsc.get("quarter", "—"),
                "Rating": bsc.get("rating", "—"),
                "Direct reports": _v468_direct_reports,
            })
        _v468_chief_rows.sort(
            key=lambda r: (-float(r["Latest BSC"]) if r["Latest BSC"] != "—" else 0)
        )
        st.dataframe(
            _v468_pd.DataFrame(_v468_chief_rows),
            use_container_width=True,
            hide_index=True,
        )

        # Chief drill-down picker
        _v468_picked = st.selectbox(
            "Drill into a chief's team:",
            options=["— Select chief —"]
                    + [f"{c.get('full_name','?')} ({c.get('staff_code','')})"
                       for c in _v468_chiefs],
            key="v468_md_drill_picker",
        )
        if _v468_picked and "— Select" not in _v468_picked:
            _v468_picked_code = _v468_picked.split("(")[-1].rstrip(")")
            _v468_team = [
                u for u in _v468_users
                if isinstance(u, dict)
                and str(u.get("reports_to", "")) == _v468_picked_code
                and u.get("active", True)
            ]
            st.write(f"**Direct reports to {_v468_picked.split(' (')[0]}: {len(_v468_team)}**")
            _v468_team_rows = []
            for member in _v468_team[:40]:
                sc = str(member.get("staff_code", ""))
                bsc = _v468_latest_bsc.get(sc, {})
                _v468_team_rows.append({
                    "Staff": member.get("full_name", "?"),
                    "Role": member.get("role", "?")[:35],
                    "Latest BSC": (f"{bsc.get('total_score', 0):.2f}"
                                  if bsc else "—"),
                    "Rating": bsc.get("rating", "—"),
                })
            _v468_team_rows.sort(
                key=lambda r: (-float(r["Latest BSC"]) if r["Latest BSC"] != "—" else 0)
            )
            st.dataframe(
                _v468_pd.DataFrame(_v468_team_rows),
                use_container_width=True,
                hide_index=True,
            )
    except Exception as exc:
        st.warning(f"MD drill-down unavailable: {exc}")

# v10.468 — explicit st.button literal (Phase 4 WF4)
if st.button("🔍 Refresh MD chief review",
            key="v468_md_refresh"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()
