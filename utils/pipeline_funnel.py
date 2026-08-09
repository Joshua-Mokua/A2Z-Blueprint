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

CLOSED = ("Closed Won", "Closed Lost")


def _settings() -> dict:
    try:
        from utils.core import get_pipeline_settings
        return get_pipeline_settings() or {}
    except Exception as exc:
        logger.warning("pipeline settings unavailable: %s", exc)
        return {}


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


def flow_for_deal(deal: dict) -> str:
    """Which configured flow this deal follows.

    Prefers the per-product flow resolution the pipeline already uses, so this
    module never invents a second answer to a question already settled.
    """
    try:
        from utils.core import _stage_flow_for
        f = _stage_flow_for(deal)
        if isinstance(f, str) and f:
            return f
    except Exception:
        pass
    cls = str(deal.get("deal_class") or deal.get("product_class")
              or deal.get("category") or "").strip().lower()
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
