"""
utils/pipeline_funnel — the sales funnel, read entirely from ADMIN CONFIG.

RULING (2026-08-09): "let me also be categorical that the stages should not be
hardcoded ... the only basic one we said we consider aligning with the win
probabilities is Documentation, Branch Credit, Department, Credit Analysis,
Credit Administration, TROPS - but that is a SIDE LAYER to say that when a deal
is within a certain probability bracket then it is likely to be within that
stage within the bank".

WHAT WAS WRONG. Three vocabularies disagreed:

    utils/core.ALL_ACTIVE_STAGES   13 stages, derived from a CODE constant
    pipeline_settings.stages       15 stages, what the admin screen offers
    utils/api._STAGE_WEIGHTS       6 stages, HARDCODED at api.py:3590

A deal at "Credit Assessment" therefore carried a win probability of ZERO in
every weighted figure, silently, because the hardcoded map had never heard of
it. And six real deals - Department Credit Committee, Legal - Security
Perfection, Initiation, Credit Analysis, Offer Letter - were being asked to be
sales stages when they describe where a deal sits inside the BANK'S process.

TWO AXES, NOT ONE
    THE JOURNEY   each product flow's configured stages, in order, from
                  pipeline_settings.stage_flows. Every stage renders, including
                  those holding nothing yet - a journey with its empty steps
                  hidden is a bar chart, not a funnel.
    THE SIDE LAYER  where the deal probably sits inside the bank, INFERRED from
                  its win probability via configurable bands. It is not a
                  position in the sales journey and never filters one.

WIN PROBABILITY IS PER STAGE WITHIN EACH FLOW (ruling 2026-08-09). "Negotiation"
on a liability product is not the same likelihood as "Negotiation" on a
corporate facility, so a single global map would misstate assured value on every
product but one.

Everything here is config with a documented default. Nothing is hardcoded that
the bank cannot change from the admin screen.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Defaults ONLY - written into pipeline_settings by scripts/seed_funnel_config.py
# and editable from admin thereafter. They exist so a fresh install is coherent,
# not as a source of truth.
DEFAULT_STAGE_PROBABILITIES = {
    "asset": {
        "Lead": 0.05, "Contacted": 0.10, "Qualified": 0.25, "Application": 0.40,
        "Credit Assessment": 0.55, "Offer / Proposal": 0.70, "Negotiation": 0.80,
        "Compliance": 0.90, "Closed Won": 1.0, "Closed Lost": 0.0,
    },
    "liability": {
        "Lead": 0.05, "Contacted": 0.15, "Proposal": 0.40, "Negotiation": 0.65,
        "Documentation": 0.85, "Closed Won": 1.0, "Closed Lost": 0.0,
    },
    "insurance": {
        "Lead": 0.05, "Contacted": 0.15, "Proposal": 0.40, "Negotiation": 0.65,
        "Documentation": 0.85, "Closed Won": 1.0, "Closed Lost": 0.0,
    },
    "other": {
        "Lead": 0.05, "Contacted": 0.15, "Qualified": 0.30, "Proposal": 0.50,
        "Negotiation": 0.75, "Closed Won": 1.0, "Closed Lost": 0.0,
    },
}

# The SIDE LAYER. Bands are inclusive of min, exclusive of max, so they tile the
# 0-1 range without a gap a deal could fall through.
DEFAULT_CREDIT_BANDS = [
    {"key": "pre_credit",     "label": "Not yet in credit",    "min": 0.00, "max": 0.40},
    {"key": "documentation",  "label": "Documentation",        "min": 0.40, "max": 0.60},
    {"key": "branch_credit",  "label": "Branch Credit",        "min": 0.60, "max": 0.70},
    {"key": "department",     "label": "Department",           "min": 0.70, "max": 0.80},
    {"key": "credit_analysis", "label": "Credit Analysis",     "min": 0.80, "max": 0.90},
    {"key": "credit_admin",   "label": "Credit Administration", "min": 0.90, "max": 0.95},
    {"key": "trops",          "label": "TROPS",                "min": 0.95, "max": 1.01},
]

# ── BUCKETS (ruling 2026-08-09) ──────────────────────────────────────────────
# "our stage is clear: Initiation, Documentation, Unit Review (Branch Credit
# Committee, Department Analyst, Department Business Committee), Credit
# Analysis, Credit Administration, TROPS ... the bucket can carry a % like 15%
# then the micro stages within that get the % distributed."
#
# So the journey has TWO LEVELS:
#   BUCKET      what management sees, carrying a weight
#   MICRO-STEP  what an officer works through, sharing the bucket's weight
#
# A deal's win probability is its CUMULATIVE position along the chain: every
# completed bucket in full, plus its progress through the current one. That is
# why the weights must sum to 100 - a chain that sums to 90 would cap a
# disbursed deal at 90% and understate the whole book.
#
# This SUPERSEDES the earlier reading in which these were a probability-inferred
# side layer. They are the journey. One model, not two.
DEFAULT_BUCKETS = {
    # Loans and other credit facilities.
    "asset": [
        {"key": "initiation",     "label": "Initiation",           "weight": 10,
         "steps": ["Initiation"]},
        {"key": "documentation",  "label": "Documentation",        "weight": 15,
         "steps": ["Documentation"]},
        {"key": "unit_review",    "label": "Unit Review",          "weight": 25,
         "steps": ["Branch Credit Committee", "Department Analyst",
                   "Department Business Committee"]},
        {"key": "credit_analysis", "label": "Credit Analysis",     "weight": 20,
         "steps": ["Credit Analysis"]},
        {"key": "credit_admin",   "label": "Credit Administration", "weight": 15,
         "steps": ["Offer Letter", "Legal - Security Perfection"]},
        {"key": "trops",          "label": "TROPS",                "weight": 15,
         "steps": ["Disbursement"]},
    ],
}
# Accounts, liabilities and everything that is not a credit facility:
# "for accounts and others should have a basic Initiation, Documentation,
#  Approval, Opening".
_ACCOUNT_BUCKETS = [
    {"key": "initiation",    "label": "Initiation",    "weight": 20, "steps": ["Initiation"]},
    {"key": "documentation", "label": "Documentation", "weight": 30, "steps": ["Documentation"]},
    {"key": "approval",      "label": "Approval",      "weight": 25, "steps": ["Approval"]},
    {"key": "opening",       "label": "Opening",       "weight": 25, "steps": ["Opening"]},
]
for _f in ("liability", "insurance", "other"):
    DEFAULT_BUCKETS[_f] = [dict(b, steps=list(b["steps"])) for b in _ACCOUNT_BUCKETS]


CLOSED = ("Closed Won", "Closed Lost")


def _settings() -> dict:
    try:
        from utils.core import get_pipeline_settings
        return get_pipeline_settings() or {}
    except Exception as exc:
        logger.warning("pipeline settings unavailable: %s", exc)
        return {}


# Target days per BUCKET — how long a deal should reasonably sit there. Config
# first (stage_buckets[].target_days), then sla_config's steps, then these.
# Without a target there is no "delayed", so the RAG line would be decoration.
DEFAULT_BUCKET_TARGET_DAYS = {
    "initiation": 3, "documentation": 5, "unit_review": 7,
    "credit_analysis": 5, "credit_admin": 7, "trops": 2,
    "approval": 3, "opening": 2,
}


def bucket_target_days(flow: str, bucket_key: str) -> float:
    """Days a deal should take to clear this bucket."""
    for b in buckets_for(flow):
        if b["key"] == bucket_key and b.get("target_days"):
            try:
                return float(b["target_days"])
            except (TypeError, ValueError):
                break
    return float(DEFAULT_BUCKET_TARGET_DAYS.get(str(bucket_key), 5))


def _days_in_stage(deal: dict) -> float:
    """WORKING days the deal has sat at its current stage.

    Business days, via workcal, for the same reason the daily log counts them
    that way: a deal that entered a stage on Friday is not two days late on
    Sunday, and calling it late would send someone chasing a queue nobody was
    rostered for.
    """
    from datetime import date, datetime
    raw = (deal.get("stage_entered_at") or deal.get("stage_changed_at")
           or deal.get("updated_at") or deal.get("open_date") or "")
    txt = str(raw)[:10]
    if not txt:
        return 0.0
    try:
        d0 = date.fromisoformat(txt)
    except ValueError:
        return 0.0
    today = date.today()
    if d0 >= today:
        return 0.0
    try:
        from utils import workcal
        return float(workcal.business_days_between(d0, today))
    except Exception:
        return float((today - d0).days)


def bucket_health(deals: list, flow: str, bucket_key: str) -> dict:
    """RAG for a bucket: are deals moving through it, or stalling?

    Scientific rather than decorative: the ratio of the AVERAGE working days
    deals have sat here to the target for this bucket.

        <= 1.0   green   moving within target
        <= 1.5   amber   slipping
        >  1.5   red     stalled

    A bucket with no deals is 'idle', not green - calling an empty stage
    healthy would hide the fact that nothing is arriving.
    """
    steps = {s.lower() for s in
             next((b["steps"] for b in buckets_for(flow) if b["key"] == bucket_key), [])}
    mine = [d for d in (deals or [])
            if str(d.get("stage") or "").strip().lower() in steps]
    if not mine:
        return {"status": "idle", "avg_days": 0.0, "target_days":
                bucket_target_days(flow, bucket_key), "oldest_days": 0.0, "at_risk": 0}
    ages = [_days_in_stage(d) for d in mine]
    avg = sum(ages) / len(ages)
    target = bucket_target_days(flow, bucket_key)
    ratio = (avg / target) if target else 0.0
    status = "green" if ratio <= 1.0 else ("amber" if ratio <= 1.5 else "red")
    return {
        "status": status,
        "avg_days": round(avg, 1),
        "target_days": target,
        "oldest_days": round(max(ages), 1),
        "at_risk": sum(1 for a in ages if target and a > target),
    }


def buckets_for(flow: str) -> list:
    """The bucket chain for a flow: [{key,label,weight,steps:[...]}, ...].

    From pipeline_settings.stage_buckets, falling back to the defaults. A flow
    with no configuration at all falls back to the account chain rather than an
    empty list - an empty chain would make every deal in that product worth
    zero, which is the failure mode this whole model exists to remove.
    """
    cfg = (_settings().get("stage_buckets") or {}).get(str(flow))
    src = cfg if isinstance(cfg, list) and cfg else DEFAULT_BUCKETS.get(str(flow))
    if not src:
        src = DEFAULT_BUCKETS.get("other") or []
    out = []
    for b in src:
        if not isinstance(b, dict):
            continue
        steps = [str(x) for x in (b.get("steps") or []) if str(x).strip()]
        try:
            w = float(b.get("weight", 0) or 0)
        except (TypeError, ValueError):
            w = 0.0
        out.append({"key": str(b.get("key") or b.get("label") or ""),
                    "label": str(b.get("label") or b.get("key") or ""),
                    "weight": w,
                    "steps": steps or [str(b.get("label") or b.get("key") or "")]})
    return out


def all_active_stages() -> list:
    """Every micro-step across every configured flow, excluding closed.

    utils.core.ACTIVE_STAGES is built from HARDCODED stage lists
    (PIPELINE_STAGES_LOAN and friends) carrying the retired vocabulary. After
    the bucket migration no deal matched it, so "active" came out empty and
    every headline value collapsed to zero. This is the configured equivalent.
    """
    out = []
    for flow in stage_flows():
        for st in micro_steps(flow):
            if st not in out and st not in CLOSED:
                out.append(st)
    return out


def micro_steps(flow: str) -> list:
    """Every micro-step of a flow, in journey order — the real stage list."""
    out = []
    for b in buckets_for(flow):
        out.extend(b["steps"])
    return out


def bucket_of(flow: str, stage: str) -> Optional[dict]:
    """Which bucket a micro-step belongs to, or None if the stage is unknown."""
    st = str(stage or "").strip().lower()
    for b in buckets_for(flow):
        if any(str(x).strip().lower() == st for x in b["steps"]):
            return b
    return None


def bucket_probability(flow: str, stage: str) -> float:
    """Cumulative win probability at a micro-step.

    Every completed bucket contributes its full weight; the current bucket
    contributes its weight pro-rata across its own steps. So the LAST step of a
    bucket carries that bucket's full weight, and the chain reaches 1.0 only at
    the end - which is why buckets are normalised to sum to 100 below.
    """
    chain = buckets_for(flow)
    total = sum(b["weight"] for b in chain) or 100.0
    st = str(stage or "").strip().lower()
    acc = 0.0
    for b in chain:
        names = [str(x).strip().lower() for x in b["steps"]]
        if st in names:
            i = names.index(st) + 1
            return round((acc + b["weight"] * (i / len(names))) / total, 4)
        acc += b["weight"]
    return 0.0


def bucket_view(deals: list, flow: str, value_of=None) -> list:
    """The journey as BUCKETS, each carrying its micro-steps.

    This is what management reads: six rows for a loan, not eleven. The
    micro-steps travel with their bucket so an officer can still see where
    inside it a deal sits.
    """
    if value_of is None:
        def value_of(d):
            try:
                return float(d.get("amount_kes") or d.get("deal_value") or 0)
            except (TypeError, ValueError):
                return 0.0

    by_stage = {}
    for d in deals or []:
        by_stage.setdefault(str(d.get("stage") or "").strip().lower(), []).append(d)

    out = []
    for b in buckets_for(flow):
        steps = []
        b_count = 0
        b_value = 0.0
        for st in b["steps"]:
            mine = by_stage.get(st.strip().lower(), [])
            v = round(sum(value_of(x) for x in mine), 2)
            steps.append({"stage": st, "count": len(mine), "value": v,
                          "probability": bucket_probability(flow, st)})
            b_count += len(mine)
            b_value += v
        out.append({
            "key": b["key"], "label": b["label"], "weight": b["weight"],
            "count": b_count, "value": round(b_value, 2),
            "probability": bucket_probability(flow, b["steps"][-1]) if b["steps"] else 0.0,
            "steps": steps,
            "health": bucket_health(deals, flow, b["key"]),
        })
    return out


def stage_flows() -> dict:
    """{flow_key: [stage, ...]} — the configured journey per product class."""
    return dict((_settings().get("stage_flows") or {}))


def flow_keys() -> list:
    return sorted(stage_flows().keys())


def stage_probabilities() -> dict:
    """{flow_key: {stage: probability}}, from config, falling back to defaults.

    A flow present in stage_flows but absent here still resolves: see
    probability_for, which degrades to an even progression rather than zero.
    """
    cfg = _settings().get("stage_probabilities") or {}
    out = {k: dict(v) for k, v in DEFAULT_STAGE_PROBABILITIES.items()}
    for flow, m in cfg.items():
        if isinstance(m, dict):
            out.setdefault(str(flow), {})
            for stage, p in m.items():
                try:
                    out[str(flow)][str(stage)] = float(p)
                except (TypeError, ValueError):
                    continue
    return out


def probability_for(flow: str, stage: str) -> float:
    """Win probability for a stage WITHIN a flow.

    An unconfigured stage does NOT return zero. Zero would silently erase a real
    deal from every weighted figure - the exact failure the hardcoded
    _STAGE_WEIGHTS caused. Instead it degrades to an even progression along the
    flow, which is wrong but visibly plausible and self-correcting once the
    admin sets a value.
    """
    f, s = str(flow or "").strip(), str(stage or "").strip()
    table = stage_probabilities().get(f) or {}
    if s in table:
        return float(table[s])
    if s == "Closed Won":
        return 1.0
    if s == "Closed Lost":
        return 0.0
    seq = [x for x in (stage_flows().get(f) or []) if x not in CLOSED]
    if s in seq and len(seq) > 1:
        return round((seq.index(s) + 1) / (len(seq) + 1), 2)
    return 0.0


def credit_bands() -> list:
    cfg = _settings().get("credit_bands")
    if isinstance(cfg, list) and cfg:
        out = []
        for b in cfg:
            if not isinstance(b, dict):
                continue
            try:
                out.append({"key": str(b.get("key") or b.get("label")),
                            "label": str(b.get("label") or b.get("key")),
                            "min": float(b.get("min", 0)),
                            "max": float(b.get("max", 1.01))})
            except (TypeError, ValueError):
                continue
        if out:
            return sorted(out, key=lambda x: x["min"])
    return [dict(b) for b in DEFAULT_CREDIT_BANDS]


def credit_band_for(probability: float) -> dict:
    """Where this deal probably sits inside the bank. THE SIDE LAYER.

    Inferred from probability, never from the deal's sales stage - the two are
    different questions about the same deal.
    """
    try:
        p = float(probability or 0)
    except (TypeError, ValueError):
        p = 0.0
    for b in credit_bands():
        if b["min"] <= p < b["max"]:
            return b
    bands = credit_bands()
    return bands[-1] if p >= bands[-1]["min"] else bands[0]


# A product's category, as the pipeline already understands it, mapped onto the
# flow whose journey that product follows.
_CATEGORY_TO_FLOW = {
    "loan": "asset",        # credit facilities take the full credit journey
    "account": "liability", # CASA and deposits: Initiation -> Opening
    "deposit": "liability",
    "insurance": "insurance",
}


def flow_for_deal(deal: dict) -> str:
    """Which configured flow this deal follows.

    Classifies by PRODUCT via utils.core.get_pipeline_category - the mapper the
    pipeline already uses - rather than by a class field the deals do not carry.
    Reading a missing field was landing every deal in "other", so loans were
    being shown the four-step account journey instead of the credit journey.

    The bank's focus is loans disbursed and deposits mobilised, so those two
    must classify correctly even when a deal is sparsely filled; everything else
    falls to "other", which is the light-touch journey by design.
    """
    for key in ("product", "product_type", "deal_type", "deal_category", "category"):
        raw = str(deal.get(key) or "").strip()
        if not raw:
            continue
        try:
            from utils.core import get_pipeline_category
            cat = str(get_pipeline_category(raw) or "").strip().lower()
        except Exception:
            cat = ""
        flow = _CATEGORY_TO_FLOW.get(cat)
        if flow and flow in stage_flows():
            return flow
        low = raw.lower()
        if any(w in low for w in ("loan", "credit", "overdraft", "finance", "mortgage")):
            return "asset"
        if any(w in low for w in ("deposit", "casa", "account", "savings", "current")):
            return "liability"
        if "insur" in low or "bancass" in low:
            return "insurance"

    cls = str(deal.get("deal_class") or deal.get("product_class") or "").strip().lower()
    return cls if cls in stage_flows() else "other"


def build_funnel(deals: list, flow: str, value_of=None) -> list:
    """Every configured stage of a flow, in order, with what sits in it.

    EMPTY STAGES ARE INCLUDED. A funnel that hides the steps holding nothing is
    a bar chart of whatever happened to be busy; the gap is usually the finding.
    """
    if value_of is None:
        def value_of(d):
            try:
                return float(d.get("amount_kes") or d.get("deal_value") or 0)
            except (TypeError, ValueError):
                return 0.0

    seq = [s for s in (stage_flows().get(str(flow)) or []) if s not in CLOSED]
    counts = {s: 0 for s in seq}
    values = {s: 0.0 for s in seq}
    for d in deals or []:
        s = str(d.get("stage") or "").strip()
        if s in counts:
            counts[s] += 1
            values[s] += value_of(d)

    out = []
    for s in seq:
        p = probability_for(flow, s)
        out.append({
            "stage": s,
            "count": counts[s],
            "value": round(values[s], 2),
            "probability": p,
            "weighted": round(values[s] * p, 2),
            "credit_band": credit_band_for(p)["label"],
        })
    return out
