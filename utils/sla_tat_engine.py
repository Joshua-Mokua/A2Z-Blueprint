"""utils/sla_tat_engine.py — S4a (shadow).

Derives a per-staff Credit TAT (business days) from the SLA clocks we built —
joining the pipeline-side START (deal.sla_step_log["credit_assessment"]) with the
credit-admin-side END (case.cleared_at, when credit clears the case for
disbursement). This mirrors api._credit_step_index's deal<-app<-case join: the
security_perfection / disbursement steps live on the credit-admin case, NOT on
deal.sla_step_log, so a TAT computed from sla_step_log alone is always empty.

TAT (business days) per deal that has completed credit processing:
    start = deal.sla_step_log["credit_assessment"]
    end   = credit-admin case.cleared_at  (case linked via application.pipeline_deal_id)
Deals in credit but not yet cleared are reported as in_progress (excluded from
the completed-TAT mean). Credit clearance — not Treasury disbursement — is the
end, because clearance is when credit's own work finishes.

This is the SHADOW source for SLA_CREDIT_TAT (weight 0): visible and validatable
next to K011 / the credit lanes before any weighted KPI is repointed (S4b).
Pure read over the managers — no mutation.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from collections import defaultdict
from statistics import mean

_START_STEP = "credit_assessment"


def _to_date(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).date()
    except Exception:
        return None


def _bdays_between(start_iso, end_iso) -> int | None:
    """Whole business days (Mon-Fri) from start to end, mirroring the SLA
    elapsed-clock convention in api._business_days_since. None if unparseable;
    0 if end <= start."""
    s, e = _to_date(start_iso), _to_date(end_iso)
    if not s or not e:
        return None
    if e <= s:
        return 0
    days, d = 0, s
    while d < e:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def _credit_end_by_deal() -> dict:
    """deal_id -> credit-completion ISO timestamp (case.cleared_at), for cases
    that credit has cleared for disbursement (cleared or already disbursed).
    Join: case.application_id -> application.id -> application.pipeline_deal_id."""
    out: dict = {}
    try:
        from utils.core import CreditAdminManager, LoanApplicationManager
        app_to_deal = {}
        for a in (LoanApplicationManager().apps or []):
            aid = str(a.get("id") or "")
            did = str(a.get("pipeline_deal_id") or "")
            if aid and did:
                app_to_deal[aid] = did
        for c in (CreditAdminManager().cases or []):
            if not (c.get("cleared_for_disbursement") or c.get("disbursed")):
                continue
            did = app_to_deal.get(str(c.get("application_id") or ""))
            if not did:
                continue
            ts = c.get("cleared_at") or c.get("last_updated") or c.get("approval_date")
            if ts:
                out[did] = ts
    except Exception:
        import logging
        logging.getLogger("a2z.sla").warning("credit-end index build failed", exc_info=True)
    return out


def compute_sla_credit_tat_by_staff() -> dict:
    """{staff_code: {tat_days, n_deals}} over deals with a completed credit TAT."""
    from utils.core import PipelineManager
    end_by_deal = _credit_end_by_deal()
    per = defaultdict(list)
    in_progress = 0
    for d in (PipelineManager().deals or []):
        if not isinstance(d, dict):
            continue
        log = d.get("sla_step_log") or {}
        start = log.get(_START_STEP) if isinstance(log, dict) else None
        if not start:
            continue
        did = str(d.get("id") or "")
        end = end_by_deal.get(did)
        if not end:
            in_progress += 1            # in credit, not yet cleared
            continue
        tat = _bdays_between(start, end)
        if tat is None:
            continue
        sc = str(d.get("staff_code") or "").strip()
        if sc:
            per[sc].append(tat)
    by_staff = {sc: {"tat_days": round(mean(v), 1), "n_deals": len(v)}
                for sc, v in per.items() if v}
    return {"by_staff": by_staff, "in_progress": in_progress}


def summary() -> dict:
    """Bank-wide + per-staff SLA-clock credit TAT, for the read endpoint."""
    res = compute_sla_credit_tat_by_staff()
    by_staff = res["by_staff"]
    all_tats = []
    for row in by_staff.values():
        all_tats.extend([row["tat_days"]] * row["n_deals"])
    bank_wide = {
        "tat_days": round(mean(all_tats), 1) if all_tats else None,
        "n_deals": len(all_tats),
        "n_staff": len(by_staff),
    }
    return {
        "kpi_id": "SLA_CREDIT_TAT",
        "shadow": True,
        "direction": "lower",
        "unit": "Days",
        "bank_wide": bank_wide,
        "by_staff": by_staff,
        "in_progress": res["in_progress"],
    }
