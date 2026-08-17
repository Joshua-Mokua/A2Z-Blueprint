#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
OR1 - Deal Origin. The first layer of the vision, made config not code.

VISION (2026-08-11): "The first layer of this is the Deal Origin. I have
identified seven origins - Self/Direct, the Referral engine, the Warehouse,
Events, Partnerships, Lead Generators, Contact Centre. These seven are my base
but in future I should be able to add more."

WHY THIS MATTERS NOW. The pipeline leaderboard and analytics were built around a
hard-coded PAIR - referred versus direct. That works for two origins and breaks
at seven. Adding an eighth must be an admin edit, not a release, exactly as
stages became buckets.

CREDITABLE vs NOT (ruling 2026-08-11). Some origins bring a second party whose
index should move; some are only a tag:

    self            no second party
    referral        the referrer          credited   (built)
    warehouse       the lister            credited   (built)
    lead_gen        the generator         credited
    contact_centre  the agent             credited   - a referral in all but name
    events          a tag, nobody to credit
    partnership     the partner is an ORGANISATION, so no index moves

party_of() returns someone ONLY when the origin says there is someone to credit.
Otherwise a stale referrer field left on a self-created deal would quietly move
an index it should not.

ONE ORIGIN PER DEAL (ruling: "a single origin, but branch as it progresses").
Origin records how the deal ENTERED. What happens afterwards - a re-referral, a
hand-off - belongs in referral_chain, which already preserves every hop. Several
origins on one deal would make "how many came from the warehouse" unanswerable
without inventing an attribution split, which is the double-counting the ranking
rules already avoid.

summarise() reports EVERY configured origin, including empty ones: an origin
producing no deals is a finding, and hiding it is how a channel dies quietly.

ALSO SHIPS scripts/backfill_deal_origins.py (ruling: "we should backfill for
proper analysis"). It classifies from what each record already says - a
warehouse id, a referral chain - and everything else becomes Self/Direct. That
last part is a stated judgement: some of those really came from an event or the
contact centre and nothing in the record says so. They can be corrected once
origin is editable; inventing a distribution would put invented numbers into the
analytics. Dry-run by default, backs up the deal store, prints the distribution
first.

MEASURED: 7 origins configured; a legacy referral deal infers "referral" and
resolves its party from the chain; an events deal correctly yields no party.

NEXT (OR2): the pipeline leaderboard and analytics read origins from config
instead of the referred/direct pair, and deal creation records the origin.

Usage (from project root, .venv active):
    python scripts\patch_or1_deal_origin.py            # dry run
    python scripts\patch_or1_deal_origin.py --apply

Then, once you have reviewed the distribution:
    python scripts\backfill_deal_origins.py
    python scripts\backfill_deal_origins.py --apply
"""
import os
import sys

MOD = os.path.join("utils", "deal_origin.py")
BF = os.path.join("scripts", "backfill_deal_origins.py")

MODULE = r'''"""
utils/deal_origin — where a deal came from, and who deserves credit for it.

VISION (2026-08-11): "The first layer of this is the Deal Origin. I have
identified seven origins - Self/Direct, the Referral engine, the Warehouse,
Events, Partnerships, Lead Generators, Contact Centre. These seven are my base
but in future I should be able to add more."

SO IT IS CONFIG, NOT AN ENUM. The pipeline leaderboard and analytics were built
around a hard-coded PAIR - referred versus direct - which works for two and
breaks at seven. Adding an eighth origin must be an admin edit, not a release,
the same way stages became buckets.

CREDITABLE vs NOT (ruling 2026-08-11). Some origins bring a second party who
deserves credit; some are simply a tag describing how the deal arrived:

    self          no second party
    referral      the referrer          credited
    warehouse     the lister            credited
    lead_gen      the generator         credited
    contact_centre the agent            credited
    events        a tag - nobody to credit beyond the owner
    partnership   the partner ORGANISATION, not a person

The distinction matters because credit is what moves someone's index. An origin
marked creditable with no party recorded is a data problem worth surfacing, not
something to silently score as zero.

ONE ORIGIN PER DEAL (ruling 2026-08-11: "I would prefer a single origin but
branch as it progresses"). The origin records how the deal ENTERED. What happens
afterwards - a re-referral to another department, a hand-off - belongs in the
referral_chain, which already exists and already preserves every hop. Letting a
deal carry several origins would make "how many deals came from the warehouse"
unanswerable without deciding what fraction to attribute, which is exactly the
double-counting the ranking rules avoid.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Seeded defaults. Config wins - see origins(). `credits_party` decides whether
# a second person's index moves; `party_label` is what the UI should ask for.
DEFAULT_ORIGINS = [
    {"key": "self", "label": "Self / Direct", "credits_party": False,
     "party_label": "", "active": True,
     "note": "Created directly by the officer who will pursue it."},
    {"key": "referral", "label": "Referral", "credits_party": True,
     "party_label": "Referrer", "active": True,
     "note": "Sent to a named person; credited on acceptance."},
    {"key": "warehouse", "label": "Deals Warehouse", "credits_party": True,
     "party_label": "Listed by", "active": True,
     "note": "Claimed from the shared shelf; the claim IS the acceptance."},
    {"key": "events", "label": "Events", "credits_party": False,
     "party_label": "", "active": True,
     "note": "Gathered at an activation, forum or roadshow."},
    {"key": "partnership", "label": "Partnerships", "credits_party": False,
     "party_label": "Partner", "active": True,
     "note": "Introduced under a partnership or MOU. The party is an "
             "organisation, not a person, so nobody's index moves."},
    {"key": "lead_gen", "label": "Lead Generators", "credits_party": True,
     "party_label": "Generator", "active": True,
     "note": "Sourced by a lead generator who is credited."},
    {"key": "contact_centre", "label": "Contact Centre", "credits_party": True,
     "party_label": "Agent", "active": True,
     "note": "Raised by an agent and handed to an officer - a referral in "
             "everything but name."},
]

DEFAULT_ORIGIN = "self"


def origins(include_inactive: bool = False) -> list:
    """The configured origins. Config first, defaults second."""
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("deal_origins")
        if isinstance(v, list) and v:
            out = []
            for o in v:
                if not isinstance(o, dict) or not str(o.get("key") or "").strip():
                    continue
                out.append({
                    "key": str(o["key"]).strip(),
                    "label": str(o.get("label") or o["key"]),
                    "credits_party": bool(o.get("credits_party")),
                    "party_label": str(o.get("party_label") or ""),
                    "active": bool(o.get("active", True)),
                    "note": str(o.get("note") or ""),
                })
            if out:
                return [o for o in out if include_inactive or o["active"]]
    except Exception as exc:
        logger.debug("deal origins: falling back to defaults (%s)", exc)
    return [dict(o) for o in DEFAULT_ORIGINS
            if include_inactive or o.get("active", True)]


def origin_map() -> dict:
    return {o["key"]: o for o in origins(include_inactive=True)}


def label_for(key: str) -> str:
    """Never blank: an unrecognised origin shows its own key rather than an
    empty cell, so a bad value is visible instead of looking like no data."""
    k = str(key or "").strip()
    if not k:
        return "Unclassified"
    return (origin_map().get(k) or {}).get("label") or k


def credits_party(key: str) -> bool:
    return bool((origin_map().get(str(key or "").strip()) or {}).get("credits_party"))


def is_known(key: str) -> bool:
    return str(key or "").strip() in origin_map()


def origin_of(deal: dict) -> str:
    """The deal's origin, inferred where it has not been set.

    Inference exists for deals created before the origin field did. It is
    deliberately conservative - it reads what the deal already records rather
    than guessing - and anything it cannot place returns DEFAULT_ORIGIN so the
    figure is never blank in a ranking.
    """
    raw = str(deal.get("origin") or "").strip()
    if raw:
        return raw
    if deal.get("warehouse_prospect_id"):
        return "warehouse"
    if deal.get("is_referral") or (deal.get("referral_chain") or []):
        return "referral"
    return DEFAULT_ORIGIN


def party_of(deal: dict) -> tuple:
    """(code, name) of the party credited for this deal, or ("", "").

    Only returns someone when the ORIGIN says there is someone to credit -
    otherwise a deal carrying a stale referrer field would quietly move an index
    it should not.
    """
    o = origin_of(deal)
    if not credits_party(o):
        return "", ""
    code = str(deal.get("origin_party_code") or "").strip()
    name = str(deal.get("origin_party_name") or "").strip()
    if code or name:
        return code, name
    # Fall back to the referral chain for deals that predate the field.
    chain = deal.get("referral_chain") or []
    if chain and isinstance(chain[-1], dict):
        hop = chain[-1]
        return (str(hop.get("referred_by_code") or "").strip(),
                str(hop.get("referred_by") or hop.get("referred_by_name") or "").strip())
    return (str(deal.get("referred_by_code") or "").strip(),
            str(deal.get("referred_by") or "").strip())


def summarise(deals: list) -> list:
    """Count, value and won per origin - for the analytics split.

    Every CONFIGURED origin appears, including those with nothing in them: an
    origin producing no deals is a finding, and hiding it is how a channel
    quietly dies without anyone noticing.
    """
    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    buckets = {o["key"]: {"origin": o["key"], "label": o["label"],
                          "credits_party": o["credits_party"],
                          "count": 0, "value": 0.0, "won": 0}
               for o in origins()}
    unknown = {}
    for d in deals or []:
        k = origin_of(d)
        b = buckets.get(k)
        if b is None:
            b = unknown.setdefault(k, {"origin": k, "label": label_for(k),
                                       "credits_party": False,
                                       "count": 0, "value": 0.0, "won": 0})
        b["count"] += 1
        b["value"] += _val(d)
        if str(d.get("stage") or "") == "Closed Won":
            b["won"] += 1
    out = list(buckets.values()) + list(unknown.values())
    for b in out:
        b["value"] = round(b["value"], 2)
    return out
'''

BACKFILL = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Backfill the origin on existing deals. DRY RUN by default.

RULING (2026-08-11): "we should backfill for proper analysis and development."

Deals created before the origin field existed have none. origin_of() infers one
at read time, so nothing is broken - but an inferred value cannot be reported on
reliably, cannot be corrected by a user, and disappears the moment the inference
rules change. Writing it down makes it data rather than a guess that happens to
be recomputed the same way each time.

HOW EACH DEAL IS CLASSIFIED - from what the record already says, never guessed:

    warehouse_prospect_id present        -> warehouse
    is_referral / referral_chain present -> referral, party from the last hop
    anything else                        -> self

That last line is a JUDGEMENT and worth stating plainly: a deal with no evidence
of another channel is treated as Self/Direct. Some of those will really have
come from an event or the contact centre, and nothing in the record says so.
They can be corrected in the UI once origin is editable; inventing a
distribution here would put invented numbers into the analytics.

The party is written ONLY for creditable origins. A stale referrer field on a
self-created deal would otherwise start moving somebody's index.

Backs up the deal store first, and prints the distribution before writing.

    python scripts\\backfill_deal_origins.py
    python scripts\\backfill_deal_origins.py --apply
"""
import collections
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv
    try:
        from utils.core import PipelineManager
        from utils.deal_origin import origin_of, credits_party, label_for, origins
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    pm = PipelineManager()
    deals = list(getattr(pm, "deals", []) or [])
    print("deal store: %d" % len(deals))

    pg = []
    try:
        from utils.db import db
        if db.is_postgres_ready():
            pg = db.fetch_all(
                "SELECT id, metadata->>'origin' AS origin, "
                "metadata->>'is_referral' AS is_ref FROM pipeline_deals") or []
            print("postgres  : %d" % len(pg))
    except Exception as exc:
        print("(postgres probe skipped: %s)" % str(exc)[:40])

    if not deals and not pg:
        print("\nNothing to backfill.")
        return 0

    plan = collections.Counter()
    already = 0
    changes = []
    for d in deals:
        if str(d.get("origin") or "").strip():
            already += 1
            continue
        o = origin_of(d)          # infers from what the record already holds
        plan[o] += 1
        changes.append((d, o))

    print("\n" + "=" * 70)
    print("PLANNED DISTRIBUTION")
    print("=" * 70)
    print("  %-24s %s" % ("already set", already))
    for k, n in plan.most_common():
        print("  %-24s %d" % (label_for(k), n))

    creditable = sum(n for k, n in plan.items() if credits_party(k))
    print("\n  %d of %d will carry a credited party" % (creditable, sum(plan.values())))
    print("\nConfigured origins (%d): %s"
          % (len(origins()), ", ".join(o["label"] for o in origins())))
    print("\nAnything not evidenced as another channel becomes Self / Direct.")
    print("Some of those will really be events or contact centre, and nothing")
    print("in the record says so - they can be corrected once origin is")
    print("editable. Inventing a split here would put invented numbers into")
    print("the analytics.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    src = os.path.join("data", "pipeline_deals.json")
    if os.path.isfile(src):
        backup = src + ".pre_origin"
        shutil.copy2(src, backup)
        print("\nbacked up %s" % backup)

    stamp = datetime.now().isoformat(timespec="seconds")
    written = 0
    for d, o in changes:
        d["origin"] = o
        d["origin_backfilled_at"] = stamp
        if credits_party(o):
            # Only for creditable origins - a stale referrer on a self-created
            # deal would otherwise start moving somebody's index.
            from utils.deal_origin import party_of
            code, name = party_of(d)
            if code:
                d["origin_party_code"] = code
            if name:
                d["origin_party_name"] = name
        written += 1

    if written:
        try:
            pm._save_deals()
        except Exception as exc:
            print("ABORT: could not save deals: %s" % exc)
            return 1
    print("wrote origin on %d deals in the JSON store." % written)

    pgw = 0
    try:
        from utils.db import db
        if db.is_postgres_ready():
            for r in pg:
                if str(r.get("origin") or "").strip():
                    continue
                o = "referral" if str(r.get("is_ref")).lower() in ("true", "1", "t") \
                    else "self"
                db.execute(
                    "UPDATE pipeline_deals SET metadata = "
                    "jsonb_set(COALESCE(metadata,'{}'::jsonb), '{origin}', %s::jsonb) "
                    "WHERE id = %s", ('"%s"' % o, r.get("id")))
                pgw += 1
    except Exception as exc:
        print("postgres backfill failed (JSON store already written): %s"
              % str(exc)[:70])
    print("wrote origin on %d deals in Postgres." % pgw)

    print("\nRestart uvicorn. Origin is now data, not an inference.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isdir("utils"):
        print("ABORT: run from the project root.")
        return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - OR1 looks applied." % MOD)
        return 1

    for token in ("DEFAULT_ORIGINS", "credits_party", "def party_of(",
                  "def summarise(", "contact_centre", "lead_gen"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    keys = [k for k in ("self", "referral", "warehouse", "events",
                        "partnership", "lead_gen", "contact_centre")
            if '"key": "%s"' % k in MODULE]
    if len(keys) != 7:
        print("ABORT: expected all 7 origins, found %d: %s" % (len(keys), keys))
        return 1
    print("  ok  all 7 origins present")

    # A party must only be returned for creditable origins, or a stale referrer
    # field would move an index it should not.
    if "if not credits_party(o):" not in MODULE:
        print("ABORT: party_of does not gate on credits_party.")
        return 1
    if "def backfill" in MODULE:
        print("ABORT: the model should not contain the backfill.")
        return 1
    for token in ("--apply", "pre_origin", "credits_party"):
        if token not in BACKFILL:
            print("ABORT: embedded backfill missing %r." % token)
            return 1
    print("  ok  party credit is gated; backfill is separate and dry-run first")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    open(BF, "w", encoding="utf-8", newline="").write(BACKFILL)
    print("CREATED %s" % BF)

    import py_compile
    for path in (MOD, BF):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Nothing reads this yet - OR2 wires the leaderboard and analytics.")
    print("Review the backfill distribution before writing anything:")
    print("  python scripts\\backfill_deal_origins.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
