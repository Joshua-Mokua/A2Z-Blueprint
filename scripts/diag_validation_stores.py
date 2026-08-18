#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why did validating one deal appear to validate all? — READ ONLY.

Written as a script, not a one-liner: `metadata->>'x'` contains `>`, which cmd
treats as a REDIRECT operator and silently mangles the SQL.

THE HYPOTHESIS THIS TESTS

    PipelineManager.get_pending_validations() iterates self.deals - the JSON
    store. The deal LIST and DETAIL routes are Postgres-first. If the two
    stores hold different populations, the manager's validation queue is drawn
    from one store while everything else he sees comes from the other.

Run from the project root with .venv active:
    python scripts\\diag_validation_stores.py
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())


def rule(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def main():
    # ── A. JSON store ────────────────────────────────────────────────────────
    rule("A. JSON STORE  (data/pipeline_deals.json) - what the QUEUE reads")
    jpath = os.path.join("data", "pipeline_deals.json")
    jdeals = []
    try:
        jdeals = json.loads(open(jpath, encoding="utf-8").read())
        print("deals in JSON            : %d" % len(jdeals))
        jval = [d for d in jdeals if d.get("manager_validated")]
        print("marked manager_validated : %d" % len(jval))
        pend = [d for d in jdeals if not d.get("manager_validated")]
        print("still pending in JSON    : %d" % len(pend))
        print("\nids: %s" % ", ".join(str(d.get("id")) for d in jdeals[:20]))
    except Exception as exc:
        print("could not read %s: %s" % (jpath, exc))

    # ── B. Postgres ──────────────────────────────────────────────────────────
    rule("B. POSTGRES  (pipeline_deals) - what the LIST and DETAIL read")
    pdeals = []
    try:
        from utils.db import db
        if not db.is_postgres_ready():
            print("Postgres not reachable.")
        else:
            n = db.fetch_scalar("SELECT count(*) FROM pipeline_deals")
            print("deals in Postgres        : %s" % n)
            pdeals = db.fetch_all(
                "SELECT id, staff_code, stage, "
                "metadata->>'manager_validated' AS mv, "
                "metadata->>'validated_by'      AS vby, "
                "metadata->>'validated_at'      AS vat "
                "FROM pipeline_deals")
            mv = [r for r in pdeals if str(r.get("mv")).lower() in ("true", "1")]
            print("marked manager_validated : %d" % len(mv))
            stamped = [r for r in pdeals if r.get("vat")]
            print("carrying a validated_at  : %d" % len(stamped))
            if stamped:
                stamped.sort(key=lambda r: str(r.get("vat")), reverse=True)
                print("\nmost recent validations recorded in Postgres:")
                for r in stamped[:10]:
                    print("   %-8s %-9s by=%-12s at=%s"
                          % (r.get("id"), r.get("staff_code"),
                             str(r.get("vby"))[:12], r.get("vat")))
            else:
                print("\n*** NO deal in Postgres carries a validated_at stamp.")
    except Exception as exc:
        print("Postgres probe failed: %s" % exc)

    # ── C. the gap ───────────────────────────────────────────────────────────
    rule("C. THE GAP")
    jids = {str(d.get("id")) for d in jdeals}
    pids = {str(r.get("id")) for r in pdeals}
    if jids and pids:
        print("in JSON only : %d  %s" % (len(jids - pids), sorted(jids - pids)[:10]))
        print("in PG only   : %d  %s" % (len(pids - jids), sorted(pids - jids)[:10]))
        print("in both      : %d" % len(jids & pids))
        print("")
        jv = {str(d.get("id")) for d in jdeals if d.get("manager_validated")}
        pv = {str(r.get("id")) for r in pdeals
              if str(r.get("mv")).lower() in ("true", "1")}
        drift = sorted(jv - pv)
        print("VALIDATED IN JSON BUT NOT IN POSTGRES: %d" % len(drift))
        for i in drift[:15]:
            print("   %s" % i)
        if drift:
            print("\n   ^ these validations were written to the JSON store and never")
            print("     reached Postgres. The DB-first read still calls them pending,")
            print("     which is why they reappear on the next login.")

    rule("D. WHAT THIS MEANS")
    print("get_pending_validations() iterates the JSON store only, so a manager's")
    print("queue can never contain more deals than the JSON file holds - however")
    print("many the bank actually has in Postgres. Clearing that short queue")
    print("empties the tab, which reads as 'it validated everything'.")
    print("")
    print("Send this whole output.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
