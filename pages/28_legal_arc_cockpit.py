"""pages/28_legal_arc_cockpit.py — Legal Arc Cockpit (v10.179).

Phase 4 Legal Module closure — 12th module closure in platform history
(after Treasury v10.155 + AML/Compliance v10.169). Locks all 9 Legal
arc standards (ENH-221..ENH-230) and ratchets the cluster against
regression.

The page makes the 9 Legal arc engines operator-driveable from the
browser through 7 thematic tabs grouping engines per workflow logic.

The companion FastAPI router `utils/api_legal.py` exposes the same
engine methods over JSON for the planned React frontend. Cockpit and
API share the engine layer as the source of truth — same pattern as
Treasury v10.155 and Compliance v10.169.

DESIGN DISCIPLINE (carried forward from v10.169 Compliance closure)
-------------------------------------------------------------------
1. Streamlit/import fallback at top so module loads even when
   Streamlit isn't installed (sandbox-friendly)
2. require_access uses REAL signature: require_access(module: str,
   silent: bool = False). Module ID is "legal" — the Legal role group
   (Admin, GC, Senior Counsel, Legal Operations).
3. audit_log uses REAL signature: action, username, detail, module
4. @st.cache_resource caches engine instances at session level
5. Read-only display except for state-mutating buttons that go
   through the explicit FastAPI POST endpoints in utils/api_legal.py

7 THEMATIC TAB STRUCTURE (G4 7-tab limit)
-----------------------------------------
1. 📊 Dashboard     — LegalDashboardEngine (cross-engine board pack)
2. ⚖️ Matters       — LegalCaseManagementEngine (cases, stages, outcomes)
3. 💰 Spend+Counsel — Legal SpendManagement + OutsideCounselPortal
4. 📜 Obligations   — ObligationTrackingEngine (renewals, deadlines)
5. 🔒 Holds+Docs    — LegalHoldManagement + LegalDocumentManagement
6. 📚 Clauses       — ClauseLibraryEngine (playbooks + standards)
7. 📈 Analytics     — LegalAnalyticsEngine (KPIs, trends, portfolio)

This grouping reflects operational adjacency: Spend pairs with
Counsel because both involve external billings; Holds pairs with
Documents because legal holds enforce preservation of documents.
ENH-221 contract review is META_ONLY at v10.179 and is referenced
in the Dashboard tab as a status placeholder.
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

# Engines — 9 Legal arc engines (8 fully-engineered + 1 META_ONLY)
from utils.obligation_tracking import ObligationTrackingEngine
from utils.legal_case_management import LegalCaseManagementEngine
from utils.legal_spend_management import LegalSpendManagementEngine
from utils.outside_counsel_portal import OutsideCounselPortalEngine
from utils.clause_library import ClauseLibraryEngine
from utils.legal_hold_management import LegalHoldManagementEngine
from utils.legal_dashboard import LegalDashboardEngine
from utils.legal_document_management import (
    LegalDocumentManagementEngine)
from utils.legal_analytics import LegalAnalyticsEngine

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

    def audit_log(action: str = "", username: str = "",
                   detail: str = "", module: str = ""):
        pass

try:
    from pages._cockpit_render import render_summary as _render_summary
except ImportError:
    def _render_summary(summary, *, exclude=()):
        if STREAMLIT_AVAILABLE:
            _render_summary(summary)


# ---------------------------------------------------------------------------
# Engine factories — module-level singletons (cached when Streamlit
# is available)
# ---------------------------------------------------------------------------

def _engines():
    """Return tuple of (obligation, case, spend, counsel, clause,
    hold, dashboard, document, analytics)."""
    ob = ObligationTrackingEngine()
    ca = LegalCaseManagementEngine()
    sp = LegalSpendManagementEngine()
    co = OutsideCounselPortalEngine()
    cl = ClauseLibraryEngine()
    ho = LegalHoldManagementEngine()
    da = LegalDashboardEngine(
        obligation_engine=ob, case_engine=ca, spend_engine=sp,
        counsel_engine=co, clause_engine=cl, hold_engine=ho)
    do = LegalDocumentManagementEngine()
    an = LegalAnalyticsEngine(
        obligation_engine=ob, case_engine=ca, spend_engine=sp,
        counsel_engine=co, clause_engine=cl, hold_engine=ho,
        dashboard_engine=da, document_engine=do)
    return (ob, ca, sp, co, cl, ho, da, do, an)


if STREAMLIT_AVAILABLE:
    @st.cache_resource
    def get_engines():
        return _engines()
else:
    def get_engines():
        return _engines()


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render():
    """Top-level render entry point."""
    if not STREAMLIT_AVAILABLE:
        return

    if not require_access("legal"):
        st.error("Access denied — Legal module restricted")
        return

    st.title("⚖️ Legal Arc Cockpit (v10.179)")
    st.caption(
        "Phase 4 Legal Module — closure-protected. 9 standards "
        "ENH-221..230. Audit gates G154 + G155.")

    state = load_shared_state()
    user = state.get("user", {"username": "anonymous"})

    audit_log(action="render_legal_cockpit",
               username=user.get("username", "anonymous"),
               detail="page load",
               module="legal")

    (ob, ca, sp, co, cl, ho, da, do, an) = get_engines()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Dashboard", "⚖️ Matters", "💰 Spend + Counsel",
        "📜 Obligations", "🔒 Holds + Docs", "📚 Clauses",
        "📈 Analytics",
    ])

    # ----- TAB 1: Dashboard -----
    with tab1:
        st.subheader("Legal Health Dashboard (ENH-228)")
        st.caption(
            "Cross-engine composition. ENH-221 contract review is "
            "META_ONLY at v10.179.")
        b = da.board_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("Overall Health",
                   f"{b['overall_health']}",
                   delta=b["health_band"])
        c2.metric("Sections Reporting",
                   f"{b['n_sections_full']}/6")
        c3.metric("Partial Data",
                   "YES" if b["partial_data"] else "NO")
        st.markdown("**Per-section snapshot:**")
        for sec in b["sections"]:
            st.write(
                f"- **{sec['section']}**: {sec['health']} "
                f"({sec['severity']}) — {sec['headline']}")
        st.markdown("**Risk heatmap:**")
        _render_summary(b["heatmap"])

    # ----- TAB 2: Matters -----
    with tab2:
        st.subheader("Matter / Case Management (ENH-223)")
        b = ca.board_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cases", b.get("n_cases_total", 0))
        c2.metric("Open", b.get("n_open", 0))
        c3.metric("Critical Open", b.get("n_critical_open", 0))
        st.markdown("**Stage counts:**")
        _render_summary(b.get("stage_counts", {}))
        st.markdown("**Materiality counts:**")
        _render_summary(b.get("materiality_counts", {}))
        st.markdown("**Outcome counts:**")
        _render_summary(b.get("outcome_counts", {}))

    # ----- TAB 3: Spend + Counsel -----
    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Legal Spend (ENH-225)")
            sb = sp.board_summary()
            st.metric("Budgets", sb.get("n_budgets_total", 0))
            st.metric("At/Over Limit",
                       sb.get("n_budgets_at_or_over_limit", 0))
            st.markdown("**Spend by currency:**")
            _render_summary(sb.get("total_spend_by_currency", {}))
        with c2:
            st.subheader("Outside Counsel (ENH-224)")
            cb = co.board_summary()
            st.metric("Total Counsel",
                       cb.get("n_counsel_total", 0))
            st.metric("Active",
                       cb.get("n_counsel_active", 0))
            st.metric("Submissions Under Review",
                       cb.get("n_submissions_under_review", 0))

    # ----- TAB 4: Obligations -----
    with tab4:
        st.subheader("Obligation Tracking (ENH-222)")
        ob_b = ob.board_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", ob_b.get("n_obligations_total", 0))
        c2.metric("Active", ob_b.get("n_active", 0))
        c3.metric("Breached", ob_b.get("n_breached", 0))
        st.markdown("**Alert counts:**")
        _render_summary(ob_b.get("alert_counts", {}))
        st.markdown("**Kind counts:**")
        _render_summary(ob_b.get("kind_counts", {}))

    # ----- TAB 5: Holds + Documents -----
    with tab5:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Legal Holds (ENH-227)")
            hb = ho.board_summary()
            st.metric("Total Holds", hb.get("n_holds_total", 0))
            st.metric("Active", hb.get("n_holds_active", 0))
            st.metric("Overdue Acks",
                       hb.get("n_acknowledgments_overdue", 0))
        with c2:
            st.subheader("Legal Documents (ENH-229)")
            db_b = do.board_summary()
            st.metric("Total Documents",
                       db_b.get("n_documents_total", 0))
            st.metric("Privileged",
                       db_b.get("n_privileged_documents", 0))
            st.metric("Purgeable Now",
                       db_b.get("n_documents_purgeable_now", 0))
            st.metric("Open Discovery Requests",
                       db_b.get("n_discovery_requests_open", 0))

    # ----- TAB 6: Clauses -----
    with tab6:
        st.subheader("Clause Library & Playbooks (ENH-226)")
        cl_b = cl.board_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Clauses",
                   cl_b.get("n_clauses_total", 0))
        c2.metric("Approved",
                   cl_b.get("n_clauses_approved", 0))
        c3.metric("Prohibited",
                   cl_b.get("n_prohibited_clauses", 0))
        st.metric("Playbooks Published",
                   f"{cl_b.get('n_playbooks_published', 0)}/"
                   f"{cl_b.get('n_playbooks_total', 0)}")
        st.markdown("**Clause classification:**")
        _render_summary(cl_b.get("clause_classification_counts", {}))

    # ----- TAB 7: Analytics -----
    with tab7:
        st.subheader("Legal Analytics & Reporting (ENH-230)")
        an_b = an.board_summary()
        ph = an_b.get("portfolio_health_score")
        st.metric("Portfolio Health Score",
                   f"{round(ph, 1) if ph is not None else 'N/A'}")
        st.markdown("**KPI snapshot:**")
        if pd is not None:
            df = pd.DataFrame(an_b.get("kpis", []))
            st.dataframe(df, use_container_width=True)
        else:
            _render_summary(an_b.get("kpis", []))
        st.markdown("**Efficiency metrics:**")
        _render_summary(an_b.get("efficiency", {}))


if STREAMLIT_AVAILABLE:
    render()
