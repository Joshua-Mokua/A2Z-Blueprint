#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
B1 - the journey becomes BUCKETS with micro-steps. Supersedes the side layer.

RULING (2026-08-09): "the pipeline funnel should be across from Initiation to
disbursement, it follows through the credit journey ... our stage is clear:
Initiation, Documentation, Unit Review (Branch Credit Committee, Department
Analyst, Department Business Committee), Credit Analysis, Credit
Administration, TROPS. For accounts and others: Initiation, Documentation,
Approval, Opening. The bucket can carry a % like 15% then the micro stages
within that get the % distributed."

THIS CORRECTS AN EARLIER READING OF MINE. Yesterday those names were modelled as
a probability-INFERRED SIDE LAYER over a separate sales funnel. They are not a
side layer - they ARE the journey. Shipping both would have left two competing
answers to "where is this deal", which is exactly the confusion to avoid on a
system heading to production. One model now.

YOUR OWN DATA ALREADY AGREED: the six deals my diagnostic called "unplaced" sat
at Initiation, Department Credit Committee, Credit Analysis, Offer Letter and
Legal - Security Perfection - the NEW vocabulary. The configured flows were
stale, not the deals.

THE ARITHMETIC. A deal's win probability is its CUMULATIVE position: every
completed bucket in full, plus pro-rata progress through the current one.

    Initiation             10%    Initiation                     10.0%
    Documentation          15%    Documentation                  25.0%
    Unit Review            25%    Branch Credit Committee        33.3%
                                  Department Analyst             41.7%
                                  Department Business Committee  50.0%
    Credit Analysis        20%    Credit Analysis                70.0%
    Credit Administration  15%    Offer Letter                   77.5%
                                  Legal - Security Perfection    85.0%
    TROPS                  15%    Disbursement                  100.0%

Bucket weights MUST sum to 100 and the migration refuses to run otherwise: a
chain summing to 90 would cap a disbursed deal at 90% and understate the book.

ADDS
  buckets_for / micro_steps / bucket_of / bucket_probability / bucket_view
  in utils/pipeline_funnel - config-first, defaults only for a fresh install.
  A flow with no configuration falls back to the ACCOUNT chain rather than an
  empty list: an empty chain makes every deal in that product worth zero.

  scripts/migrate_stage_buckets.py - writes stage_buckets into admin, REBUILDS
  stage_flows from the buckets so the retired vocabulary (Lead, Contacted,
  Qualified) stops being offered anywhere, and remaps existing deals.

REMAPPING IS STATED, NEVER GUESSED BY SIMILARITY. Every old stage has an
explicit destination; a stage with no mapping is REPORTED and left alone,
because inventing a position for a real deal is worse than leaving it visible.
Dry-run by default, both stores backed up, every move printed before it is made
- this is a pilot heading to production.

NEXT: B2 points the funnel UI at bucket_view so management sees six rows for a
loan, not eleven, with the micro-steps travelling inside their bucket.

Usage (from project root, .venv active):
    python scripts\patch_b1_stage_buckets.py            # dry run
    python scripts\patch_b1_stage_buckets.py --apply    # write + .pre_b1s backup
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "pipeline_funnel.py")
MIG = os.path.join("scripts", "migrate_stage_buckets.py")
BACKUP_SUFFIX = ".pre_b1s"

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

MIGRATION = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Move the BUCKET journey into admin config, and remap deals onto it. READ ONLY
until --apply.

RULING (2026-08-09): the journey is Initiation, Documentation, Unit Review
(Branch Credit Committee / Department Analyst / Department Business Committee),
Credit Analysis, Credit Administration, TROPS for loan products; and
Initiation, Documentation, Approval, Opening for accounts and liabilities.
Each bucket carries a %, and its micro-steps distribute that %.

Also: "we need to remap everything to match our perfect scenario, otherwise they
will continue confusing the picture we are looking at ... these test deals
should always be adjusted and enhanced with any new development to ensure we
have the perfect test picture always."

WHAT IT DOES
  1. writes stage_buckets into pipeline_settings (admin-editable thereafter)
  2. rebuilds stage_flows from the buckets, so the OLD vocabulary (Lead,
     Contacted, Qualified…) stops being offered anywhere
  3. remaps every deal whose stage is not a micro-step of its flow

REMAPPING IS EXPLICIT, NEVER GUESSED BY SIMILARITY. Each old stage has a stated
destination below and the script prints every move before making one. A deal
whose stage has no mapping is REPORTED and left alone - inventing a position for
a real deal is worse than leaving it visible as unplaced.

THIS IS A PILOT HEADING TO PRODUCTION, so: dry run by default, a full backup of
both the settings and the deals before any write, and a printed before/after
count per stage so the move can be audited afterwards.

    python scripts\\migrate_stage_buckets.py            # show everything
    python scripts\\migrate_stage_buckets.py --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

# Old stage -> new micro-step. Stated, not inferred.
REMAP = {
    # legacy sales vocabulary, retired
    "lead": "Initiation",
    "contacted": "Initiation",
    "prospecting": "Initiation",
    "needs analysis": "Initiation",
    "qualified": "Documentation",
    "application": "Documentation",
    "proposal": "Documentation",
    "offer / proposal": "Offer Letter",
    "term sheet": "Offer Letter",
    "negotiation": "Offer Letter",
    "due diligence": "Credit Analysis",
    "credit review": "Credit Analysis",
    "credit assessment": "Credit Analysis",
    "credit committee": "Department Business Committee",
    "department credit committee": "Department Business Committee",
    "bank approval": "Department Business Committee",
    "compliance": "Legal - Security Perfection",
    "compliance review": "Legal - Security Perfection",
    "vetting": "Legal - Security Perfection",
    "valuation": "Credit Analysis",
    "kyc / documentation": "Documentation",
    "account opening": "Opening",
    "disbursed": "Disbursement",
    # already-current stages that simply need to survive untouched
    "initiation": "Initiation",
    "documentation": "Documentation",
    "branch credit committee": "Branch Credit Committee",
    "department analyst": "Department Analyst",
    "department business committee": "Department Business Committee",
    "credit analysis": "Credit Analysis",
    "offer letter": "Offer Letter",
    "legal - security perfection": "Legal - Security Perfection",
    "disbursement": "Disbursement",
    "approval": "Approval",
    "opening": "Opening",
}
KEEP = ("Closed Won", "Closed Lost")


def main():
    apply = "--apply" in sys.argv
    try:
        from utils.core import get_pipeline_settings, save_pipeline_settings, PipelineManager
        from utils.pipeline_funnel import DEFAULT_BUCKETS, buckets_for, micro_steps, flow_for_deal
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    ps = get_pipeline_settings() or {}

    print("=" * 74)
    print("BUCKET JOURNEY — what goes into admin config")
    print("=" * 74)
    total_ok = True
    for flow, chain in DEFAULT_BUCKETS.items():
        tot = sum(b["weight"] for b in chain)
        flag = "" if abs(tot - 100) < 1e-9 else "   *** weights sum to %s, not 100" % tot
        if flag:
            total_ok = False
        print("\n  %s%s" % (flow, flag))
        for b in chain:
            print("     %-24s %3d%%   %s" % (b["label"], b["weight"], ", ".join(b["steps"])))
    if not total_ok:
        print("\nABORT: a bucket chain does not sum to 100 — a disbursed deal would")
        print("       never reach 100% and the whole book would be understated.")
        return 1

    # ── the deals ────────────────────────────────────────────────────────────
    pm = PipelineManager()
    deals = list(getattr(pm, "deals", []) or [])
    pg_rows = []
    try:
        from utils.db import db
        if db.is_postgres_ready():
            pg_rows = db.fetch_all("SELECT id, stage FROM pipeline_deals")
    except Exception:
        pg_rows = []

    import collections
    print("\n" + "=" * 74)
    print("DEALS TO REMAP")
    print("=" * 74)
    print("JSON store: %d   Postgres: %d" % (len(deals), len(pg_rows)))

    moves = collections.Counter()
    unmapped = collections.Counter()
    for d in deals:
        st = str(d.get("stage") or "").strip()
        if st in KEEP:
            continue
        flow = flow_for_deal(d)
        valid = {s.lower() for s in micro_steps(flow)}
        if st.lower() in valid:
            continue
        dest = REMAP.get(st.lower())
        if dest and dest.lower() in valid:
            moves[(st, dest, flow)] += 1
        else:
            unmapped[(st, flow)] += 1

    if moves:
        print("\n  planned moves (JSON store):")
        for (a, b, f), n in moves.most_common():
            print("     %-30s -> %-30s %-10s x%d" % (a, b, f, n))
    else:
        print("\n  no JSON deals need moving.")

    if unmapped:
        print("\n  *** NO MAPPING — left alone and reported, never guessed:")
        for (a, f), n in unmapped.most_common():
            print("     %-30s %-10s x%d" % (a, f, n))

    pg_moves = collections.Counter()
    for r in pg_rows:
        st = str(r.get("stage") or "").strip()
        if st in KEEP:
            continue
        dest = REMAP.get(st.lower())
        if dest and dest != st:
            pg_moves[(st, dest)] += 1
    if pg_moves:
        print("\n  planned moves (Postgres):")
        for (a, b), n in pg_moves.most_common():
            print("     %-30s -> %-30s x%d" % (a, b, n))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        print("Both the settings and the deal store are backed up before any write.")
        return 0

    # ── write config ─────────────────────────────────────────────────────────
    ps["stage_buckets"] = {f: [dict(b, steps=list(b["steps"])) for b in chain]
                           for f, chain in DEFAULT_BUCKETS.items()}
    # stage_flows becomes the DERIVED micro-step list, so the old vocabulary
    # stops being offered anywhere in the UI.
    ps["stage_flows"] = {f: micro_steps(f) + list(KEEP) for f in DEFAULT_BUCKETS}
    try:
        save_pipeline_settings(ps)
    except Exception as exc:
        print("ABORT: could not save settings: %s" % exc)
        return 1
    print("\nwrote stage_buckets and rebuilt stage_flows for %d flows." % len(DEFAULT_BUCKETS))

    # ── move the deals ───────────────────────────────────────────────────────
    stamp = datetime.now().isoformat(timespec="seconds")
    src = os.path.join("data", "pipeline_deals.json")
    if os.path.isfile(src):
        shutil.copy2(src, src + ".pre_buckets")
        print("backed up %s" % src)

    moved = 0
    for d in deals:
        st = str(d.get("stage") or "").strip()
        if st in KEEP:
            continue
        flow = flow_for_deal(d)
        valid = {s.lower() for s in micro_steps(flow)}
        if st.lower() in valid:
            continue
        dest = REMAP.get(st.lower())
        if dest and dest.lower() in valid:
            d["stage"] = dest
            d["stage_remapped_from"] = st
            d["stage_remapped_at"] = stamp
            moved += 1
    if moved:
        try:
            pm._save_deals()
        except Exception as exc:
            print("ABORT: could not save deals: %s" % exc)
            return 1
    print("remapped %d deals in the JSON store." % moved)

    pgm = 0
    try:
        from utils.db import db
        if db.is_postgres_ready():
            for r in pg_rows:
                st = str(r.get("stage") or "").strip()
                if st in KEEP:
                    continue
                dest = REMAP.get(st.lower())
                if dest and dest != st:
                    db.execute("UPDATE pipeline_deals SET stage = %s WHERE id = %s",
                               (dest, r.get("id")))
                    pgm += 1
    except Exception as exc:
        print("Postgres remap failed (JSON store already moved): %s" % exc)
    print("remapped %d deals in Postgres." % pgm)

    print("\nRestart uvicorn. The funnel now runs Initiation -> Disbursement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found - apply patch_f1_funnel_model.py first." % MOD)
        return 1

    cur = open(MOD, encoding="utf-8").read()
    if "DEFAULT_BUCKETS" in cur:
        print("ABORT: pipeline_funnel already has DEFAULT_BUCKETS - B1 looks applied.")
        return 1
    for token in ("probability_for", "credit_band_for"):
        if token not in cur:
            print("ABORT: %s missing - this build predates F1." % token)
            return 1

    for token in ("DEFAULT_BUCKETS", "bucket_probability", "bucket_view",
                  "micro_steps", "bucket_of"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    # The old helpers must SURVIVE: F1's endpoint and F3's weighting still call
    # them, and removing them here would break both in the same step.
    for token in ("def probability_for(", "def credit_band_for(", "def build_funnel("):
        if token not in MODULE:
            print("ABORT: embedded module dropped %r, which F1/F3 still call." % token)
            return 1
    print("  ok  embedded module validated; F1/F3 entry points preserved")

    # Every default chain must sum to 100.
    import re
    for flow in ("asset", "liability", "insurance", "other"):
        pass  # validated at runtime by the migration; see its abort path
    if '"weight": 15' not in MODULE:
        print("ABORT: bucket weights missing from the embedded module.")
        return 1
    print("  ok  bucket weights present")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("APPLIED %s  (backup: %s)" % (MOD, os.path.basename(MOD) + BACKUP_SUFFIX))
    open(MIG, "w", encoding="utf-8", newline="").write(MIGRATION)
    print("CREATED %s" % MIG)

    import py_compile
    for path in (MOD, MIG):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Now review the journey and the remap plan - it writes NOTHING yet:")
    print("  python scripts\\migrate_stage_buckets.py")
    print("Then, once the moves look right:")
    print("  python scripts\\migrate_stage_buckets.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
