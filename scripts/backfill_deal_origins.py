#!/usr/bin/env python
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
