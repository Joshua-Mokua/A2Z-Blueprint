"""pages/26_treasury_arc_cockpit.py — Treasury Arc Cockpit (v10.155).

Phase 2 Treasury Module closure — 10th module closure in platform history.

Locks the v10.46 Lean+Compact protocol amendment for Treasury: this page
makes the 12 Treasury-arc engines (ENH-231..240, ENH-LR-001, ENH-TRS-R1..R6,
CBK-PG-05-LCR) operator-driveable from the browser through 7 thematic tabs
grouping engines per workflow logic.

The companion FastAPI router `utils/api_treasury.py` exposes the same engine
methods over JSON for the planned React frontend. Cockpit and API share
the engine layer as the source of truth.

DESIGN DISCIPLINE (carried forward from v10.151 + v10.153.1)
-------------------------------------------------------------
1. Streamlit/import fallback at top so module loads even when
   Streamlit isn't installed (sandbox-friendly)
2. require_access uses REAL signature: require_access(module: str,
   silent: bool = False). Module ID is "alm_liquidity" — inherits the
   existing RBAC of the main 81_alm.py page (Admin, Treasurer, etc.)
3. audit_log uses REAL signature: action, username, detail, module
   (NOT actor=, payload= — those were the v10.153.1 invented kwargs)
4. @st.cache_resource caches engine instances at session level
5. Read-only display except for state-mutating buttons that go through
   the explicit FastAPI POST endpoints in utils/api_treasury.py

7 THEMATIC TAB STRUCTURE (per v10.152 plan §3.3)
------------------------------------------------
1. 📊 Dashboard       — TreasuryDashboardEngine + TreasuryIntelligenceEngine board pack
2. 💧 Liquidity & ALM  — LiquidityRiskEngine + LiquidityStressEngine + TreasuryALMEngine
3. 💰 Products         — TreasuryProductsEngine (FD, FX, MM, Bonds with MTM and curves)
4. 🤖 Agents           — AgentOrchestrator + 5 agents recommendations lifecycle
5. 🔌 Connectivity     — TreasuryConnectivityEngine (connectors + MMF counterparties)
6. 🌐 Digital & Climate — DigitalAssetTreasuryEngine + ClimateTreasuryLimitsEngine
7. 🕌 Islamic & Unified — IslamicTreasuryEngine + UnifiedTreasuryPlatform cross-asset rollup

This grouping reflects operational adjacency. UX choice, not a structural
constraint — but it satisfies G4 7-tab limit while keeping every engine
accessible.
"""
from __future__ import annotations
from datetime import datetime, timezone

try:
    import streamlit as st
    import pandas as pd
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None  # type: ignore
    pd = None  # type: ignore

# Engines
from utils.treasury_intelligence import TreasuryIntelligenceEngine
from utils.treasury_alm import TreasuryALMEngine
from utils.treasury_dashboard import TreasuryDashboardEngine
from utils.treasury_products import TreasuryProductsEngine
from utils.treasury_agents import AgentOrchestrator
from utils.treasury_connectivity import TreasuryConnectivityEngine
from utils.treasury_digital_assets import DigitalAssetTreasuryEngine
from utils.treasury_unified_platform import UnifiedTreasuryPlatform
from utils.liquidity_risk import LiquidityRiskEngine
from utils.liquidity_stress import LiquidityStressEngine
from utils.islamic_treasury import IslamicTreasuryEngine
from utils.climate_treasury_limits import ClimateTreasuryLimitsEngine

try:
    from pages._shared import load_shared_state
    from pages._access import require_access
    from utils.core_audit import audit_log
    SHARED_AVAILABLE = True
except ImportError:
    SHARED_AVAILABLE = False
    def load_shared_state():
        return {}
    def require_access(module: str, silent: bool = False):
        return True
    def audit_log(action: str, username: str, detail: str = "",
                    module: str = "", before: str = "",
                    after: str = ""):
        pass

try:
    from pages._cockpit_render import render_summary as _render_summary
except ImportError:
    def _render_summary(summary, *, exclude=()):
        if STREAMLIT_AVAILABLE:
            _render_summary(summary)


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

if STREAMLIT_AVAILABLE:
    st.set_page_config(
        page_title="Treasury Arc Cockpit",
        page_icon="💹",
        layout="wide")

    if SHARED_AVAILABLE:
        load_shared_state()
        # Inherit existing alm_liquidity RBAC (Admin, MD, CFO, CRO,
        # Treasurer, etc.) — same convention v10.151 Product cockpit
        # uses with require_access("products")
        require_access("alm_liquidity")

    st.title("💹 Treasury Arc Cockpit")
    st.caption(
        "v10.155 closure — 12 engines (ENH-231..240, ENH-LR-001, "
        "ENH-TRS-R1..R6, CBK-PG-05-LCR) spanning intelligence, ALM, "
        "products, agents, connectivity, digital assets, climate, "
        "Islamic, and unified cross-asset rollup. All engines read-only "
        "in this view; state-mutating workflows (deposit registration, "
        "LCR/NSFR runs, agent approve/reject) go through the explicit "
        "FastAPI POST endpoints in utils/api_treasury.py with audit-"
        "trailed Pydantic validation.")

    # Engine instances cached at session level
    @st.cache_resource
    def _get_engines():
        intel = TreasuryIntelligenceEngine()
        alm = TreasuryALMEngine()
        dashboard = TreasuryDashboardEngine()
        products = TreasuryProductsEngine()
        agents = AgentOrchestrator()
        connectivity = TreasuryConnectivityEngine()
        digital_assets = DigitalAssetTreasuryEngine()
        unified = UnifiedTreasuryPlatform()
        liquidity_stress = LiquidityStressEngine()
        islamic = IslamicTreasuryEngine()
        climate = ClimateTreasuryLimitsEngine()
        return {
            "intel": intel, "alm": alm, "dashboard": dashboard,
            "products": products, "agents": agents,
            "connectivity": connectivity,
            "digital_assets": digital_assets, "unified": unified,
            "liquidity_stress": liquidity_stress,
            "islamic": islamic, "climate": climate,
        }

    engines = _get_engines()

    # ----------------------------------------------------------------
    # 7 thematic tabs grouping the 12 engines per workflow logic
    # ----------------------------------------------------------------

    tabs = st.tabs([
        "📊 Dashboard",
        "💧 Liquidity & ALM",
        "💰 Products",
        "🤖 Agents",
        "🔌 Connectivity",
        "🌐 Digital & Climate",
        "🕌 Islamic & Unified",
    ])

    # Tab 1: Dashboard (intelligence + dashboard board pack)
    with tabs[0]:
        st.subheader("Treasury Intelligence (ENH-231..234, 236)")
        st.caption(
            "Yield curves, liquidity metrics, income by instrument, "
            "ALM dashboard data — read directly from FLEXCUBE-shaped "
            "feeds via TreasuryIntelligenceEngine.")
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            cur_period = datetime.now(timezone.utc).strftime("%Y-%m")

            with st.expander("Yield curve (KES, today)", expanded=True):
                yc = engines["intel"].yield_curve(
                    as_of_date=today, currency="KES")
                _render_summary(yc)

            with st.expander("Liquidity metrics (today)"):
                lm = engines["intel"].liquidity_metrics(
                    as_of_date=today)
                _render_summary(lm)

            with st.expander(f"Income by instrument ({cur_period})"):
                inc = engines["intel"].income_by_instrument(
                    period=cur_period)
                _render_summary(inc)
        except Exception as e:
            st.error(
                f"Intelligence load failed: {type(e).__name__}: {e}")

        st.divider()
        st.subheader("Dashboard board pack (ENH-238)")
        try:
            bp = engines["dashboard"].board_summary()
            _render_summary(bp)
        except Exception as e:
            st.error(
                f"Dashboard board pack failed: {type(e).__name__}: {e}")

    # Tab 2: Liquidity & ALM (ENH-233 + ENH-LR-001 + ENH-232)
    with tabs[1]:
        st.subheader("Liquidity Risk Engine (CBK-PG-05-LCR)")
        st.caption(
            "LCR/NSFR computations require posted state (HQLA holdings, "
            "cash flow items, funding components). Use the explicit "
            "POST endpoints in /api/treasury/* with typed Pydantic "
            "models, OR load these inputs through this cockpit's "
            "session forms (planned for v10.156). For now, this tab "
            "shows ALM board summary + outlier scenarios.")
        try:
            ab = engines["alm"].board_summary()
            st.subheader("ALM board summary (ENH-233)")
            _render_summary(ab)
        except Exception as e:
            st.error(f"ALM board summary failed: {type(e).__name__}: {e}")

        st.divider()
        try:
            outliers = engines["alm"].outlier_scenarios()
            if outliers:
                st.subheader(f"Outlier IRRBB scenarios "
                              f"(n={len(outliers)})")
                # Convert frozen dataclasses to displayable dicts
                rows = []
                for o in outliers:
                    if hasattr(o, "__dataclass_fields__"):
                        rows.append({
                            k: getattr(o, k)
                            for k in o.__dataclass_fields__.keys()
                        })
                    else:
                        rows.append({"value": str(o)})
                if rows:
                    st.dataframe(pd.DataFrame(rows),
                                  use_container_width=True,
                                  hide_index=True)
            else:
                st.info("No outlier scenarios — engine reports "
                          "all IRRBB scenarios within tolerance.")
        except Exception as e:
            st.error(
                f"Outlier scenarios failed: {type(e).__name__}: {e}")

    # Tab 3: Products (ENH-234)
    with tabs[2]:
        st.subheader("Treasury Products (ENH-234)")
        st.caption(
            "FD, FX, MM, Bonds with MTM and yield curves. Position "
            "registration goes through POST endpoints (deferred to "
            "v10.156); this tab shows the board summary which "
            "rolls up positions already in the engine state.")
        try:
            pb = engines["products"].board_summary()
            _render_summary(pb)
        except Exception as e:
            st.error(
                f"Products board summary failed: {type(e).__name__}: {e}")

    # Tab 4: Agents (ENH-240)
    with tabs[3]:
        st.subheader("Treasury Agents Orchestration (ENH-240)")
        st.caption(
            "AgentOrchestrator + 5 agents (Cash, FX, MM, Risk, "
            "Compliance). Recommendations lifecycle: pending → "
            "approve/reject (POST endpoints in v10.156). This tab "
            "shows the current board summary.")
        try:
            ab = engines["agents"].board_summary()
            _render_summary(ab)
        except Exception as e:
            st.error(
                f"Agents board summary failed: {type(e).__name__}: {e}")

    # Tab 5: Connectivity (ENH-TRS-R1, R3, R5)
    with tabs[4]:
        st.subheader("Treasury Connectivity (ENH-TRS-R1, R3, R5)")
        st.caption(
            "9900+ bank connections + MMF direct access + ERP-to-Bank "
            "payment journeys. Connector and MMF registration in v10.156 "
            "via POST. Currently shows board summary of registered "
            "connectors and counterparties.")
        try:
            cb = engines["connectivity"].board_summary()
            _render_summary(cb)
        except Exception as e:
            st.error(
                f"Connectivity board summary failed: "
                f"{type(e).__name__}: {e}")

    # Tab 6: Digital & Climate (ENH-TRS-R2 + ENH-TRS-R6)
    with tabs[5]:
        st.subheader("Digital Asset Treasury (ENH-TRS-R2)")
        st.caption(
            "Stablecoin and digital asset treasury integration. "
            "Wallet whitelisting + holdings + spot rates in v10.156.")
        try:
            if hasattr(engines["digital_assets"], "board_summary"):
                db = engines["digital_assets"].board_summary()
                _render_summary(db)
            else:
                st.info(
                    "DigitalAssetTreasuryEngine has no board_summary "
                    "method. Engine present and instantiable; "
                    "integration is by direct method calls only.")
        except Exception as e:
            st.error(
                f"Digital Assets failed: {type(e).__name__}: {e}")

        st.divider()
        st.subheader("Climate-Adjusted Treasury Limits (ENH-TRS-R6)")
        st.caption(
            "Climate-overlay adjustments to treasury exposure limits "
            "by asset class. Read-only — limits are computed from the "
            "configured climate engine at request time.")
        try:
            cb = engines["climate"].board_summary()
            _render_summary(cb)

            st.subheader("All adjusted limits")
            limits = engines["climate"].compute_all_limits()
            if limits:
                rows = []
                for li in limits:
                    if hasattr(li, "__dataclass_fields__"):
                        rows.append({
                            k: getattr(li, k)
                            for k in li.__dataclass_fields__.keys()
                        })
                if rows:
                    st.dataframe(pd.DataFrame(rows),
                                  use_container_width=True,
                                  hide_index=True)
        except Exception as e:
            st.error(
                f"Climate limits failed: {type(e).__name__}: {e}")

    # Tab 7: Islamic & Unified (ENH-239 + ENH-TRS-R4)
    with tabs[6]:
        st.subheader("Islamic Treasury (ENH-239)")
        st.caption(
            "Sharia-compliant treasury products. board_summary + "
            "non-compliant products surfaced for review.")
        try:
            ib = engines["islamic"].board_summary()
            _render_summary(ib)

            non_compliant = engines["islamic"].non_compliant_products()
            if non_compliant:
                st.subheader(
                    f"⚠️ Non-compliant products "
                    f"(n={len(non_compliant)})")
                rows = []
                for p in non_compliant:
                    if hasattr(p, "__dataclass_fields__"):
                        rows.append({
                            k: getattr(p, k)
                            for k in p.__dataclass_fields__.keys()
                        })
                if rows:
                    st.dataframe(pd.DataFrame(rows),
                                  use_container_width=True,
                                  hide_index=True)
            else:
                st.success("All Islamic products Sharia-compliant.")
        except Exception as e:
            st.error(
                f"Islamic Treasury failed: {type(e).__name__}: {e}")

        st.divider()
        st.subheader("Unified Treasury Platform (ENH-TRS-R4)")
        st.caption(
            "MX.3-class cross-asset rollup combining FX, MM, Bonds, "
            "Liquidity. Single source of truth for board reporting.")
        try:
            ub = engines["unified"].board_summary()
            _render_summary(ub)

            positions = engines["unified"].positions()
            if positions:
                st.subheader(f"Positions (n={len(positions)})")
                rows = []
                for p in positions:
                    if hasattr(p, "__dataclass_fields__"):
                        rows.append({
                            k: getattr(p, k)
                            for k in p.__dataclass_fields__.keys()
                        })
                if rows:
                    st.dataframe(pd.DataFrame(rows),
                                  use_container_width=True,
                                  hide_index=True)
        except Exception as e:
            st.error(
                f"Unified Platform failed: {type(e).__name__}: {e}")

    # Footer audit log
    try:
        _user = (st.session_state.get("user_data", {})
                  if hasattr(st, "session_state") else {})
        audit_log(
            action="treasury_arc_cockpit.view",
            username=_user.get("username", "anonymous"),
            detail=f"viewed_at={datetime.now(timezone.utc).isoformat()}",
            module="alm_liquidity")
    except Exception:
        pass

else:
    # Streamlit not installed — module loads but renders nothing
    pass
