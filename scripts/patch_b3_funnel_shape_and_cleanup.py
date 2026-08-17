#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
B3 - a real funnel shape, RAG stage health, and a clean-up of unprofessional text.

YOUR ASKS (2026-08-09)
  "a well curved 3d funnel that shows how perfectly a pipeline should flow
   across these stages, then based on our achievement within that stage ... that
   line colour coded from red amber green to indicate if we are delaying deals
   at that stage in a scientific way"
  "these redundant statements we need to clean them out across the system since
   they are showing unprofessionalism on a system on pilot"

1. A TRUE FUNNEL, not stacked bars. Each bucket is a TRAPEZOID whose top edge
   matches the band above, so the silhouette is continuous from Initiation to
   disbursement. Width follows the IDEAL taper - what a healthy pipeline should
   look like - while colour reports what it is actually doing.
   SHAPE SHOWS THE PLAN; COLOUR SHOWS THE TRUTH. Depth comes from a four-stop
   vertical gradient (highlight, body, body, shadow) so each band reads as a
   solid object; hovering lifts and brightens it.

2. RAG STAGE HEALTH, computed not decorative. bucket_health compares the AVERAGE
   WORKING DAYS deals have sat in a bucket against that bucket's target:

        <= 1.0x target   green   moving
        <= 1.5x target   amber   slipping
        >  1.5x target   red     stalled
        no deals         idle    (NOT green - an empty stage is not healthy,
                                  it means nothing is arriving)

   Working days via workcal, for the same reason the daily log uses them: a deal
   that entered a stage on Friday is not late on Sunday, and calling it late
   sends someone chasing a queue nobody was rostered for.

   Targets come from stage_buckets[].target_days, then sla_config, then
   documented defaults - config first, as everywhere else.

   Verified: Initiation 0.5d/3d green · Documentation 7d/5d amber ·
   Unit Review 23d/7d RED with 2 deals over.

3. TEXT CLEANED. Removed from the UI:
     - the Pipeline "status footer" telling bank users that actions are "gated
       by the per-deal permissions from alpha-7" and that features "land in
       subsequent beta-batches". Internal batch names were on screen in a pilot.
     - "Deals across your scope - assured value, stage, and ownership." ->
       "Your pipeline"
     - the funnel's "N deal(s) sit at a stage no configured flow contains" -
       a developer diagnostic; the endpoint still reports it for scripts
     - "Initiative is not yet wired to a balanced-scorecard KPI" ->
       "Not linked to a balanced scorecard KPI."
   The colour legend is four words, not a paragraph.

   ALSO REMOVED: the count/value toggle. Width now follows the ideal taper, so
   the toggle no longer changed anything - a dead control is worse than none.

Verified: py_compile clean, tsc --noEmit clean, vite build clean.

REQUIRES B2.

Usage (from project root, .venv active):
    python scripts\patch_b3_funnel_shape_and_cleanup.py            # dry run
    python scripts\patch_b3_funnel_shape_and_cleanup.py --apply    # write + .pre_b3f backups
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "pipeline_funnel.py")
COMP = os.path.join("frontend", "web", "src", "components", "DefinedFunnel.tsx")
PAGE = os.path.join("frontend", "web", "src", "pages", "Pipeline.tsx")
INIT = os.path.join("frontend", "web", "src", "pages", "InitiativeDetail.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
BACKUP_SUFFIX = ".pre_b3f"

MODULE = r'''"""
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
'''

TS_NEW = r'''export interface BucketHealth {
  status: 'green' | 'amber' | 'red' | 'idle';
  avg_days: number; target_days: number; oldest_days: number; at_risk: number;
}
export interface DefinedBucket {
  key: string; label: string; weight: number;
  count: number; value: number; probability: number;
  steps: DefinedStep[];
  health: BucketHealth;
}
export interface DefinedFlow {
  flow: string; buckets: DefinedBucket[];
  deals: number; value: number; weighted: number;
}
export interface DefinedFunnel {
  flows: DefinedFlow[];
  total_deals: number;
  unplaced_deals: number;
}
'''

COMPONENT = r'''// DefinedFunnel — the pipeline centrepiece, drawn from ADMIN CONFIG.
//
// Ruling 2026-08-09: stages are never hardcoded. Every band here is a stage the
// bank configured in that product's flow, in the order it configured them, with
// the win probability it set for that stage WITHIN THAT FLOW.
//
// EMPTY STAGES ARE DRAWN. A funnel that hides the steps holding nothing is a bar
// chart of whatever happened to be busy — and the empty step is usually the
// finding: it is where deals stop arriving.
//
// THE CREDIT LAYER IS A SECOND AXIS, not a stage. Documentation / Branch Credit /
// Department / Credit Analysis / Credit Administration / TROPS say where a deal
// probably sits inside the bank, inferred from its probability. It sits beneath
// the journey and never filters it.

import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import { fetchPipelineDefinedFunnel, type DefinedFunnel as FunnelData, type DefinedFlow } from '@/lib/api';

// Cool→warm sweep: early stages cool, closing stages warm. Depth comes from a
// vertical gradient plus a soft inner highlight, so a band reads as a solid
// object rather than a coloured rectangle.
const PALETTE = ['#0082BB', '#0C7BC0', '#3F6FC4', '#6A61C0', '#9455B0', '#BE4E93', '#D75A72', '#E0A02B', '#669438'];

function bandColour(i: number, n: number): string {
  if (n <= 1) return PALETTE[0];
  const seg = (i / (n - 1)) * (PALETTE.length - 1);
  const idx = Math.min(Math.floor(seg), PALETTE.length - 2);
  const t = seg - idx;
  const hex = (h: string) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const [r1, g1, b1] = hex(PALETTE[idx]);
  const [r2, g2, b2] = hex(PALETTE[idx + 1]);
  const m = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${m(r1, r2)}, ${m(g1, g2)}, ${m(b1, b2)})`;
}

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export interface DefinedFunnelProps {
  /** Clicking a non-empty band drills into that flow + stage. Preserved from the
   *  previous funnel: dropping it would have removed a working feature quietly. */
  onStageClick?: (flow: string, stage: string) => void;
}

export default function DefinedFunnel({ onStageClick }: DefinedFunnelProps = {}) {
  const { toast } = useToast();
  const [data, setData] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(false);
  const [flowKey, setFlowKey] = useState('');
  const [hover, setHover] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void (async () => {
      try {
        const r = await fetchPipelineDefinedFunnel();
        if (!alive) return;
        setData(r);
        setFlowKey((k) => k || (r.flows[0]?.flow ?? ''));
      } catch (e) {
        if (alive) toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the funnel.' });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [toast]);

  const flow: DefinedFlow | undefined = useMemo(
    () => data?.flows.find((f) => f.flow === flowKey) ?? data?.flows[0],
    [data, flowKey]);

  const buckets = flow?.buckets ?? [];
  // Micro-steps open on demand: management reads the six buckets, an officer
  // opens the one they work in.
  const [openBucket, setOpenBucket] = useState('');

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Pipeline journey</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Each product's defined stages, in the order the bank configured them.
            </p>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {loading && <p className="py-10 text-center text-sm text-gray-400">Loading the journey…</p>}

        {!loading && data && data.flows.length === 0 && (
          <p className="py-10 text-center text-sm text-gray-400">
            No product flows configured. Define them in Administration.
          </p>
        )}

        {!loading && data && data.flows.length > 0 && (
          <>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {data.flows.map((f) => (
                <button key={f.flow} type="button" onClick={() => setFlowKey(f.flow)}
                  className={'rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors '
                    + (flow?.flow === f.flow ? 'bg-[#005B82] text-white'
                                             : 'bg-gray-100 text-gray-600 hover:bg-[#0082BB]/10')}>
                  {f.flow}
                  <span className="ml-1.5 opacity-70">{f.deals}</span>
                </button>
              ))}
            </div>

            {/* A TRUE FUNNEL: each band is a trapezoid whose top edge matches
                the band above, so the silhouette is continuous from Initiation
                to disbursement rather than a stack of separate bars. Width
                follows the ideal taper — what a healthy pipeline SHOULD look
                like — while the RAG rail on the left reports what it is
                actually doing. Shape shows the plan; colour shows the truth. */}
            <div className="mx-auto" style={{ maxWidth: 760 }}>
              {buckets.map((b, i) => {
                const wTop = 100 - (i / Math.max(buckets.length, 1)) * 62;
                const wBot = 100 - ((i + 1) / Math.max(buckets.length, 1)) * 62;
                const colour = bandColour(i, buckets.length);
                const empty = b.count === 0;
                const on = hover === b.key;
                const open = openBucket === b.key;
                const h = b.health;
                const rag = h.status === 'red' ? '#C4536F'
                  : h.status === 'amber' ? '#E0A02B'
                  : h.status === 'green' ? '#669438' : '#D8DBDF';
                return (
                  <div key={b.key}>
                    <div
                      onMouseEnter={() => setHover(b.key)}
                      onMouseLeave={() => setHover('')}
                      onClick={() => setOpenBucket(open ? '' : b.key)}
                      className="relative flex cursor-pointer items-stretch gap-2"
                    >
                      {/* the health rail — red/amber/green, per stage */}
                      <div className="w-1.5 shrink-0 rounded-full transition-all"
                           style={{ background: rag, opacity: on ? 1 : 0.85 }}
                           title={h.status === 'idle'
                             ? 'No deals at this stage'
                             : `${h.avg_days} working days on average against a ${h.target_days}-day target`} />

                      <div className="relative flex-1" style={{ height: 58 }}>
                        {/* the trapezoid */}
                        <div
                          className="absolute inset-0 transition-transform duration-200"
                          style={{
                            clipPath: `polygon(${(100 - wTop) / 2}% 0%, ${100 - (100 - wTop) / 2}% 0%, ${100 - (100 - wBot) / 2}% 100%, ${(100 - wBot) / 2}% 100%)`,
                            background: empty
                              ? 'repeating-linear-gradient(45deg,#F4F5F7,#F4F5F7 7px,#E9EBEE 7px,#E9EBEE 14px)'
                              : `linear-gradient(180deg, rgba(255,255,255,0.30) 0%, ${colour} 34%, ${colour} 62%, rgba(0,0,0,0.26) 100%), ${colour}`,
                            transform: on ? 'scaleY(1.04)' : 'none',
                            filter: on ? 'brightness(1.06)' : 'none',
                          }}
                        />
                        {/* fill: how much of this band the deals occupy */}
                        {!empty && (
                          <div className="absolute inset-y-0 left-0 flex items-center justify-center"
                               style={{ width: '100%' }}>
                            <div className="flex items-baseline gap-2 text-white drop-shadow">
                              <span className="text-lg font-semibold tabular-nums">{b.count}</span>
                              <span className="text-[11px] opacity-90">KES {kes(b.value)}</span>
                            </div>
                          </div>
                        )}
                        {empty && (
                          <div className="absolute inset-0 flex items-center justify-center">
                            <span className="text-[11px] text-gray-400">nothing here</span>
                          </div>
                        )}
                      </div>

                      <div className="w-52 shrink-0 self-center">
                        <div className={'truncate text-xs font-semibold ' + (empty ? 'text-gray-400' : 'text-gray-800')}
                             title={b.label}>
                          <span className="mr-1 text-gray-400">{open ? '▾' : '▸'}</span>
                          {b.label}
                        </div>
                        <div className="text-[10px] text-gray-400">
                          {b.weight}% · {Math.round(b.probability * 100)}% at exit
                        </div>
                        <div className="text-[10px]" style={{ color: rag }}>
                          {h.status === 'idle'
                            ? 'no deals'
                            : `${h.avg_days}d avg / ${h.target_days}d target`
                              + (h.at_risk ? ` · ${h.at_risk} over` : '')}
                        </div>
                      </div>
                    </div>

                    {open && (
                      <div className="mb-1 ml-4 space-y-1 border-l-2 border-gray-200 pl-3">
                        {b.steps.map((st) => (
                          <div key={st.stage}
                               onClick={(e) => {
                                 e.stopPropagation();
                                 if (st.count && onStageClick && flow) onStageClick(flow.flow, st.stage);
                               }}
                               className={'flex items-center gap-3 text-xs '
                                 + (st.count && onStageClick ? 'cursor-pointer hover:bg-gray-50' : '')}>
                            <span className="w-56 truncate text-gray-600" title={st.stage}>{st.stage}</span>
                            <span className="w-14 text-right tabular-nums text-gray-400">
                              {Math.round(st.probability * 100)}%
                            </span>
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100">
                              <div className="h-full rounded-full"
                                   style={{ width: `${b.count ? (st.count / Math.max(b.count, 1)) * 100 : 0}%`,
                                            background: colour }} />
                            </div>
                            <span className="w-10 text-right tabular-nums text-gray-700">{st.count}</span>
                            <span className="w-28 text-right tabular-nums text-gray-500">KES {kes(st.value)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* What the colours mean — three words, not a paragraph. */}
            <div className="mt-3 flex items-center justify-center gap-4 text-[10px] text-gray-500">
              {[['#669438', 'within target'], ['#E0A02B', 'slipping'],
                ['#C4536F', 'stalled'], ['#D8DBDF', 'no deals']].map(([c, l]) => (
                <span key={l} className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: c }} />
                  {l}
                </span>
              ))}
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3 text-xs">
              <span className="text-gray-500">
                {flow?.deals ?? 0} deals · KES {kes(flow?.value ?? 0)} ·{' '}
                <span className="font-semibold text-gray-800">
                  KES {kes(flow?.weighted ?? 0)} weighted
                </span>
              </span>
            </div>

          </>
        )}
      </Card.Body>
    </Card>
  );
}
'''

PAGE_NEW = r'''// v10.510 Phase 4 Batch β1 — Pipeline page.
//
// First read-only consumer of the α1-α7 pipeline API surface. Shows
// the caller's cascade-scoped deal list with per-deal permission
// indicators (α7) visible inline. The mutation surface (create, edit,
// advance, refer, validate, cancel/request, cancel/approve) lands in
// subsequent β-batches.
//
// What this proves end-to-end:
//   1. α1's pipeline list endpoint returns data → React renders it
//   2. α2's cascade scope filters → caller sees only own/scope deals
//   3. α3's CRUD endpoint Pydantic typing → matches our TypeScript shape
//   4. α7's permissions object → React reads it without recomputing auth
//   5. The Bearer-header JWT lifecycle from Phase 1 → carries through
//      to a brand-new authenticated endpoint
//   6. The Provider pattern from Batch 2d → extends cleanly to a new domain
//
// Layout pattern matches Dashboard.tsx:
//   - Header strip with brand.secondary background (deep navy)
//   - max-w-7xl content column
//   - Stat strip at top for at-a-glance metrics
//   - Card-wrapped Table for the deal list
//   - Footer with branding ip_notice
//
// Composition: 100% bespoke v10.496 primitives. No new visual atoms.

import { displayName } from "../lib/names";
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { usePipelineDeals } from '@/hooks/usePipelineDeals';
import { useRole } from '@/hooks/useRole';
import { fetchPipelineConfig, fetchPipelineAnalytics, fetchFunnelDrill, downloadFile } from '@/lib/api';
import { Card } from '@/components/Card';
import DefinedFunnel from '@/components/DefinedFunnel';
import { PageHeader } from '@/components/PageHeader';
import { Stat } from '@/components/Stat';
import { Badge, type BadgeTone } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Table, type Column } from '@/components/Table';
import { PermissionBadges } from '@/components/PermissionBadges';
import { parseTs } from '@/lib/datetime';
import {
  stageTone,
  type PipelineDeal,
  type PipelineConfig,
  type PipelineAnalyticsResponse,
  type FunnelDrillResponse,
} from '@/types/pipeline';


// ── Display helpers ─────────────────────────────────────────────────────

/** Format a deal_value in the tenant's currency. Compact format for table cells. */
function formatValue(v: number, symbol: string): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  return `${symbol} ${v.toLocaleString()}`;
}

/** Days a deal has been open, from its earliest available timestamp. */
function daysOpen(deal: PipelineDeal): number | null {
  const raw = deal.created_at || deal.open_date || deal.updated_at;
  if (!raw) return null;
  // parseTs, not new Date: a date-only open_date must anchor to LOCAL midnight,
  // otherwise the age is measured from 03:00 and can round down a whole day.
  const parsed = parseTs(raw);
  if (!parsed) return null;
  const start = parsed.getTime();
  if (!Number.isFinite(start)) return null;
  const diff = Date.now() - start;
  if (diff < 0) return 0;
  return Math.floor(diff / 86_400_000);
}

/** Traffic-light cell for a deal's attached SLA status. Null when no SLA applies
 *  (closed / no timestamp). */
function slaCell(deal: PipelineDeal): { tone: BadgeTone; label: string; title: string } | null {
  const s = deal.sla;
  if (!s || !s.state) return null;
  const clock = s.clock === 'step' ? (s.step || 'step').replace(/_/g, ' ') : 'age';
  if (s.state === 'breached') {
    return {
      tone: 'danger',
      label: `breached +${s.overdue_business_days ?? 0}`,
      title: `${clock}: ${s.elapsed_business_days ?? '?'}/${s.target_days ?? '?'} bd — escalate to ${(s.escalate_to || '').replace(/_/g, ' ') || 'step owner'}`,
    };
  }
  if (s.state === 'due_soon') {
    return { tone: 'warning', label: 'due soon', title: `${clock}: ${s.remaining_business_days ?? '?'} bd to target` };
  }
  return { tone: 'success', label: 'on track', title: `${clock}: ${s.remaining_business_days ?? '?'} bd to target` };
}


// ── Page component ──────────────────────────────────────────────────────

export function Pipeline() {
  const { branding } = useBranding();
  const { user } = useRole();
  const { deals, count, loading, error, refetch } = usePipelineDeals();

  // SLA traffic-light filter, driven by ?sla=on_track|due_soon|breached (e.g. from the
  // Analytics SLA summary card). Filters the already-loaded deals client-side on sla.state.
  const [searchParams, setSearchParams] = useSearchParams();
  const slaFilter = searchParams.get('sla');
  // Win-probability band filter (?winprob=high|medium|low). high ≥75, medium 40–74,
  // low <40 — derived per-deal from the current stage's product flow. Combines with sla.
  const winprobFilter = searchParams.get('winprob');
  const winprobBand = (wp: number | null | undefined): 'high' | 'medium' | 'low' | null => {
    if (typeof wp !== 'number') return null;
    return wp >= 75 ? 'high' : wp >= 40 ? 'medium' : 'low';
  };
  const [config, setConfig] = useState<PipelineConfig | null>(null);
  const [segmentFilter, setSegmentFilter] = useState('');
  // Two-level segment model, sourced from the configurable business units (customer_segments):
  //   Business unit (Consumer/Commercial/CIB/Treasury) -> its sub-segments (Premier/SME/...).
  // Each visible deal's sub-segment is resolved to its business unit via a reverse map, then
  // grouped by unit. A single-unit viewer (e.g. Consumer) therefore sees ONLY that unit's
  // sub-segments; a leaked cross-unit value groups under its OWN unit, never polluting another.
  const segmentGroups = useMemo(() => {
    const cfgSegs = config?.customer_segments ?? {};
    // reverse map: sub-segment -> business unit
    const subToUnit = new Map<string, string>();
    for (const [unit, subs] of Object.entries(cfgSegs)) {
      for (const sub of subs) subToUnit.set(sub, unit);
    }
    // tally sub-segment counts present in visible deals
    const counts = new Map<string, number>();
    for (const d of deals) {
      const k = (d.segment && String(d.segment).trim()) || 'Unclassified';
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    // build ordered groups: business unit -> [{key, count}] in config order
    const groups: { unit: string; subs: { key: string; count: number }[] }[] = [];
    for (const [unit, subs] of Object.entries(cfgSegs)) {
      const present = subs
        .filter((sub) => counts.has(sub))
        .map((sub) => ({ key: sub, count: counts.get(sub) ?? 0 }));
      if (present.length) groups.push({ unit, subs: present });
    }
    // any present sub-segment that IS a bare business-unit name (mis-tagged) or unknown:
    // collect under an 'Other' group so it's visible but not mixed into a real unit.
    const known = new Set<string>();
    for (const g of groups) for (const s of g.subs) known.add(s.key);
    const other: { key: string; count: number }[] = [];
    for (const [k, c] of counts.entries()) {
      if (k === 'Unclassified') continue;
      if (!known.has(k) && !subToUnit.has(k)) other.push({ key: k, count: c });
    }
    if (other.length) groups.push({ unit: 'Other', subs: other });
    if (counts.has('Unclassified')) {
      groups.push({ unit: 'Unclassified', subs: [{ key: 'Unclassified', count: counts.get('Unclassified') ?? 0 }] });
    }
    return groups;
  }, [deals, config]);
  const singleUnit = segmentGroups.length === 1;
  const visibleDeals = useMemo(
    () => deals.filter((d) =>
      (!slaFilter || d.sla?.state === slaFilter)
      && (!winprobFilter || winprobBand(d.win_probability) === winprobFilter)
      && (!segmentFilter || (d.segment || 'Unclassified') === segmentFilter)),
    [deals, slaFilter, winprobFilter, segmentFilter],
  );
  const clearSlaFilter = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('sla');
    setSearchParams(next, { replace: true });
  };
  const setWinprobFilter = (band: string) => {
    const next = new URLSearchParams(searchParams);
    if (band) next.set('winprob', band); else next.delete('winprob');
    setSearchParams(next, { replace: true });
  };

  // Batch A: admin-configured category/stage filters (from /api/pipeline/stages)
  const [catFilter, setCatFilter] = useState('');
  const [stageFilter, setStageFilter] = useState('');

  // Funnel stage-drill: click a band → fetch deals at that class+stage,
  // broken down by product and segment.
  const [drill, setDrill] = useState<FunnelDrillResponse | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);
  const [drillVisible, setDrillVisible] = useState(50);
  const [exporting, setExporting] = useState(false);
  const drillRef = useRef<HTMLDivElement | null>(null);
  const onStageDrill = (cls: string, stage: string): void => {
    setDrillLoading(true);
    setDrill(null);
    setDrillVisible(50);
    fetchFunnelDrill(cls, stage)
      .then((d) => setDrill(d))
      .catch(() => setDrill(null))
      .finally(() => setDrillLoading(false));
  };
  // When the drill opens, bring the panel into view (the funnel can be tall,
  // so the panel would otherwise open below the fold).
  useEffect(() => {
    if (drill && drillRef.current) {
      drillRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [drill]);

  useEffect(() => {
    let active = true;
    fetchPipelineConfig()
      .then((c) => { if (active) setConfig(c); })
      .catch(() => { /* dropdowns stay empty if config can't load */ });
    return () => { active = false; };
  }, []);

  // Analytics: validated/pending split, per-class buckets, the validated
  // funnel, and the scope-aware pending-validation count. Refetched whenever
  // the deal list settles (after create/validate/advance/refresh).
  const [analytics, setAnalytics] = useState<PipelineAnalyticsResponse | null>(null);
  useEffect(() => {
    if (loading) return;
    let active = true;
    fetchPipelineAnalytics()
      .then((a) => { if (active) setAnalytics(a); })
      .catch(() => { /* tiles fall back to local sums if analytics fails */ });
    return () => { active = false; };
  }, [loading, count]);

  // Stage options narrow to the selected category's flow; else all stages.
  const stageOptions = useMemo(() => {
    if (!config) return [] as string[];
    if (catFilter) {
      const cat = config.deal_categories.find((c) => c.category === catFilter);
      if (cat) return cat.stages;
    }
    return config.stages.map((s) => s.stage);
  }, [config, catFilter]);

  const onCategoryChange = (value: string) => {
    setCatFilter(value);
    setStageFilter('');
    void refetch({ category: value || undefined });
  };
  const onStageChange = (value: string) => {
    setStageFilter(value);
    void refetch({ category: catFilter || undefined, stage: value || undefined });
  };
  const navigate = useNavigate();

  const sym = branding?.currency_symbol ?? '';

  // Table column config — typed against PipelineDeal so render functions
  // get full intellisense on row data.
  const columns: Column<PipelineDeal>[] = useMemo(() => [
    {
      key: 'id',
      header: 'Deal ID',
      width: 110,
      sortable: true,
      exportValue: (row) => row.id,
      render: (row) => (
        <span className="font-mono text-xs text-gray-600">{row.id}</span>
      ),
    },
    {
      key: 'client_name',
      header: 'Client',
      sortable: true,
      exportValue: (row) => row.client_name || '',
      render: (row) => (
        <div>
          <div className="font-medium text-gray-900">{row.client_name || '—'}</div>
          {row.product_type && (
            <div className="text-xs text-gray-500 mt-0.5">{row.product_type}</div>
          )}
        </div>
      ),
    },
    {
      key: 'stage',
      header: 'Stage',
      sortable: true,
      exportValue: (row) => row.stage,
      render: (row) => (
        <Badge tone={stageTone(row.stage)} size="sm">{row.stage}</Badge>
      ),
    },
    {
      key: 'deal_value',
      header: 'Value',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => Number(row.amount_kes ?? row.deal_value) || 0,
      exportValue: (row) => String(row.amount_kes ?? row.deal_value ?? ''),
      render: (row) => (
        <span className="font-medium text-gray-900">
          {formatValue(Number(row.amount_kes ?? row.deal_value), branding?.currency_symbol ?? '')}
        </span>
      ),
    },
    {
      key: 'aging',
      header: 'Age',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => daysOpen(row) ?? -1,
      exportValue: (row) => { const d = daysOpen(row); return d == null ? '' : String(d); },
      render: (row) => {
        const d = daysOpen(row);
        if (d == null) return <span className="text-xs text-gray-400">—</span>;
        const stale = d > 14;
        return (
          <span className={`text-xs font-medium ${stale ? 'text-red-600' : 'text-gray-600'}`}>
            {d}d{stale ? ' · stale' : ''}
          </span>
        );
      },
    },
    {
      key: 'sla',
      header: 'SLA',
      exportValue: (row) => row.sla?.state || '',
      render: (row) => {
        const c = slaCell(row);
        if (!c) return <span className="text-xs text-gray-300">—</span>;
        return <span title={c.title}><Badge tone={c.tone} size="sm">{c.label}</Badge></span>;
      },
    },
    {
      key: 'win_probability',
      header: 'Win %',
      align: 'right',
      sortable: true,
      sortAccessor: (row) => (typeof row.win_probability === 'number' ? row.win_probability : -1),
      exportValue: (row) => (typeof row.win_probability === 'number' ? String(row.win_probability) : ''),
      render: (row) => {
        const wp = row.win_probability;
        if (typeof wp !== 'number') return <span className="text-xs text-gray-300">—</span>;
        const tone: BadgeTone = wp >= 75 ? 'success' : wp >= 40 ? 'info' : 'neutral';
        return (
          <span title="Likelihood of closing, from the current stage's product flow">
            <Badge tone={tone} size="sm">{Math.round(wp)}%</Badge>
          </span>
        );
      },
    },
    {
      key: 'staff_name',
      header: 'Owner',
      sortable: true,
      exportValue: (row) => row.staff_name || '',
      render: (row) => (
        <div>
          <div className="text-sm text-gray-800">{row.staff_name ? displayName(row.staff_name) : '—'}</div>
          {row.staff_code && (
            <div className="text-xs text-gray-400 mt-0.5 font-mono">
              {row.staff_code}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'permissions',
      header: 'You can',
      render: (row) => <PermissionBadges permissions={row.permissions} />,
    },
  // intentionally not depending on the dynamic data; column config is stable
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [branding?.currency_symbol]);

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        ribbon
        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'EKE Sales Pro' }]}
        title="EKE Sales Pro"
        subtitle="Your pipeline"
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setExporting(true);
                downloadFile('/pipeline/export/xlsx', 'EKE_Pipeline.xlsx')
                  .catch(() => { /* surfaced via button state only */ })
                  .finally(() => setExporting(false));
              }}
              disabled={exporting}
            >
              {exporting ? 'Exporting…' : 'Export Excel'}
            </Button>
            <Button variant="primary" onClick={() => navigate('/pipeline/new')}>
              + New Deal
            </Button>
          </>
        }
      />

      {/* Main content */}
      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-8">
        {/* Assured pipeline by product class — validated value headline,
            pending-assurance beneath. Sourced from /api/pipeline/analytics. */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Stat
            label="Asset Pipeline"
            value={analytics ? formatValue(analytics.pipelines.asset.value, sym) : '—'}
            sub={analytics && analytics.pipelines.asset.pending_value > 0
              ? `${formatValue(analytics.pipelines.asset.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="primary"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Liability Pipeline"
            value={analytics ? formatValue(analytics.pipelines.liability.value, sym) : '—'}
            sub={analytics && analytics.pipelines.liability.pending_value > 0
              ? `${formatValue(analytics.pipelines.liability.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="success"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Insurance"
            value={analytics ? formatValue(analytics.pipelines.insurance.value, sym) : '—'}
            sub={analytics && analytics.pipelines.insurance.pending_value > 0
              ? `${formatValue(analytics.pipelines.insurance.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="lime"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Other"
            value={analytics ? formatValue(analytics.pipelines.other.value, sym) : '—'}
            sub={analytics && analytics.pipelines.other.pending_value > 0
              ? `${formatValue(analytics.pipelines.other.pending_value, sym)} pending assurance`
              : 'Assured'}
            loading={loading}
            stripe={false}
            tone="violet"
            onClick={() => navigate('/analytics')}
          />
        </div>

        {/* Scope summary row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          <Stat
            label="Deals Visible"
            value={loading ? '—' : count}
            sub="In your cascade scope"
            loading={loading}
            stripe={false}
            tone="teal"
            onClick={() => navigate('/analytics')}
          />
          <Stat
            label="Pending Validation"
            value={analytics ? analytics.totals.pending_validation : (loading ? '—' : 0)}
            sub={analytics && analytics.totals.pending_validation > 0
              ? 'Awaiting your sign-off'
              : 'Nothing to validate'}
            loading={loading}
            stripe={false}
            tone={analytics && analytics.totals.pending_validation > 0 ? 'accent' : 'neutral'}
            onClick={() => navigate('/pipeline/queues')}
          />
          <Stat
            label="Total Assured"
            value={analytics ? formatValue(analytics.totals.total_value, sym) : '—'}
            sub={analytics && analytics.totals.pending_value > 0
              ? `${formatValue(analytics.totals.pending_value, sym)} pending assurance`
              : 'All validated'}
            loading={loading}
            stripe={false}
            tone="secondary"
            onClick={() => navigate('/analytics')}
          />
        </div>

        {/* Validated pipeline funnel */}
        <DefinedFunnel onStageClick={onStageDrill} />

        {/* Funnel stage-drill panel */}
        {(drillLoading || drill) && (
          <div ref={drillRef} className="scroll-mt-24">
          <Card className="mt-4 ring-2 ring-[var(--brand-primary)]/30">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">
                {drill ? `${drill.cls === 'all' ? 'All' : drill.cls[0].toUpperCase() + drill.cls.slice(1)} · ${drill.stage}` : 'Loading…'}
              </h2>
              <button
                type="button"
                onClick={() => setDrill(null)}
                className="text-xs text-gray-400 hover:text-gray-700"
              >
                Close ✕
              </button>
            </Card.Header>
            <Card.Body>
              {drillLoading && <div className="h-24 animate-pulse rounded bg-gray-100" />}
              {drill && (
                <div>
                  <div className="mb-4 text-sm text-gray-500">
                    <span className="font-semibold text-gray-800">{drill.totals.count}</span> assured deals ·{' '}
                    <span className="font-semibold text-gray-800">{formatValue(drill.totals.value, sym)}</span>
                  </div>
                  <div className="grid gap-6 md:grid-cols-3">
                    <DrillBreakdown title="By segment" rows={drill.by_segment.map((s) => ({ label: s.segment, value: s.value, count: s.count }))} sym={sym} />
                    <DrillBreakdown title="By sector" rows={drill.by_sector.map((s) => ({ label: s.sector, value: s.value, count: s.count }))} sym={sym} />
                    <DrillBreakdown title="By product" rows={drill.by_product.map((p) => ({ label: p.product, value: p.value, count: p.count }))} sym={sym} />
                  </div>
                  {drill.deals.length > 0 && (
                    <div className="mt-6 overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                            <th className="py-2 pr-3">Deal</th>
                            <th className="py-2 pr-3">Client</th>
                            <th className="py-2 pr-3">Product</th>
                            <th className="py-2 pr-3">Segment</th>
                            <th className="py-2 pr-3 text-right">Value</th>
                            <th className="py-2 pr-3">Owner</th>
                          </tr>
                        </thead>
                        <tbody>
                          {drill.deals.slice(0, drillVisible).map((d) => (
                            <tr key={d.id} className="border-b border-gray-100">
                              <td className="py-1.5 pr-3 font-mono text-xs text-gray-500">{d.id}</td>
                              <td className="py-1.5 pr-3 text-gray-800">{d.client_name}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{d.product_type}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{d.segment}</td>
                              <td className="py-1.5 pr-3 text-right tabular-nums text-gray-800">{formatValue(d.amount_kes, sym)}</td>
                              <td className="py-1.5 pr-3 text-gray-600">{displayName(d.staff_name)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {drill.deals.length > drillVisible ? (
                        <div className="mt-2 flex items-center gap-3">
                          <Button variant="ghost" size="sm" onClick={() => setDrillVisible((n) => n + 50)}>
                            Show more ({drill.deals.length - drillVisible} more)
                          </Button>
                          <span className="text-xs text-gray-400">Showing {drillVisible} of {drill.deals.length}</span>
                        </div>
                      ) : drill.deals.length > 50 ? (
                        <div className="mt-2 text-xs text-gray-400">Showing all {drill.deals.length} deals.</div>
                      ) : null}
                    </div>
                  )}
                </div>
              )}
            </Card.Body>
          </Card>
          </div>
        )}

        {/* Error panel — only renders on error */}
        {error && (
          <Card className="mt-6">
            <Card.Body>
              <div className="flex items-center gap-3">
                <Badge tone="danger">Error</Badge>
                <div className="flex-1 text-sm text-gray-700">{error}</div>
                <Button variant="ghost" size="sm" onClick={() => void refetch()}>
                  Retry
                </Button>
              </div>
            </Card.Body>
          </Card>
        )}

        {/* Deal table */}
        <Card className="mt-8" padding="none">
          <Card.Header>
            <div className="flex items-center gap-3">
              <h2 className="text-base font-semibold text-gray-900">
                Pipeline Deals
              </h2>
                </div>
            <div className="flex items-center gap-2">
              <select
                value={catFilter}
                onChange={(e) => onCategoryChange(e.target.value)}
                aria-label="Filter by deal category"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All categories</option>
                {config?.deal_categories.map((c) => (
                  <option key={c.category} value={c.category}>{c.category}</option>
                ))}
              </select>
              <select
                value={stageFilter}
                onChange={(e) => onStageChange(e.target.value)}
                aria-label="Filter by stage"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All stages</option>
                {stageOptions.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              {segmentGroups.length > 0 && (
                <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Filter by segment">
                  <div className="flex items-center gap-1 rounded-lg bg-gray-100 p-1">
                    <button
                      type="button"
                      onClick={() => setSegmentFilter('')}
                      className={[
                        'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                        segmentFilter === '' ? 'bg-white text-[var(--brand-secondary)] shadow-sm'
                                             : 'text-gray-500 hover:text-gray-800',
                      ].join(' ')}
                    >
                      All
                    </button>
                  </div>
                  {segmentGroups.map((g) => (
                    <div key={g.unit} className="flex items-center gap-1 rounded-lg bg-gray-100 p-1">
                      {!singleUnit && (
                        <span className="px-2 text-[10px] font-semibold uppercase tracking-wide text-gray-400">{g.unit}</span>
                      )}
                      {g.subs.map((sg) => {
                        const on = segmentFilter === sg.key;
                        return (
                          <button
                            key={sg.key}
                            type="button"
                            onClick={() => setSegmentFilter(sg.key)}
                            className={[
                              'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                              on ? 'bg-white text-[var(--brand-secondary)] shadow-sm'
                                 : 'text-gray-500 hover:text-gray-800',
                            ].join(' ')}
                          >
                            {sg.key}
                            <span className="ml-1.5 text-gray-400">{sg.count}</span>
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
              )}
              <select
                value={winprobFilter ?? ''}
                onChange={(e) => setWinprobFilter(e.target.value)}
                aria-label="Filter by win probability"
                className="h-9 px-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              >
                <option value="">All win %</option>
                <option value="high">High (≥75%)</option>
                <option value="medium">Medium (40–74%)</option>
                <option value="low">Low (&lt;40%)</option>
              </select>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void refetch()}
                loading={loading}
              >
                Refresh
              </Button>
            </div>
          </Card.Header>
          <Card.Body className="p-4">
            {slaFilter && (
              <div className="mb-3 flex items-center gap-2 text-sm">
                <span className="text-gray-500">SLA filter:</span>
                <Badge
                  tone={slaFilter === 'breached' ? 'danger' : slaFilter === 'due_soon' ? 'warning' : 'success'}
                  size="sm"
                >
                  {slaFilter.replace(/_/g, ' ')}
                </Badge>
                <span className="text-xs text-gray-400">{visibleDeals.length} of {deals.length}</span>
                <button onClick={clearSlaFilter} className="text-xs text-brand-primary hover:underline">clear</button>
              </div>
            )}
            {winprobFilter && (
              <div className="mb-3 flex items-center gap-2 text-sm">
                <span className="text-gray-500">Win probability:</span>
                <Badge
                  tone={winprobFilter === 'high' ? 'success' : winprobFilter === 'medium' ? 'info' : 'neutral'}
                  size="sm"
                >
                  {winprobFilter === 'high' ? 'High (≥75%)' : winprobFilter === 'medium' ? 'Medium (40–74%)' : 'Low (<40%)'}
                </Badge>
                <span className="text-xs text-gray-400">{visibleDeals.length} of {deals.length}</span>
                <button onClick={() => setWinprobFilter('')} className="text-xs text-brand-primary hover:underline">clear</button>
              </div>
            )}
            <Table<PipelineDeal>
              columns={columns}
              rows={visibleDeals}
              rowKey="id"
              loading={loading}
              searchable
              searchPlaceholder="Search deals by client, stage, owner…"
              paginated
              pageSize={25}
              onRowClick={(row) => navigate(`/pipeline/${encodeURIComponent(row.id)}`)}
              empty={
                <div className="py-8">
                  <div className="text-base text-gray-700 font-medium">
                    No deals in your scope.
                  </div>
                  <div className="text-sm text-gray-500 mt-1">
                    {user?.role && `As ${user.role}, you see deals from your cascade.`}
                  </div>
                </div>
              }
            />
          </Card.Body>
        </Card>

        {/* IP notice footer — verbatim from /api/branding */}
        <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
          {branding?.ip_notice}
        </footer>
      </main>
    </div>
  );
}

// ── Drill breakdown: a compact value-ranked bar list (segment / product) ──
function DrillBreakdown({
  title, rows, sym,
}: {
  title: string;
  rows: { label: string; value: number; count: number }[];
  sym: string;
}) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  const PALETTE = ['#06b6d4', '#3b82f6', '#6366f1', '#a855f7', '#ec4899', '#f59e0b', '#10b981', '#14b8a6'];
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</div>
      {rows.length === 0 ? (
        <div className="text-sm text-gray-400">No data.</div>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 8).map((r, i) => (
            <div key={r.label} className="flex items-center gap-3">
              <div className="w-28 shrink-0 truncate text-xs text-gray-600" title={r.label}>{r.label}</div>
              <div className="h-4 flex-1 rounded bg-gray-100">
                <div
                  className="h-4 rounded"
                  style={{ width: `${Math.max(4, Math.round((r.value / max) * 100))}%`, background: PALETTE[i % PALETTE.length] }}
                />
              </div>
              <div className="w-32 shrink-0 text-right text-xs text-gray-500">
                {formatValue(r.value, sym)} <span className="text-gray-400">· {r.count}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
'''

INIT_NEW = r'''// v10.541 Phase 8 Batch γ4b — Single initiative detail page.

import { useParams, useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useInitiativeDetail } from '@/hooks/useInitiativeDetail';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { PageHeader } from '@/components/PageHeader';
import { Skeleton } from '@/components/Skeleton';
import {
  ragTone,
  phaseTone,
  riskTone,
  milestoneStateTone,
  formatBudget,
  type InitiativeMilestone,
  type InitiativeDependency,
  type InitiativeBsc,
} from '@/types/initiatives';


export function InitiativeDetail() {
  const { initiativeId } = useParams<{ initiativeId: string }>();
  const { branding } = useBranding();
  const { initiative, loading, error, notFound, refetch } = useInitiativeDetail(initiativeId);
  const navigate = useNavigate();

  const currencySymbol = branding?.currency_symbol ?? 'KES';

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Initiative Detail"
        breadcrumbs={[{ label: 'Initiatives', to: '/initiatives' }, { label: initiativeId ?? '—' }]}
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate('/initiatives')}>
            ← Back to Initiatives
          </Button>
        }
      />

      <main className="max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6 space-y-5">

        {loading && (
          <Card>
            <Card.Body>
              <Skeleton className="h-8 w-1/2" />
              <Skeleton className="h-4 w-full mt-3" />
              <Skeleton className="h-4 w-3/4 mt-2" />
            </Card.Body>
          </Card>
        )}

        {notFound && !loading && (
          <Card>
            <Card.Body>
              <div className="text-sm text-gray-700">
                <span className="font-medium">Initiative not found.</span> No initiative with id{' '}
                <span className="font-mono">{initiativeId}</span> is registered. This could be a
                stale link, a typo in the id, or the engine has no data file yet.
              </div>
              <div className="mt-3">
                <Button variant="primary" size="sm" onClick={() => navigate('/initiatives')}>
                  Back to portfolio
                </Button>
              </div>
            </Card.Body>
          </Card>
        )}

        {error && !loading && !notFound && (
          <Card>
            <Card.Body>
              <div className="text-sm text-red-700">{error}</div>
              <div className="mt-3">
                <Button variant="ghost" size="sm" onClick={() => refetch()}>
                  Retry
                </Button>
              </div>
            </Card.Body>
          </Card>
        )}

        {!loading && !error && !notFound && initiative && (
          <>
            {/* ─── Identity card ─── */}
            <Card stripe="primary">
              <Card.Header>
                <div className="flex items-center gap-3 flex-wrap">
                  <h2 className="text-lg font-semibold text-brand-secondary">
                    {(initiative.name as string) ?? '—'}
                  </h2>
                  {initiative.rag && (
                    <Badge tone={ragTone(initiative.rag as string)} size="md">
                      RAG: {initiative.rag as string}
                    </Badge>
                  )}
                  {initiative.phase && (
                    <Badge tone={phaseTone(initiative.phase as string)} size="sm">
                      {initiative.phase as string}
                    </Badge>
                  )}
                  {initiative.risk_level && (
                    <Badge tone={riskTone(initiative.risk_level as string)} size="sm">
                      Risk: {initiative.risk_level as string}
                    </Badge>
                  )}
                </div>
                <span className="font-mono text-xs text-gray-500">{(initiative.id as string) ?? '—'}</span>
              </Card.Header>
              <Card.Body>
                {initiative.description ? (
                  <p className="text-sm text-gray-700">{initiative.description as string}</p>
                ) : (
                  <p className="text-sm text-gray-400 italic">No description provided.</p>
                )}

                <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <KV label="Owner"      value={(initiative.owner as string) ?? '—'} />
                  <KV label="Start"      value={(initiative.start_date as string) ?? '—'} />
                  <KV label="End"        value={(initiative.end_date as string) ?? '—'} />
                  <KV label="Budget"     value={formatBudget(initiative.budget as number | undefined, currencySymbol)} />
                </div>
              </Card.Body>
            </Card>


            {/* ─── Milestones ─── */}
            <Card>
              <Card.Header>
                <h3 className="text-base font-semibold text-gray-900">
                  Milestones ({(initiative.milestones as InitiativeMilestone[] | undefined)?.length ?? 0})
                </h3>
              </Card.Header>
              <Card.Body className="p-0">
                {!initiative.milestones || (initiative.milestones as InitiativeMilestone[]).length === 0 ? (
                  <div className="px-6 py-4 text-xs text-gray-400 italic">No milestones registered.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                          <th className="px-4 py-3">Milestone</th>
                          <th className="px-4 py-3">Due</th>
                          <th className="px-4 py-3">State</th>
                          <th className="px-4 py-3">Completed</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {(initiative.milestones as InitiativeMilestone[]).map((m, i) => (
                          <tr key={m.id ?? `ms-${i}`} className="hover:bg-gray-50">
                            <td className="px-4 py-2 font-medium text-gray-900">{m.name ?? '—'}</td>
                            <td className="px-4 py-2 text-xs text-gray-700">{m.due_date ?? '—'}</td>
                            <td className="px-4 py-2">
                              <Badge tone={milestoneStateTone(m.state as string)} size="sm">
                                {(m.state as string) ?? '—'}
                              </Badge>
                            </td>
                            <td className="px-4 py-2 text-xs text-gray-600">{m.completed_at ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card.Body>
            </Card>


            {/* ─── BSC linkage ─── */}
            <Card>
              <Card.Header>
                <h3 className="text-base font-semibold text-gray-900">
                  BSC linkage ({(initiative.bsc_linkage as InitiativeBsc[] | undefined)?.length ?? 0})
                </h3>
              </Card.Header>
              <Card.Body className="p-0">
                {!initiative.bsc_linkage || (initiative.bsc_linkage as InitiativeBsc[]).length === 0 ? (
                  <div className="px-6 py-4 text-xs text-gray-400 italic">
                    Not linked to a balanced scorecard KPI.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                          <th className="px-4 py-3">Perspective</th>
                          <th className="px-4 py-3">KPI ID</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {(initiative.bsc_linkage as InitiativeBsc[]).map((b, i) => (
                          <tr key={`bsc-${i}`}>
                            <td className="px-4 py-2 text-sm text-gray-700">{b.perspective ?? '—'}</td>
                            <td className="px-4 py-2 text-xs font-mono text-gray-600">{b.kpi_id ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card.Body>
            </Card>


            {/* ─── Dependencies ─── */}
            <Card>
              <Card.Header>
                <h3 className="text-base font-semibold text-gray-900">
                  Dependencies ({(initiative.dependencies as InitiativeDependency[] | undefined)?.length ?? 0})
                </h3>
              </Card.Header>
              <Card.Body className="p-0">
                {!initiative.dependencies || (initiative.dependencies as InitiativeDependency[]).length === 0 ? (
                  <div className="px-6 py-4 text-xs text-gray-400 italic">No upstream dependencies registered.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                          <th className="px-4 py-3">Depends on</th>
                          <th className="px-4 py-3">Status</th>
                          <th className="px-4 py-3"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {(initiative.dependencies as InitiativeDependency[]).map((d, i) => (
                          <tr key={d.depends_on_id ?? `dep-${i}`} className="hover:bg-gray-50">
                            <td className="px-4 py-2 text-sm text-gray-700">
                              {d.depends_on_name ?? '—'}
                              {d.depends_on_id && <span className="text-gray-400 ml-1 font-mono text-xs">({d.depends_on_id})</span>}
                            </td>
                            <td className="px-4 py-2 text-xs text-gray-600">{d.status ?? '—'}</td>
                            <td className="px-4 py-2 text-right">
                              {d.depends_on_id && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => navigate(`/initiatives/${encodeURIComponent(String(d.depends_on_id))}`)}
                                >
                                  View →
                                </Button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card.Body>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}


// ── KV helper ────────────────────────────────────────────────────────────

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-sm text-gray-900 mt-0.5">{value}</div>
    </div>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (MOD, COMP, PAGE, INIT, APITS):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_b2_bucket_funnel_ui.py first." % p)
            return 1

    cur_mod = open(MOD, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()
    if "bucket_health" in cur_mod:
        print("ABORT: bucket_health already present - B3 looks applied.")
        return 1
    if "bucket_view" not in cur_mod:
        print("ABORT: apply patch_b1_stage_buckets.py first.")
        return 1

    a = ts.index("export interface BucketHealth {") if "BucketHealth" in ts else -1
    if a >= 0:
        print("ABORT: api.ts already has BucketHealth.")
        return 1
    anchor = "export async function fetchPipelineDefinedFunnel()"
    if ts.count(anchor) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(anchor))
        return 1
    # BucketHealth must sit with the other funnel types, before the fetcher.
    i = ts.index("export interface DefinedBucket {")
    j = ts.index(anchor, i)
    ts = ts[:i] + TS_NEW + ts[j:]
    print("  ok  api.ts - BucketHealth on the bucket type")

    for token in ("bucket_health", "_days_in_stage", "DEFAULT_BUCKET_TARGET_DAYS",
                  "business_days_between"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    if '"health": bucket_health' not in MODULE:
        print("ABORT: bucket_view does not attach health.")
        return 1
    for token in ("clipPath", "polygon(", "within target", "stalled"):
        if token not in COMPONENT:
            print("ABORT: embedded component missing %r." % token)
            return 1
    # The clean-up must have actually happened.
    # Check the RENDERED strings, not bare words: "subsequent" also appears in
    # a source comment at the top of the file, which no user ever sees.
    for bad, where, blob in (("in subsequent", "Pipeline page", PAGE_NEW),
                             ("Deals across your scope", "Pipeline page", PAGE_NEW),
                             ("no configured flow contains", "funnel", COMPONENT),
                             ("not yet wired", "Initiative page", INIT_NEW)):
        if bad in blob:
            print("ABORT: %r survives in the %s." % (bad, where))
            return 1
    for name, blob in (("component", COMPONENT), ("page", PAGE_NEW), ("initiative", INIT_NEW)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: shape, health, and the text clean-up all verified")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((MOD, MODULE), (APITS, ts), (COMP, COMPONENT),
                          (PAGE, PAGE_NEW), (INIT, INIT_NEW)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  pipeline_funnel.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd, then restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
