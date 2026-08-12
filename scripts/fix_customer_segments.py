#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why do Premier and Advantage sit under "Other"? DRY RUN by default.

FROM THE PILOT (2026-08-12): "I am unable to click on Consumer and see all" -
the Pipeline Deals filter shows Commercial and CIB correctly, but Premier,
Advantage, Direct, Large Corporate and Micro Enterprise land under "Other", and
40 deals under "Unclassified".

TWO CONFIG FAULTS, neither visible on the screen:

  A TRAILING SPACE. customer_segments has the key "Consumer " - with a space.
  It renders as a group nobody can match against and is impossible to spot in
  the admin table.

  THE NAMES DO NOT MATCH THE DEALS. The config lists "Premier Banking",
  "Advantage Banking", "Direct Banking"; the deals carry "Premier",
  "Advantage", "Direct". A sub-segment that does not match its config entry is
  bucketed under "Other" by design - the grouping code is behaving correctly on
  bad data.

WHAT THIS DOES. Trims the keys, and adds the SHORT names alongside the long
ones so both spellings resolve to the same business unit. It does not rename
anything on a deal: a deal carrying "Premier" keeps it, and the config learns
to recognise it.

WHAT IT WILL NOT DO. Any sub-segment it cannot place - "Large Corporate",
"Micro Enterprise" - is REPORTED, not guessed at. Which business unit those
belong to is the bank's answer, and putting a corporate under the wrong line
would quietly misstate a whole book.

"Unclassified" is a deal with NO segment at all. That is a capture problem, not
a mapping one, and it is counted here so the size of it is visible.

    python scripts\\fix_customer_segments.py
    python scripts\\fix_customer_segments.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

PS = os.path.join("data", "pipeline_settings.json")

# Short forms that mean the same unit as the long ones already configured.
ALIASES = {
    "Consumer": ["Premier", "Advantage", "Direct"],
    "Commercial": ["Local Corporates", "SME Banking"],
    "CIB": ["Corporate", "Multinational Corporates"],
}


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PS):
        print("ABORT: %s not found - run from the project root." % PS)
        return 1

    ps = json.load(open(PS, encoding="utf-8")) or {}
    segs = ps.get("customer_segments") or {}
    if not isinstance(segs, dict) or not segs:
        print("ABORT: customer_segments is not configured.")
        return 1

    print("=" * 74)
    print("CUSTOMER SEGMENT MAPPING")
    print("=" * 74)

    # 1. Keys with stray whitespace.
    dirty = [k for k in segs if k != k.strip()]
    if dirty:
        print("\n  KEYS WITH STRAY WHITESPACE (invisible in admin):")
        for k in dirty:
            print("     %r  ->  %r" % (k, k.strip()))

    # 2. What the deals actually carry.
    used = {}
    try:
        from utils.core import PipelineManager
        for d in (getattr(PipelineManager(), "deals", []) or []):
            s = str(d.get("segment") or "").strip()
            used[s or "(none)"] = used.get(s or "(none)", 0) + 1
    except Exception as exc:
        print("  (could not read deals: %s)" % str(exc)[:50])

    known = set()
    for k, v in segs.items():
        for sub in (v or []):
            known.add(str(sub).strip())

    unmapped = {s: n for s, n in used.items()
                if s not in known and s != "(none)"}
    aliasable, orphan = {}, {}
    for s, n in unmapped.items():
        unit = next((u for u, names in ALIASES.items() if s in names), "")
        (aliasable if unit else orphan)[s] = (n, unit)

    if used:
        print("\n  WHAT THE DEALS CARRY:")
        for s, n in sorted(used.items(), key=lambda x: -x[1])[:14]:
            mark = "OK" if s in known else ("-> %s" % aliasable[s][1]
                                            if s in aliasable else "UNPLACED")
            if s == "(none)":
                mark = "no segment set"
            print("     %-30s %4d  %s" % (s[:30], n, mark))

    if orphan:
        print("\n  *** CANNOT PLACE THESE - the bank's answer, not a guess:")
        for s, (n, _u) in sorted(orphan.items(), key=lambda x: -x[1][0]):
            print("     %-30s %4d deal(s)" % (s[:30], n))
        print("")
        print("     Add each to the right unit in customer_segments. Putting a")
        print("     corporate under the wrong line would misstate a whole book.")

    if used.get("(none)"):
        print("\n  %d deal(s) carry NO segment at all - they show as"
              % used["(none)"])
        print("  'Unclassified'. That is a capture problem, not a mapping one:")
        print("  the field is set at deal creation and these were saved without")
        print("  it. Worth finding out how, before the count grows.")

    changes = bool(dirty) or bool(aliasable)
    if not changes:
        print("\n  Nothing to change in the mapping.")
        return 0

    if aliasable:
        print("\n  WILL ADD these short forms alongside the long ones:")
        for s, (n, unit) in sorted(aliasable.items()):
            print("     %-24s -> %-12s (%d deal(s))" % (s[:24], unit, n))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(PS, PS + ".pre_segments")
    cleaned = {}
    for k, v in segs.items():
        key = k.strip()
        vals = [str(x).strip() for x in (v or [])]
        cleaned.setdefault(key, [])
        for x in vals:
            if x not in cleaned[key]:
                cleaned[key].append(x)
    for s, (_n, unit) in aliasable.items():
        if unit in cleaned and s not in cleaned[unit]:
            cleaned[unit].append(s)
    ps["customer_segments"] = cleaned
    tmp = PS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ps, fh, indent=2)
    os.replace(tmp, PS)

    print("\napplied (backup: %s)" % os.path.basename(PS + ".pre_segments"))
    print("Restart uvicorn and reload Pipeline Deals - Consumer should now")
    print("carry Premier, Advantage and Direct rather than 'Other'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
