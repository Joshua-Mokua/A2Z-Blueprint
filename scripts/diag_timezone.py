#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Timezone ground-truth diagnostic — READ ONLY, writes nothing.

Answers, with evidence rather than theory:
  A. What clock is the API process on?
  B. What clock is Postgres on?
  C. Are stored timestamps naive (no offset) or aware (with offset)?
  D. Do the two stores disagree — i.e. is the same wall-clock event recorded
     differently depending on which write path created it?
  E. What hour-of-day do deals actually land on, and how many land 00:00-05:00?

Run from the project root with .venv active:
    python scripts\\diag_timezone.py
"""
import collections
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EAT_OFFSET_HOURS = 3  # Africa/Nairobi, UTC+3, no DST


def rule(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def classify(ts):
    """Return 'aware(+HH:MM)' / 'naive' / 'not-a-timestamp' for a raw value."""
    if ts is None:
        return "null"
    if isinstance(ts, datetime):
        return "aware(%s)" % ts.strftime("%z") if ts.tzinfo else "naive(datetime)"
    s = str(ts)
    if len(s) < 10:
        return "not-a-timestamp"
    tail = s[10:]
    if tail.endswith("Z"):
        return "aware(Z)"
    for i in range(len(tail) - 1, max(len(tail) - 7, -1), -1):
        if tail[i] in "+-" and ":" in tail[i:]:
            return "aware(%s)" % tail[i:]
    return "naive"


# ── A. process clock ─────────────────────────────────────────────────────────
rule("A. PROCESS CLOCK (whatever machine runs uvicorn)")
now_local = datetime.now()
now_aware = datetime.now().astimezone()
print("TZ env var        : %s" % os.environ.get("TZ", "(unset — OS default)"))
print("time.tzname       : %s" % (time.tzname,))
print("datetime.now()    : %s   <- what datetime.now().isoformat() writes" % now_local.isoformat())
print("local UTC offset  : %s" % now_aware.strftime("%z"))
print("datetime.utcnow() : %s   <- what the 636 utcnow() call sites write"
      % datetime.now(timezone.utc).replace(tzinfo=None).isoformat())
offset_h = now_aware.utcoffset().total_seconds() / 3600 if now_aware.utcoffset() else 0
if abs(offset_h - EAT_OFFSET_HOURS) < 0.01:
    print("VERDICT           : process is on EAT (UTC+3). Naive now() strings are EAT wall-clock.")
else:
    print("VERDICT           : *** process is on UTC%+g, NOT EAT. Every naive datetime.now()"
          % offset_h)
    print("                    string written by this process is off by %+g hours. ***"
          % (EAT_OFFSET_HOURS - offset_h))

# ── B. Postgres clock ────────────────────────────────────────────────────────
rule("B. POSTGRES CLOCK")
db = None
try:
    from utils.db import db as _db
    db = _db
    if not db.is_postgres_ready():
        print("Postgres not reachable — skipping sections B, C, D.")
        db = None
except Exception as e:
    print("Could not import utils.db (%s) — skipping sections B, C, D." % e)
    db = None

if db:
    try:
        tzname = db.fetch_scalar("SHOW timezone")
        pg_now = db.fetch_scalar("SELECT now()")
        pg_naive = db.fetch_scalar("SELECT now()::timestamp")
        print("SHOW timezone         : %s" % tzname)
        print("SELECT now()          : %s  [%s]" % (pg_now, classify(pg_now)))
        print("SELECT now()::timestamp: %s" % pg_naive)
        print("Server wall clock in Nairobi: %s"
              % db.fetch_scalar("SELECT now() AT TIME ZONE 'Africa/Nairobi'"))
        if str(tzname).upper() in ("UTC", "ETC/UTC", "GMT"):
            print("\n*** Postgres session TZ is UTC. Any NAIVE timestamp string this app writes")
            print("    into a TIMESTAMPTZ column is interpreted by Postgres as UTC. A deal keyed")
            print("    at 21:40 EAT is then stored as 21:40 UTC and reads back as 00:40 EAT the")
            print("    NEXT DAY. This is the classic 'created past midnight' mechanism. ***")
        elif "Nairobi" in str(tzname) or str(tzname) in ("EAT", "Africa/Nairobi"):
            print("\nPostgres session TZ is Nairobi — naive writes land on EAT as intended.")
    except Exception as e:
        print("Postgres clock query failed: %s" % e)

# ── C. what is actually stored ───────────────────────────────────────────────
rule("C. STORED TIMESTAMPS — naive or aware?")
if db:
    probes = [
        ("audit_trail.ts (TIMESTAMPTZ)",
         "SELECT ts AS v, action AS label FROM audit_trail ORDER BY ts DESC LIMIT 8"),
        ("pipeline_deals.metadata->>'created_at' (JSON string)",
         "SELECT metadata->>'created_at' AS v, id AS label FROM pipeline_deals "
         "WHERE metadata ? 'created_at' ORDER BY id DESC LIMIT 8"),
        ("pipeline_deals.last_updated (DATE)",
         "SELECT last_updated::text AS v, id AS label FROM pipeline_deals "
         "ORDER BY id DESC LIMIT 5"),
    ]
    for name, sql in probes:
        print("\n-- %s" % name)
        try:
            rows = db.fetch_all(sql)
            if not rows:
                print("   (no rows)")
                continue
            for r in rows:
                print("   %-28s %-34s %s" % (str(r.get("label"))[:28], str(r.get("v")),
                                             classify(r.get("v"))))
        except Exception as e:
            print("   query failed: %s" % e)

# ── D. hour-of-day distribution ──────────────────────────────────────────────
rule("D. HOUR-OF-DAY DISTRIBUTION — where do events actually land?")


def histogram(label, hours):
    if not hours:
        print("\n-- %s: no data" % label)
        return
    print("\n-- %s (n=%d)" % (label, sum(hours.values())))
    graveyard = sum(v for k, v in hours.items() if k in ("00", "01", "02", "03", "04"))
    for h in ("%02d" % i for i in range(24)):
        n = hours.get(h, 0)
        if n:
            print("   %s  %-4d %s" % (h, n, "#" * min(n, 50)))
    pct = 100.0 * graveyard / max(sum(hours.values()), 1)
    print("   00:00-04:59 share: %d (%.1f%%)%s"
          % (graveyard, pct, "   <-- SUSPICIOUS" if pct > 5 else ""))


if db:
    try:
        rows = db.fetch_all(
            "SELECT to_char(ts, 'HH24') AS h, count(*) AS n FROM audit_trail "
            "WHERE ts > now() - interval '30 days' GROUP BY 1 ORDER BY 1")
        histogram("audit_trail.ts, last 30d (as Postgres renders it)",
                  {r["h"]: int(r["n"]) for r in rows})
    except Exception as e:
        print("audit_trail histogram failed: %s" % e)
    try:
        rows = db.fetch_all(
            "SELECT substring(metadata->>'created_at' from 12 for 2) AS h, count(*) AS n "
            "FROM pipeline_deals WHERE metadata ? 'created_at' GROUP BY 1 ORDER BY 1")
        histogram("pipeline_deals created_at (naive string, as stored)",
                  {r["h"]: int(r["n"]) for r in rows if r["h"]})
    except Exception as e:
        print("pipeline_deals histogram failed: %s" % e)

# JSON stores need no DB.
for rel in ("data/branch_logs.json", "data/referrals.json"):
    p = ROOT / rel
    if not p.exists():
        continue
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        recs = raw if isinstance(raw, list) else next(
            (v for v in raw.values() if isinstance(v, list)), [])
        hours, kinds = collections.Counter(), collections.Counter()
        for r in recs:
            if not isinstance(r, dict):
                continue
            for k in ("created_at", "submitted_at", "referred_at", "updated_at"):
                v = r.get(k)
                if isinstance(v, str) and "T" in v and len(v) >= 13:
                    hours[v[11:13]] += 1
                    kinds[classify(v)] += 1
                    break
        histogram("%s" % rel, hours)
        print("   offset forms present: %s" % dict(kinds))
    except Exception as e:
        print("%s: %s" % (rel, e))

# ── E. summary ───────────────────────────────────────────────────────────────
rule("E. WHAT TO SEND BACK")
print("Paste this whole output. The three lines that decide the fix are:")
print("  1. A > 'local UTC offset'      (is the API process on EAT?)")
print("  2. B > 'SHOW timezone'         (is Postgres on EAT or UTC?)")
print("  3. C > the naive/aware column  (do the two stores agree?)")
print("\nAlso useful: one deal ID whose displayed time looked wrong, and the")
print("time you actually keyed it. One concrete pair pins the offset exactly.")
