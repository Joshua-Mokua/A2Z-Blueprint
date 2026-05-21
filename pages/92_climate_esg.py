"""pages/92_climate_esg.py — v10.9 Climate/ESG Dashboard

Surfaces all 4 v10.6-v10.9 climate engines:
  - utils/esg_intelligence (v10.6) — IFRS S1/S2 + KGFT + governance
  - utils/climate_risk (v10.7) — physical + transition + TNFD
  - utils/climate_ecl_adjustment (v10.8) — climate-adjusted ECL + scenarios
  - utils/esg_reporting_outputs (v10.9) — KGFT/CRDF reports + greenwashing

Read-only board-ready dashboard. Data input via existing admin panels.
"""
from __future__ import annotations
import json
from decimal import Decimal
from pathlib import Path

import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

import pandas as pd

from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access
from utils.core_audit import audit_log

# v10.6-v10.9 engines
from utils.esg_intelligence import (
    ESGIntelligenceEngine,
    IFRS_S2_DISCLOSURES,
    IFRS_S1_S2_MANDATORY_DEADLINE,
    CRDF_FIRST_REPORTING_PERIOD,
    KGFT_GREEN_CATEGORIES,
    CLIMATE_GOVERNANCE_REQUIRED_ROLES,
    CLIMATE_GOVERNANCE_REQUIRED_PRACTICES,
    GreenAssetClassification,
    classify_green_asset,
    compute_portfolio_emissions,
    validate_climate_governance,
    IFRSS2Disclosure,
)
from utils.climate_risk import (
    ClimateRiskEngine,
    NGFSScenario,
    NGFS_CARBON_PRICE_2030_USD_PER_TCO2E,
    SECTOR_BASELINE_VULNERABILITY,
    SECTOR_TRANSITION_INTENSITY,
    TNFD_LEAP_STAGES,
    TNFD_BIOMES_KENYA,
)
from utils.climate_ecl_adjustment import (
    ClimateECLEngine,
    StressScenarioType,
    STRESS_HORIZONS_YEARS,
    DEFAULT_IFRS9_SCENARIO_WEIGHTS,
)
from utils.esg_reporting_outputs import (
    ESGReportingOutputsEngine,
    KGFT_REPORT_SECTIONS,
    CRDF_PILLARS,
    CRDF_DISCLOSURES,
    GREENWASHING_RED_FLAGS,
)

require_access("risk.climate_esg")

um, ud, uname, *_ = load_shared_state()
role = ud.get("role", "")
is_board = any(x in role for x in ("Board", "Director", "Chief", "MD", "Head"))
is_compliance = any(x in role for x in ("Compliance", "Risk", "ESG", "Climate"))

st.title("🌍 Climate/ESG Dashboard")
st.caption(
    f"IFRS S1/S2 mandatory: **{IFRS_S1_S2_MANDATORY_DEADLINE}** · "
    f"CRDF first period: **{CRDF_FIRST_REPORTING_PERIOD}** · "
    f"Active engines: v10.6 (ESG core) · v10.7 (climate risk) · "
    f"v10.8 (climate-adjusted ECL) · v10.9 (KGFT/CRDF/greenwashing)"
)

audit_log(uname, "view", "climate_esg_dashboard")

tab_overview, tab_ifrs, tab_kgft, tab_risk, tab_ecl, tab_governance, tab_greenwashing = st.tabs([
    "📊 Overview",
    "📋 IFRS S2 Status",
    "🌱 KGFT Green Book",
    "🔥 Risk Heat Map",
    "💰 Climate-Adjusted ECL",
    "🏛️ Governance",
    "🚫 Greenwashing Controls",
])


# ════════════════════════════════════════════════════════════════════════
# Tab: Overview
# ════════════════════════════════════════════════════════════════════════

with tab_overview:
    st.subheader("Climate/ESG Readiness — Board Summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "IFRS S1/S2 deadline",
        IFRS_S1_S2_MANDATORY_DEADLINE,
        help="Mandatory disclosure date for Public Interest Entities in Kenya")
    col2.metric(
        "CRDF first period",
        CRDF_FIRST_REPORTING_PERIOD,
        help="CBK CRDF first annual reporting period end")
    col3.metric(
        "Climate engines active",
        "4",
        help="v10.6 ESG · v10.7 Risk · v10.8 ECL · v10.9 Reporting")
    col4.metric(
        "Standards implemented",
        "13 / 13",
        help="Climate/ESG arc fully implemented across v10.6-v10.9")

    st.markdown("---")
    st.markdown("##### Engines & their standards")

    engines_df = pd.DataFrame([
        {"Batch": "v10.6", "Engine": "esg_intelligence",
          "Standards": "ENH-CLI-01, 02, 08, 09, 11",
          "Coverage": "IFRS S1/S2 + KGFT classification + Scope 1/2/3 + governance"},
        {"Batch": "v10.7", "Engine": "climate_risk",
          "Standards": "ENH-CLI-05, 06, 10",
          "Coverage": "Physical + transition + TNFD biodiversity"},
        {"Batch": "v10.8", "Engine": "climate_ecl_adjustment",
          "Standards": "ENH-CLI-07, 12",
          "Coverage": "Climate-adjusted ECL + scenario stress tests (IFRS 9 §5.5.17)"},
        {"Batch": "v10.9", "Engine": "esg_reporting_outputs",
          "Standards": "ENH-CLI-03, 04, 13",
          "Coverage": "KGFT reports + CRDF reports + greenwashing controls"},
    ])
    st.dataframe(engines_df, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════
# Tab: IFRS S2 Status
# ════════════════════════════════════════════════════════════════════════

with tab_ifrs:
    st.subheader("IFRS S2 — Climate-Related Disclosures Coverage")
    st.caption(
        "21 mandatory disclosures across Governance / Strategy / "
        "Risk Management / Metrics & Targets pillars (IFRS S2 §6-§37).")

    pillar_map = {
        "Governance (§6-§7)": ("S2_GOV_BOARD_OVERSIGHT", "S2_GOV_MANAGEMENT_ROLE"),
        "Strategy (§8-§22)": tuple(d for d in IFRS_S2_DISCLOSURES if d.startswith("S2_STR_")),
        "Risk Management (§23-§27)": tuple(d for d in IFRS_S2_DISCLOSURES if d.startswith("S2_RM_")),
        "Metrics & Targets (§28-§37)": tuple(d for d in IFRS_S2_DISCLOSURES if d.startswith("S2_MT_")),
    }

    rows = []
    for pillar, ds in pillar_map.items():
        rows.append({
            "Pillar": pillar,
            "Disclosures required": len(ds),
            "Examples": ", ".join(ds[:2])
                            + (f" + {len(ds)-2} more" if len(ds) > 2 else ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.info(
        "📌 The engine `assess_ifrs_s2_compliance()` returns "
        "`READY` / `ON_TRACK` / `AT_RISK` / `URGENT_ACTION_REQUIRED` "
        "based on completeness percentage. Disclosures are recorded "
        "via the Compliance admin panel.")


# ════════════════════════════════════════════════════════════════════════
# Tab: KGFT Green Book
# ════════════════════════════════════════════════════════════════════════

with tab_kgft:
    st.subheader("Kenya Green Finance Taxonomy — Green Book Position")
    st.caption(
        "8 KGFT green categories. ALIGNED requires DNSH (Do No "
        "Significant Harm) + at least one eligibility dimension.")

    cats_df = pd.DataFrame([
        {"#": i + 1, "KGFT Green Category": c.replace("_", " ").title()}
        for i, c in enumerate(KGFT_GREEN_CATEGORIES)
    ])
    st.dataframe(cats_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### Alignment levels (cascade)")
    st.markdown("""
    - **ALIGNED** — meets KGFT category + ≥1 eligibility dimension + DNSH verified
    - **TRANSITIONING** — on credible path to alignment
    - **ENABLING** — enables others' alignment (e.g., grid infrastructure for renewables)
    - **NON_ALIGNED** — does not meet criteria
    """)

    if is_compliance or is_board:
        st.success(
            "💡 Generate KGFT report via "
            "`ESGReportingOutputsEngine.generate_kgft()` — outputs "
            f"all 6 sections: {', '.join(s.replace('_', ' ').title() for s in KGFT_REPORT_SECTIONS)}.")


# ════════════════════════════════════════════════════════════════════════
# Tab: Risk Heat Map
# ════════════════════════════════════════════════════════════════════════

with tab_risk:
    st.subheader("Climate Risk — Sector Heat Map")
    st.caption(
        "Sector-level baseline vulnerability (physical) + "
        "transition intensity (NGFS v4 + ECB STS 2022).")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Physical risk vulnerability by sector")
        df_phys = pd.DataFrame([
            {"Sector": s.replace("_", " ").title(), "Vulnerability (0-100)": float(v)}
            for s, v in sorted(SECTOR_BASELINE_VULNERABILITY.items(),
                                 key=lambda kv: kv[1], reverse=True)
        ])
        st.dataframe(df_phys, use_container_width=True, hide_index=True, height=400)

    with col2:
        st.markdown("##### Transition risk intensity by sector")
        df_tr = pd.DataFrame([
            {"Sector": s.replace("_", " ").title(), "Intensity (0-100)": float(v)}
            for s, v in sorted(SECTOR_TRANSITION_INTENSITY.items(),
                                 key=lambda kv: kv[1], reverse=True)
        ])
        st.dataframe(df_tr, use_container_width=True, hide_index=True, height=400)

    st.markdown("---")
    st.markdown("##### NGFS Carbon Price (2030 forecast)")
    df_carbon = pd.DataFrame([
        {"NGFS Scenario": s.value.replace("_", " "),
          "Carbon Price (USD/tCO2e)": float(p)}
        for s, p in NGFS_CARBON_PRICE_2030_USD_PER_TCO2E.items()
    ])
    st.dataframe(df_carbon, use_container_width=True, hide_index=True)

    st.info(
        f"**TNFD biodiversity** (ENH-CLI-10): LEAP framework "
        f"({' → '.join(TNFD_LEAP_STAGES)}). "
        f"Kenya biomes covered: {len(TNFD_BIOMES_KENYA)}.")


# ════════════════════════════════════════════════════════════════════════
# Tab: Climate-Adjusted ECL
# ════════════════════════════════════════════════════════════════════════

with tab_ecl:
    st.subheader("Climate-Adjusted ECL — IFRS 9 §5.5.17 Forward-Looking")
    st.caption(
        "Multipliers applied to base ECL: PD × LGD × EAD. "
        "Probability-weighted across ≥3 scenarios per IFRS 9 §5.5.4.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Min scenarios required", "3", help="IFRS 9 §5.5.4")
    col2.metric("Multiplier range", "[1.0, 3.0]",
                  help="Climate adds risk, never subtracts")
    col3.metric("Stress horizons", ", ".join(f"{h}y" for h in STRESS_HORIZONS_YEARS))

    st.markdown("---")
    st.markdown("##### Default IFRS 9 scenario weights")
    df_w = pd.DataFrame([
        {"Scenario": k, "Weight": float(v)}
        for k, v in DEFAULT_IFRS9_SCENARIO_WEIGHTS.items()
    ])
    st.dataframe(df_w, use_container_width=True, hide_index=True)

    st.markdown("##### Multiplier formulas")
    st.markdown("""
    - **PD multiplier** = 1 + (0.4 × physical + 0.6 × transition) / 100 × horizon_factor
    - **LGD multiplier** = 1 + physical × 0.5 / 100 (× 1.5 for real estate)
    - **EAD multiplier** = 1 + transition × 0.2 / 100 (× 1.5 for fossils)
    - **horizon_factor** = linear from 1.0 at 5y → 2.0 at 30y
    """)

    if is_board:
        st.warning(
            "⚠️ Climate-adjusted ECL is **Cat A (financial calculation)** — "
            "directly affects balance-sheet provisions. Run via "
            "`ClimateECLEngine.run_three_scenarios()`. Output is "
            "audited by gate G120 in v10.10.")


# ════════════════════════════════════════════════════════════════════════
# Tab: Governance
# ════════════════════════════════════════════════════════════════════════

with tab_governance:
    st.subheader("Climate Governance — IFRS S2 §6-§7 + CBK CRMF Pillar 1")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Required roles (5)")
        for r in CLIMATE_GOVERNANCE_REQUIRED_ROLES:
            st.markdown(f"- {r.replace('_', ' ').title()}")

    with col2:
        st.markdown("##### Required practices (6)")
        for p in CLIMATE_GOVERNANCE_REQUIRED_PRACTICES:
            st.markdown(f"- {p.replace('_', ' ').title()}")

    st.markdown("---")
    st.info(
        "🏛️ Governance assessment via "
        "`validate_climate_governance(roles_in_place, practices_in_place)`. "
        "All 11 items required for `is_compliant() == True`.")


# ════════════════════════════════════════════════════════════════════════
# Tab: Greenwashing Controls
# ════════════════════════════════════════════════════════════════════════

with tab_greenwashing:
    st.subheader("Greenwashing Risk Controls — Claim Verification")
    st.caption(
        "Heuristic + KGFT-cross-check verification of green claims. "
        "Risk levels: LOW / MEDIUM / HIGH.")

    st.markdown("##### Red flags checked")
    df_flags = pd.DataFrame([
        {"#": i + 1, "Red flag": f.replace("_", " ").title()}
        for i, f in enumerate(GREENWASHING_RED_FLAGS)
    ])
    st.dataframe(df_flags, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### Risk level cascade")
    st.markdown("""
    - **LOW** — no red flags, KGFT-supported claim
    - **MEDIUM** — 1-2 red flags
    - **HIGH** — ≥3 flags **OR** claim inconsistent with KGFT classification
    """)

    if is_compliance:
        st.success(
            "💡 Verify claims via "
            "`verify_green_claim(claim, kgft_classifications=...)`. "
            "Engine method: `ESGReportingOutputsEngine.verify_all_claims()`.")


# ════════════════════════════════════════════════════════════════════════
# Sidebar: Quick reference
# ════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### 🌍 Climate/ESG Quick Ref")
    st.markdown(f"""
    **Active engines (v10.6-v10.9):**
    - `utils.esg_intelligence` (v10.6)
    - `utils.climate_risk` (v10.7)
    - `utils.climate_ecl_adjustment` (v10.8)
    - `utils.esg_reporting_outputs` (v10.9)

    **Standards:** 13/13 active.

    **Next:** v10.10 G120 audit gate locks the arc.

    **Key dates:**
    - IFRS S1/S2: {IFRS_S1_S2_MANDATORY_DEADLINE}
    - CRDF first period: {CRDF_FIRST_REPORTING_PERIOD}
    """)

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()

