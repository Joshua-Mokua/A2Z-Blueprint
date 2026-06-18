"""utils/sla_tat_engine.py — S4a (shadow).

Derives a per-staff Credit TAT (business days) from the pipeline SLA clocks we
built (deal.sla_step_log), independent of the CBS batch and the credit_engine
lane TATs. This is the SHADOW source for the SLA_CREDIT_TAT KPI (weight 0):
it lets the SLA-derived TAT be SEEN and validated next to K011 / the credit
lanes before any weighted KPI is repointed at it (S4b promotion).

TAT definition (per deal, in business days):
    start = sla_step_log["credit_assessment"]
    end   = sla_step_log["disbursement"]  (preferred)
            else sla_step_log["security_perfection"]
Deals still inside credit (no end stamp) are reported separately as
in_progress and do NOT pollute the completed-TAT mean.

Pure read over PipelineManager().deals — no mutation, no DB writes.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from collections import defaultdict
from statistics import mean

_START_STEP = "credit_assessment"
_END_STEPS = ("disbursement", "security_perfection")  # first present wins


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


def _deal_credit_tat(deal: dict) -> int | None:
    """Completed credit TAT (business days) for one deal, or None if the deal
    has not reached a credit end-step yet."""
    log = deal.get("sla_step_log") or {}
    if not isinstance(log, dict):
        return None
    start = log.get(_START_STEP)
    if not start:
        return None
    end = next((log[k] for k in _END_STEPS if log.get(k)), None)
    if not end:
        return None
    return _bdays_between(start, end)


def compute_sla_credit_tat_by_staff() -> dict:
    """{staff_code: {tat_days, n_deals}} over deals with a completed credit TAT."""
    from utils.core import PipelineManager
    per = defaultdict(list)
    in_progress = 0
    for d in (PipelineManager().deals or []):
        if not isinstance(d, dict):
            continue
        tat = _deal_credit_tat(d)
        if tat is None:
            # has it started credit but not finished? count as in-progress
            log = d.get("sla_step_log") or {}
            if isinstance(log, dict) and log.get(_START_STEP):
                in_progress += 1
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
    for sc, row in by_staff.items():
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
