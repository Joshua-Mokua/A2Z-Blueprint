#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
F1 - the funnel as the nerve centre: everything from admin, nothing hardcoded.

YOUR RULING (2026-08-09): "let me also be categorical that the stages should not
be hardcoded ... the only basic one we said we consider aligning with the win
probabilities is Documentation, Branch Credit, Department, Credit Analysis,
Credit Administration, TROPS - but that is a SIDE LAYER to say that when a deal
is within a certain probability bracket then it is likely to be within that
stage within the bank". Plus: win probability PER STAGE WITHIN EACH FLOW.

WHAT WAS WRONG - three vocabularies that disagreed:

    utils/core.ALL_ACTIVE_STAGES   13 stages, from a CODE constant
    pipeline_settings.stages       15 stages, what admin offers
    utils/api._STAGE_WEIGHTS        6 stages, HARDCODED at api.py:3590

A deal at "Credit Assessment" therefore carried a win probability of ZERO in
every weighted figure, silently, because the hardcoded map had never heard of
it. And the diagnostic showed six real deals - Department Credit Committee,
Legal - Security Perfection, Initiation, Credit Analysis, Offer Letter - being
asked to be sales stages when they describe where a deal sits inside the BANK'S
process. That is the side layer, not the journey.

TWO AXES
    THE JOURNEY     each flow's configured stages, in order, EVERY ONE
                    rendered including the empty ones. A funnel that hides its
                    empty steps is a bar chart of whatever happened to be busy,
                    and the gap is usually the finding.
    THE SIDE LAYER  Documentation / Branch Credit / Department / Credit
                    Analysis / Credit Administration / TROPS, inferred from the
                    probability bracket. Never filters the journey.

ADDS
  utils/pipeline_funnel.py - flows, per-flow probabilities, credit bands, and
      build_funnel. An UNCONFIGURED stage degrades to an even progression rather
      than returning zero: zero silently erases a real deal from every weighted
      figure, which is exactly what _STAGE_WEIGHTS was doing.

  GET /api/pipeline/funnel - the defined journey per flow plus the credit layer,
      scoped with _acquire_scoped_deals (the canonical read). NO try/except
      fallback: a fallback to "all deals" would show a caller deals outside
      their cascade, and a scope bypass that looks like a working page is worse
      than an error. Deals at a stage no flow contains are REPORTED as
      unplaced_deals rather than dropped - silently vanishing deals is the
      defect this replaces.

  scripts/seed_funnel_config.py - writes stage_probabilities and credit_bands
      into pipeline_settings so they are ADMIN-EDITABLE. Defaults exist only so
      a fresh install is coherent; once written they are never consulted again.
      A flow with no default gets an even progression, so a product added later
      is never silently worth zero.

MEASURED on the live config:
    asset  Negotiation p=0.80    liability Negotiation p=0.65   <- per flow
    p=0.45 -> Documentation   p=0.75 -> Department   p=0.98 -> TROPS

FRONTEND IS F2. This lands the model and the endpoint alone so they can be
verified without a second moving part.

Usage (from project root, .venv active):
    python scripts\patch_f1_funnel_model.py            # dry run
    python scripts\patch_f1_funnel_model.py --apply    # write + .pre_f1 backup
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "pipeline_funnel.py")
SEED = os.path.join("scripts", "seed_funnel_config.py")
API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_f1"

ANCHOR = """from utils.api_branch_log import router as branch_log_router
app.include_router(branch_log_router)"""

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
'''

SEEDER = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Write the funnel model into ADMIN CONFIG so nothing lives in code.

RULING (2026-08-09): "let me also be categorical that the stages should not be
hardcoded". Defaults exist in utils/pipeline_funnel so a fresh install is
coherent, but the bank must be able to change every number from the admin
screen. This writes them into data/pipeline_settings.json, after which the
defaults are never consulted again for those keys.

WHAT IT WRITES
    stage_probabilities   {flow: {stage: win probability}}
        PER STAGE WITHIN EACH FLOW (ruling): "Negotiation" on a liability
        product is not the same likelihood as "Negotiation" on a corporate
        facility, so one global map would misstate assured value on every
        product but one.

    credit_bands          the SIDE LAYER: Documentation, Branch Credit,
        Department, Credit Analysis, Credit Administration, TROPS - where a deal
        probably sits inside the bank, inferred from its probability bracket.
        Not a sales stage, and it never filters the journey.

    Any flow present in stage_flows but missing a probability table gets an even
    progression, so a product added later is never silently worth zero.

SAFE: dry-run by default; --apply writes through the existing settings saver,
which refuses to write a config missing its core keys and writes atomically.

    python scripts\\seed_funnel_config.py            # show what would change
    python scripts\\seed_funnel_config.py --apply
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv

    try:
        from utils.core import get_pipeline_settings, save_pipeline_settings
        from utils.pipeline_funnel import (
            DEFAULT_STAGE_PROBABILITIES, DEFAULT_CREDIT_BANDS, CLOSED,
        )
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    ps = get_pipeline_settings() or {}
    flows = ps.get("stage_flows") or {}
    if not flows:
        print("ABORT: no stage_flows configured — nothing to attach probabilities to.")
        return 1

    existing_p = ps.get("stage_probabilities") or {}
    existing_b = ps.get("credit_bands") or []

    plan = {k: dict(v) for k, v in DEFAULT_STAGE_PROBABILITIES.items() if k in flows}

    # A flow with no default gets an even progression rather than nothing: a
    # product added later must never be silently worth zero.
    for flow, seq in flows.items():
        if flow in plan:
            continue
        active = [s for s in (seq or []) if s not in CLOSED]
        table = {}
        for i, s in enumerate(active):
            table[s] = round((i + 1) / (len(active) + 1), 2)
        table["Closed Won"] = 1.0
        table["Closed Lost"] = 0.0
        plan[flow] = table
        print("  note: %r had no default; assigned an even progression" % flow)

    print("=" * 74)
    print("STAGE PROBABILITIES — per stage within each flow")
    print("=" * 74)
    for flow in sorted(plan):
        cur = existing_p.get(flow) or {}
        print("\n  %s" % flow)
        for s in (flows.get(flow) or []):
            new = plan[flow].get(s)
            if new is None:
                continue
            old = cur.get(s)
            mark = "" if old is None else ("  (unchanged)" if float(old) == float(new)
                                           else "  was %s" % old)
            print("     %-22s %.2f%s" % (s, new, mark))

    print("\n" + "=" * 74)
    print("CREDIT BANDS — the side layer, inferred from probability")
    print("=" * 74)
    for b in DEFAULT_CREDIT_BANDS:
        print("   %-22s %.0f%% – %.0f%%"
              % (b["label"], b["min"] * 100, min(b["max"], 1.0) * 100))
    if existing_b:
        print("\n   (%d bands already configured — they will be REPLACED)" % len(existing_b))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        print("Everything above becomes editable in admin once written.")
        return 0

    ps["stage_probabilities"] = plan
    ps["credit_bands"] = [dict(b) for b in DEFAULT_CREDIT_BANDS]
    try:
        save_pipeline_settings(ps)
    except Exception as exc:
        print("ABORT: could not save settings: %s" % exc)
        return 1

    check = get_pipeline_settings() or {}
    if not check.get("stage_probabilities") or not check.get("credit_bands"):
        print("ABORT: settings saved but read back without the new keys.")
        return 1
    print("\nwrote stage_probabilities for %d flows and %d credit bands."
          % (len(plan), len(DEFAULT_CREDIT_BANDS)))
    print("Restart uvicorn. These are now config, not code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

ENDPOINT = r'''@app.get("/api/pipeline/funnel")
def pipeline_funnel_defined(user: dict = Depends(get_current_user)):
    """The DEFINED journey per product flow — from admin config, not from code.

    Returns every configured stage of every flow in order, including the ones
    holding nothing: a funnel that hides its empty steps is a bar chart of
    whatever happened to be busy, and the gap is usually the finding.

    Each stage carries its win probability PER FLOW (ruling 2026-08-09) and the
    credit band that probability implies. The band is a SIDE LAYER describing
    where the deal probably sits inside the bank — it is not a sales stage and
    it never filters the journey.

    Scope is the caller's own: the same visible-deal rule the rest of the
    pipeline uses, so this can never show a deal the list would hide.
    """
    from utils.pipeline_funnel import (
        stage_flows, build_funnel, flow_for_deal, credit_bands, credit_band_for,
        probability_for,
    )

    # _acquire_scoped_deals is the canonical scope read used by the pipeline
    # list and analytics. NO try/except fallback here on purpose: a fallback to
    # "all deals" would silently show a caller deals outside their cascade, and
    # a scope bypass that looks like a working page is worse than an error.
    deals = _acquire_scoped_deals(user)

    grouped: dict = {}
    for d in deals:
        grouped.setdefault(flow_for_deal(d), []).append(d)

    flows_out = []
    for flow, seq in (stage_flows() or {}).items():
        mine = grouped.get(flow, [])
        stages = build_funnel(mine, flow)
        flows_out.append({
            "flow": flow,
            "stages": stages,
            "deals": len(mine),
            "value": round(sum(float(x.get("value") or 0) for x in stages), 2),
            "weighted": round(sum(float(x.get("weighted") or 0) for x in stages), 2),
        })
    flows_out.sort(key=lambda f: -f["deals"])

    # The side layer, over the same population.
    bands = credit_bands()
    tally = {b["label"]: {"label": b["label"], "count": 0, "value": 0.0,
                          "min": b["min"], "max": b["max"]} for b in bands}
    unplaced = 0
    for d in deals:
        st = str(d.get("stage") or "").strip()
        fl = flow_for_deal(d)
        if st not in (stage_flows().get(fl) or []):
            unplaced += 1          # a stage no configured flow contains
            continue
        p = probability_for(fl, st)
        lab = credit_band_for(p)["label"]
        try:
            v = float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            v = 0.0
        tally[lab]["count"] += 1
        tally[lab]["value"] = round(tally[lab]["value"] + v, 2)

    return {
        "flows": flows_out,
        "credit_layer": [tally[b["label"]] for b in bands],
        "total_deals": len(deals),
        # Deals sitting at a stage NO configured flow contains. Reported rather
        # than dropped: silently vanishing deals is the defect this replaces.
        "unplaced_deals": unplaced,
    }


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - F1 looks applied." % MOD)
        return 1

    api = open(API, encoding="utf-8").read()
    # Match the EXACT route: /api/pipeline/funnel/drill already exists, and a
    # substring guard here refused to run against a perfectly clean tree.
    if '@app.get("/api/pipeline/funnel")' in api:
        print("ABORT: the funnel endpoint is already registered.")
        return 1
    if api.count(ANCHOR) != 1:
        print("ABORT: router anchor matched %d times (expected 1)." % api.count(ANCHOR))
        return 1
    if "_acquire_scoped_deals" not in api:
        print("ABORT: _acquire_scoped_deals not found - this build predates the")
        print("       canonical scope read the endpoint depends on.")
        return 1

    for token in ("DEFAULT_STAGE_PROBABILITIES", "DEFAULT_CREDIT_BANDS",
                  "credit_band_for", "build_funnel", "probability_for"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    # Check for USE, not mention: the module's docstring explains why the
    # hardcoded map was wrong, and matching the bare name trips on that.
    if "_STAGE_WEIGHTS.get" in MODULE or "_STAGE_WEIGHTS[" in MODULE:
        print("ABORT: embedded module still reads the hardcoded weight map.")
        return 1
    if "_scope_deals_for_user" in ENDPOINT:
        print("ABORT: endpoint still calls a helper that does not exist.")
        return 1
    if "_acquire_scoped_deals(user)" not in ENDPOINT:
        print("ABORT: endpoint is not using the canonical scope read.")
        return 1
    print("  ok  embedded module and endpoint validated")

    api = api.replace(ANCHOR, ENDPOINT + ANCHOR, 1)
    if api.count('@app.get("/api/pipeline/funnel")') != 1:
        print("ABORT: post-check - funnel route registered %d times."
              % api.count('@app.get("/api/pipeline/funnel")'))
        return 1
    if api.count("include_router(branch_log_router)") != 1:
        print("ABORT: post-check - the branch-log router registration changed.")
        return 1
    print("  ok  api.py - one funnel route, branch-log untouched")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    open(SEED, "w", encoding="utf-8", newline="").write(SEEDER)
    print("CREATED %s" % SEED)
    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s  (backup: %s)" % (API, os.path.basename(API) + BACKUP_SUFFIX))

    import py_compile
    for path in (MOD, SEED, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Now move the model into ADMIN so nothing stays in code:")
    print("  python scripts\\seed_funnel_config.py")
    print("  python scripts\\seed_funnel_config.py --apply")
    print("Then restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
