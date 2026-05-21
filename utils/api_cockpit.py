"""utils/api_cockpit — FastAPI router for live cockpit reads (v10.297).

Exposes the cockpit_read composers as HTTP endpoints so the React SPA
(#37) can fetch the same live cockpit views that Streamlit pages 109
(CIMS) and 110 (Treasury) render. Single source of truth: both
transports call the same composer functions.

DESIGN CONTRACT
---------------
1. Every endpoint requires a valid JWT — `Depends(get_current_user)`
2. Every endpoint is READ-ONLY (GET). State changes go through the
   engine-specific APIs (api_treasury, api_compliance, etc.), not
   through cockpit composers.
3. Every endpoint returns a JSON-serialisable dict.
4. Audit logging via `_audit_cockpit(action, user, detail)` after
   every successful endpoint call.
5. The cockpit_read composers are the source of truth. This module
   only wraps them in HTTP transport. If the composer returns
   `{"foo": 1}`, the endpoint returns `{"foo": 1}` verbatim.
6. Unknown IDs are NOT a 404 — they return the well-formed empty
   shape the composer returns (per the cockpit_read contract).
   The React SPA shouldn't have to handle two response shapes.

ENDPOINT MAP (all GET, all JWT-protected)
-----------------------------------------
  GET /api/cockpit/health
      Connectivity + version probe; React SPA uses this to detect
      backend upgrades.

  GET /api/cockpit/cims/open-work
      Bank-wide CIMS work landscape: open sessions, pending NLP,
      STP manual queue, exceptions, SLA breaches, pending merges.

  GET /api/cockpit/cims/instruction-trace/{session_id}
      Full lifecycle for one linked_session_id, joining capture +
      classification + STP + exceptions + SLA + audit history.

  GET /api/cockpit/treasury/open-work
      Treasury landscape: FX positions, IRRBB breaches, LCR
      status.

  GET /api/cockpit/treasury/liquidity
      Raw liquidity_metrics.json contents (LCR + NSFR + components).

  GET /api/cockpit/treasury/irrbb
      Raw irrbb.json contents (scenarios + CBK limits).

  GET /api/cockpit/treasury/capital
      Raw capital_adequacy.json contents (CET1/Tier1/Total ratios).

  GET /api/cockpit/treasury/daily-report
      Daily Treasury Dashboard Report composed via a wired
      TreasuryDashboardEngine (v10.302). Returns report
      metadata + all sections + engine wiring summary.
      Optional ?as_of_date=YYYY-MM-DD query param.

  GET /api/cockpit/treasury/cash-forecast
      13-week (default) cash forecast composed via a primed
      TreasuryCashForecastingEngine (v10.304). Returns
      forecast metadata + daily points with 80%/95% bands.
      Optional ?horizon_days=N (1-365, default 91).

  GET /api/cockpit/credit/open-work
      Bank-wide Credit work landscape — applications, IFRS9
      stages, NPL ratio, watchlist count.

  GET /api/cockpit/credit/applications
      All loan application records (list).

  GET /api/cockpit/credit/ifrs9
      All IFRS9 loan records with stage classification (list).

  GET /api/cockpit/credit/watchlist
      Credit monitoring watchlist entries (list).

  GET /api/cockpit/credit/portfolio-analytics
      Cat A Portfolio Analytics report (v10.309). Composes
      AIUnderwritingEngine + CreditRiskScoringEngine +
      IRBCapitalEngine into a 3-section report. First multi-
      engine aggregation composer in the cockpit API.

  GET /api/cockpit/compliance/open-work
      Bank-wide Compliance landscape — cases, AML alerts,
      sanctions hits, regulatory returns with overdue and
      on-time KPIs.

  GET /api/cockpit/compliance/cases
      All compliance case records (list).

  GET /api/cockpit/compliance/aml-alerts
      All AML monitoring alert records (list).

  GET /api/cockpit/compliance/sanctions
      All sanctions screening records (list).

  GET /api/cockpit/compliance/regulatory-returns
      All regulatory return records (CBK, KRA, etc.) (list).

  GET /api/cockpit/compliance/cra-training
      Cat A composer (v10.310). Composes
      ComplianceRiskAssessmentEngine (#198) +
      ComplianceTrainingEngine (#197) into a 2-section
      report. Second Cat A composer in the cockpit API.

  GET /api/cockpit/audit/log
      Filtered audit trail from data/audit_log.json. Query
      params: action, module, user_filter, since, until,
      limit (1-1000, default 100). Returns
      {records, count, filters, as_at}.

  GET /api/cockpit/audit/reviews
      Audit review register (#201-#210). v10.306-migrated;
      reads JSON by default, PG when per_table.audit_reviews
      is set to "auto" or "pg_view".

  GET /api/cockpit/ops/incidents
      IT/Ops incident register. v10.306-migrated; cutover via
      per_table.incidents config.

  GET /api/cockpit/cx/nps
      Customer NPS survey responses. v10.306-migrated;
      cutover via per_table.nps_responses config (file is
      data/nps.json — table name differs).

  GET /api/cockpit/risk/rcsa
      Risk Control Self-Assessment register (#211-#220).
      v10.306-migrated; cutover via per_table.rcsa_register
      config.

USAGE
-----
Mount in the parent FastAPI app:

    from utils.api_cockpit import router as cockpit_router
    app.include_router(cockpit_router)

React fetch example:

    fetch('/api/cockpit/cims/open-work', {
      headers: { Authorization: `Bearer ${jwt}` }
    })

GRACEFUL DEGRADATION
--------------------
If FastAPI isn't installed, the module still imports — `router`
is None, `FASTAPI_AVAILABLE` is False. Same pattern as
utils/api_treasury.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

try:
    from fastapi import APIRouter, Depends, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore
    Depends = None  # type: ignore
    HTTPException = Exception  # type: ignore

# JWT auth: try the real one, fall back to a stub for environments
# without FastAPI / dev sandboxes.
try:
    from utils.auth_jwt import get_current_user
except Exception:
    def get_current_user():  # type: ignore[no-redef]
        return {"username": "anonymous", "role": "guest"}

from utils.cockpit_read import (
    cims_open_work, cims_instruction_trace,
    treasury_open_work, treasury_liquidity_metrics,
    treasury_irrbb, treasury_capital_adequacy,
    treasury_daily_report, treasury_cash_forecast,
    credit_open_work, credit_loan_applications,
    credit_ifrs9_loans, credit_watchlist,
    credit_portfolio_analytics,
    compliance_open_work, compliance_cases,
    compliance_aml_alerts, compliance_sanctions_screening,
    compliance_regulatory_returns,
    compliance_cra_training,
    audit_log_records,
    audit_reviews_records, incidents_records,
    nps_responses_records, rcsa_register_records,
)


COCKPIT_READ_API_VERSION = "21.0"  # Bumped v10.310 — added
                                    # compliance_cra_training
                                    # (second Cat A composer)


def _audit_cockpit(action: str, user: Dict[str, Any],
                    detail: str = "") -> None:
    """Audit-log wrapper matching audit_log's canonical signature
    (action, username, detail, module, before, after).

    audit_log is imported lazily here because utils.core_audit
    pulls in utils.core which imports streamlit. The cockpit API
    module must be importable in non-Streamlit environments (e.g.
    a standalone FastAPI server feeding the React SPA)."""
    username = (
        user.get("username") if isinstance(user, dict)
        else "anonymous"
    )
    try:
        from utils.core_audit import audit_log
        audit_log(
            action=action,
            username=username or "anonymous",
            detail=detail,
            module="cockpit_api",
            before=None,
            after=None,
        )
    except Exception:
        # Audit failures must not break the API response —
        # they're recorded separately by the audit subsystem.
        pass


if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])

    # ------------------------------------------------------------
    # Health
    # ------------------------------------------------------------

    @router.get("/health")
    def cockpit_health(user=Depends(get_current_user)):
        """Connectivity probe + version. React SPA reads
        `cockpit_read_api_version` to detect when the backend
        has been upgraded and the frontend may need a refresh."""
        result = {
            "status": "ok",
            "cockpit_read_api_version": COCKPIT_READ_API_VERSION,
            "checked_at_utc": datetime.now(
                timezone.utc).isoformat(),
        }
        _audit_cockpit("health", user)
        return result

    # ------------------------------------------------------------
    # CIMS
    # ------------------------------------------------------------

    @router.get("/cims/open-work")
    def cims_open_work_endpoint(
        user=Depends(get_current_user),
    ):
        """Bank-wide CIMS work landscape — counts of open
        sessions, pending NLP, STP manual queue, open exceptions,
        SLA risk, pending merges. Refreshed live every call."""
        result = cims_open_work(data_dir="data")
        _audit_cockpit("cims.open_work", user)
        return result

    @router.get("/cims/instruction-trace/{session_id}")
    def cims_instruction_trace_endpoint(
        session_id: str,
        user=Depends(get_current_user),
    ):
        """Full CIMS lifecycle trace for one linked_session_id.
        Joins capture (#166) + NLP (#167) + STP (#168) +
        exceptions (#175) + SLA (#171) + audit history (#176).

        Unknown session_id returns a well-formed empty trace
        (capture: null, lists empty) — NOT a 404. React doesn't
        need to handle two response shapes."""
        result = cims_instruction_trace(
            session_id, data_dir="data",
        )
        _audit_cockpit(
            "cims.instruction_trace", user,
            detail=f"session_id={session_id}",
        )
        return result

    # ------------------------------------------------------------
    # Treasury
    # ------------------------------------------------------------

    @router.get("/treasury/open-work")
    def treasury_open_work_endpoint(
        user=Depends(get_current_user),
    ):
        """Treasury landscape — FX positions, IRRBB breaches,
        LCR status with breach flag."""
        result = treasury_open_work(data_dir="data")
        _audit_cockpit("treasury.open_work", user)
        return result

    @router.get("/treasury/liquidity")
    def treasury_liquidity_endpoint(
        user=Depends(get_current_user),
    ):
        """Raw liquidity_metrics.json contents. Returns null
        if the file is missing or malformed."""
        result = treasury_liquidity_metrics(data_dir="data")
        _audit_cockpit("treasury.liquidity", user)
        return result if result is not None else {
            "status": "no_data",
            "message": (
                "liquidity_metrics.json not present or "
                "malformed"
            ),
        }

    @router.get("/treasury/irrbb")
    def treasury_irrbb_endpoint(
        user=Depends(get_current_user),
    ):
        """Raw irrbb.json contents — scenarios and CBK limits."""
        result = treasury_irrbb(data_dir="data")
        _audit_cockpit("treasury.irrbb", user)
        return result if result is not None else {
            "status": "no_data",
            "message": "irrbb.json not present or malformed",
        }

    @router.get("/treasury/capital")
    def treasury_capital_endpoint(
        user=Depends(get_current_user),
    ):
        """Raw capital_adequacy.json contents — CET1/Tier1/Total
        capital ratios under Basel III as adopted by CBK."""
        result = treasury_capital_adequacy(data_dir="data")
        _audit_cockpit("treasury.capital", user)
        return result if result is not None else {
            "status": "no_data",
            "message": (
                "capital_adequacy.json not present or malformed"
            ),
        }

    @router.get("/treasury/daily-report")
    def treasury_daily_report_endpoint(
        as_of_date: str = "",
        user=Depends(get_current_user),
    ):
        """Daily Treasury Dashboard Report composed by a wired
        TreasuryDashboardEngine (v10.302). Returns report
        metadata, all sections with status/metrics/thresholds,
        and engine wiring summary. `as_of_date` optional —
        defaults to today UTC. Used by Streamlit cockpit
        page 110 tab 7 + future React SPA dashboard view."""
        date_arg = as_of_date.strip() or None
        result = treasury_daily_report(as_of_date=date_arg)
        _audit_cockpit(
            "treasury.daily_report", user,
            detail=f"as_of_date={date_arg or 'today'}",
        )
        return result

    @router.get("/treasury/cash-forecast")
    def treasury_cash_forecast_endpoint(
        horizon_days: int = 91,
        user=Depends(get_current_user),
    ):
        """13-week (default) cash forecast composed via a
        primed TreasuryCashForecastingEngine (v10.304). Returns
        forecast metadata + daily points with 80%/95% bands.
        Empty production data returns status=no_data with a
        well-formed empty points list — React doesn't need to
        handle two response shapes."""
        # Clamp the horizon to a sane range to avoid abuse
        if horizon_days < 1:
            horizon_days = 1
        elif horizon_days > 365:
            horizon_days = 365
        result = treasury_cash_forecast(
            horizon_days=horizon_days,
        )
        _audit_cockpit(
            "treasury.cash_forecast", user,
            detail=f"horizon_days={horizon_days}",
        )
        return result

    # ------------------------------------------------------------
    # Credit (v10.300)
    # ------------------------------------------------------------

    @router.get("/credit/open-work")
    def credit_open_work_endpoint(
        user=Depends(get_current_user),
    ):
        """Bank-wide Credit work landscape — loan applications
        by lane, IFRS9 stage distribution, NPL ratio,
        watchlist count. All derived from loan_applications.json,
        ifrs9_loans.json, and credit_monitoring.json."""
        result = credit_open_work(data_dir="data")
        _audit_cockpit("credit.open_work", user)
        return result

    @router.get("/credit/applications")
    def credit_applications_endpoint(
        user=Depends(get_current_user),
    ):
        """All loan application records. Returns a list.
        React SPA can paginate / filter client-side until a
        server-side query endpoint is added in a later batch."""
        records = credit_loan_applications(data_dir="data")
        _audit_cockpit(
            "credit.applications", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/credit/ifrs9")
    def credit_ifrs9_endpoint(
        user=Depends(get_current_user),
    ):
        """All IFRS9 loan records with stage classification.
        Returns a list. Source of truth for regulatory
        Stage 1/2/3 reporting."""
        records = credit_ifrs9_loans(data_dir="data")
        _audit_cockpit(
            "credit.ifrs9", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/credit/watchlist")
    def credit_watchlist_endpoint(
        user=Depends(get_current_user),
    ):
        """Credit monitoring watchlist entries. Lists clients
        flagged for proactive risk management (e.g. missed
        payments, covenant breaches, sector concerns)."""
        records = credit_watchlist(data_dir="data")
        _audit_cockpit(
            "credit.watchlist", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/credit/portfolio-analytics")
    def credit_portfolio_analytics_endpoint(
        user=Depends(get_current_user),
    ):
        """Cat A Portfolio Analytics report (v10.309).
        Composes AIUnderwritingEngine + CreditRiskScoringEngine
        + IRBCapitalEngine into a 3-section report. Each
        section has its own status; top-level status
        aggregates. The IRB section runs against the IFRS9
        loan portfolio (with a shape-fit note about retail
        loans being mapped to SME_CORPORATE)."""
        result = credit_portfolio_analytics(data_dir="data")
        _audit_cockpit(
            "credit.portfolio_analytics", user,
            detail=f"n_sections={result['n_sections']}",
        )
        return result

    # ------------------------------------------------------------
    # Compliance (v10.301)
    # ------------------------------------------------------------

    @router.get("/compliance/open-work")
    def compliance_open_work_endpoint(
        user=Depends(get_current_user),
    ):
        """Bank-wide Compliance work landscape — compliance
        cases, AML alerts, sanctions screening hits, and
        regulatory returns. Includes overdue + on-time KPIs."""
        result = compliance_open_work(data_dir="data")
        _audit_cockpit("compliance.open_work", user)
        return result

    @router.get("/compliance/cases")
    def compliance_cases_endpoint(
        user=Depends(get_current_user),
    ):
        """All compliance case records. Returns a list."""
        records = compliance_cases(data_dir="data")
        _audit_cockpit(
            "compliance.cases", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/compliance/aml-alerts")
    def compliance_aml_alerts_endpoint(
        user=Depends(get_current_user),
    ):
        """All AML monitoring alert records. Returns a list."""
        records = compliance_aml_alerts(data_dir="data")
        _audit_cockpit(
            "compliance.aml_alerts", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/compliance/sanctions")
    def compliance_sanctions_endpoint(
        user=Depends(get_current_user),
    ):
        """All sanctions screening records. Returns a list.
        Pending-review status is the regulatorily critical
        subset; consumers should filter accordingly."""
        records = compliance_sanctions_screening(data_dir="data")
        _audit_cockpit(
            "compliance.sanctions", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/compliance/regulatory-returns")
    def compliance_regulatory_returns_endpoint(
        user=Depends(get_current_user),
    ):
        """All regulatory return records (CBK, KRA, etc.).
        Returns a list. Overdue items have past `due_date`
        with null `filed_date`."""
        records = compliance_regulatory_returns(data_dir="data")
        _audit_cockpit(
            "compliance.regulatory_returns", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/compliance/cra-training")
    def compliance_cra_training_endpoint(
        user=Depends(get_current_user),
    ):
        """Cat A composer (v10.310). Composes
        ComplianceRiskAssessmentEngine (#198) +
        ComplianceTrainingEngine (#197) into a 2-section
        report. Same shape as
        /api/cockpit/credit/portfolio-analytics from v10.309:
        per-section status + top-level status aggregate."""
        result = compliance_cra_training(data_dir="data")
        _audit_cockpit(
            "compliance.cra_training", user,
            detail=f"n_sections={result['n_sections']}",
        )
        return result

    # ------------------------------------------------------------
    # Audit trail (v10.305)
    # ------------------------------------------------------------

    @router.get("/audit/log")
    def audit_log_endpoint(
        action: str = "",
        module: str = "",
        user_filter: str = "",
        since: str = "",
        until: str = "",
        limit: int = 100,
        user=Depends(get_current_user),
    ):
        """Filtered audit trail from data/audit_log.json.
        Supports filters by action/module/user/date range,
        with a configurable limit. Used by Credit + Compliance
        cockpit tab 7 + React SPA. Returns
        {records, count, filters, as_at} — count is the
        unfiltered total so the UI can show 'showing N of M'.

        Note: the `user` parameter is the JWT-authenticated
        actor (auto-injected by Depends). The
        `user_filter` query parameter is the filter applied
        to record["user"] in the returned records — separate
        from auth. This naming avoids collision.
        """
        result = audit_log_records(
            data_dir="data",
            action=(action.strip() or None),
            module=(module.strip() or None),
            user=(user_filter.strip() or None),
            since=(since.strip() or None),
            until=(until.strip() or None),
            limit=max(1, min(int(limit), 1000)),
        )
        _audit_cockpit(
            "audit.log", user,
            detail=f"count={result['count']} limit={limit}",
        )
        return result

    # ------------------------------------------------------------
    # PG-ready endpoints (v10.308)
    # ------------------------------------------------------------
    # Each of these wraps a v10.306-migrated table's composer.
    # Default behavior reads JSON; flipping
    # _data_source.per_table.<table> = "auto" in
    # integration_layer_config.json routes the read to PG.

    @router.get("/audit/reviews")
    def audit_reviews_endpoint(user=Depends(get_current_user)):
        """Audit review register (#201-#210). 250 records.
        Reads from data/audit_reviews.json by default; flip to
        PG via per_table.audit_reviews config."""
        records = audit_reviews_records(data_dir="data")
        _audit_cockpit(
            "audit.reviews", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/ops/incidents")
    def ops_incidents_endpoint(user=Depends(get_current_user)):
        """IT/Ops incident register. 80 records.
        Reads data/incidents.json by default; flip to PG via
        per_table.incidents config."""
        records = incidents_records(data_dir="data")
        _audit_cockpit(
            "ops.incidents", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/cx/nps")
    def cx_nps_endpoint(user=Depends(get_current_user)):
        """Customer NPS survey responses. 150 records.
        Reads data/nps.json by default; flip to PG via
        per_table.nps_responses config (note table name
        differs from file name)."""
        records = nps_responses_records(data_dir="data")
        _audit_cockpit(
            "cx.nps", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

    @router.get("/risk/rcsa")
    def risk_rcsa_endpoint(user=Depends(get_current_user)):
        """Risk Control Self-Assessment register
        (#211-#220). 80 records. Reads data/rcsa_register.json
        by default; flip to PG via per_table.rcsa_register
        config."""
        records = rcsa_register_records(data_dir="data")
        _audit_cockpit(
            "risk.rcsa", user,
            detail=f"count={len(records)}",
        )
        return {"records": records, "count": len(records)}

else:
    router = None
