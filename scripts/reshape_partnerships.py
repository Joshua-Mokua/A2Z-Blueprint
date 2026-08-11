#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Reshape partnerships so they can be owned, scoped and tested. DRY RUN by default.

RULING (2026-08-11): "we can reuse but we will need to reshape if we are to test
well from our PC."

WHY THEY CANNOT BE USED AS THEY STAND. data/partnerships.json holds 50 records
with an rm_code like "300008". Real staff codes are "KE343"-style, and ZERO of
the 46 distinct codes match the roster. So ownership cannot be derived - an
unowned partnership is invisible to every unit view, which makes the whole
channel untestable.

Partnerships also carry expected_volume_kes_m but no budget and no lead or
account targets, so a Partnerships analytics tab has nothing to measure
progress against.

WHAT THIS DOES, and what it deliberately does not:

    ASSIGNS an owner - a real MD-reporting unit, chosen by the partner's
    SECTOR where that maps sensibly (Tech -> the technology unit, Insurance ->
    consumer, and so on) and spread across the rest otherwise. Ownership is
    written as owner_type + owner, never as a single free-text field, because
    "Nakuru" could be a branch or a region and a report cannot ask later.

    ASSIGNS a real rm_code from the roster, so the record points at somebody
    who exists.

    DERIVES targets from expected_volume_kes_m, which the record already
    carries: target_value_kes is that figure, and target_accounts is a
    proportion of it. It does NOT invent a budget. Partnerships are measured on
    volume against expectation, not on return on spend - inventing a spend
    figure would produce an ROI percentage the bank never agreed to.

Everything is written back into the same file, so the existing Streamlit pages
keep working. Backs up first.

    python scripts\\reshape_partnerships.py
    python scripts\\reshape_partnerships.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

# Sector -> the unit that would plausibly own it. Anything unmapped is spread
# across the commercial units rather than dumped on one.
# Keys are the sector values ACTUALLY in the file - checked, not assumed. The
# first draft mapped "Government", "Manufacturing" and "Agriculture", none of
# which appear; the real values are Govt, Manufacturer, SACCO, NGO, Telco. Five
# of nine sectors fell through to a round-robin as a result.
SECTOR_UNIT = {
    "Tech": "Director Operations & Technology",
    "Telco": "Director Operations & Technology",
    "Insurance": "Head of Consumer",
    "Retail": "Head of Consumer",
    "SACCO": "Head of Consumer",
    "Health": "Director Consumer & Commercial Banking (CCB)",
    "NGO": "Director Consumer & Commercial Banking (CCB)",
    "Manufacturer": "Director, Corporate Banking Kenya & EAC",
    "Govt": "Director, Corporate Banking Kenya & EAC",
}
FALLBACK_UNITS = [
    "Director, Corporate Banking Kenya & EAC",
    "Director Consumer & Commercial Banking (CCB)",
    "Head of Consumer",
]


def main():
    apply = "--apply" in sys.argv
    path = os.path.join("data", "partnerships.json")
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    try:
        from utils.org_validator import md_reporting_roles
        from utils.api_pipeline_scope import get_staff_roster
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    units = set(md_reporting_roles() or [])
    if not units:
        print("ABORT: no MD-reporting units found - org_config is not loaded.")
        return 1

    # Real staff codes, so a record points at somebody who exists.
    codes = []
    try:
        df = get_staff_roster()
        codes = [str(c) for c in df["Staff Code"].tolist() if str(c).strip()]
    except Exception as exc:
        print("(roster unavailable: %s)" % str(exc)[:40])
    if not codes:
        print("ABORT: the staff roster is empty, so no real rm_code can be")
        print("       assigned. Run this where the register is present.")
        return 1

    records = json.load(open(path, encoding="utf-8"))
    if isinstance(records, dict):
        records = list(records.values())

    unmapped = sorted({str(r.get("sector") or "") for r in records}
                      - set(SECTOR_UNIT))
    print("=" * 72)
    print("PARTNERSHIP RESHAPE")
    print("=" * 72)
    print("  records            %d" % len(records))
    print("  real staff codes   %d available" % len(codes))
    if unmapped:
        print("  sectors with no unit mapping: %s" % ", ".join(x for x in unmapped if x))
        for u in FALLBACK_UNITS:
            print("     fallback: %s" % u)

    import collections
    plan = collections.Counter()
    changes = []
    for i, r in enumerate(records):
        if str(r.get("owner_type") or "").strip():
            continue
        sector = str(r.get("sector") or "").strip()
        unit = SECTOR_UNIT.get(sector) or FALLBACK_UNITS[i % len(FALLBACK_UNITS)]
        if unit not in units:
            # A mapping naming a unit that does not exist would silently
            # produce another unowned record.
            unit = FALLBACK_UNITS[i % len(FALLBACK_UNITS)]
        vol_m = r.get("expected_volume_kes_m")
        try:
            vol = float(vol_m or 0) * 1_000_000
        except (TypeError, ValueError):
            vol = 0.0
        changes.append((r, unit, codes[i % len(codes)], vol))
        plan[unit] += 1

    print("\n  PLANNED OWNERSHIP")
    for u, n in plan.most_common():
        print("     %-46s %d" % (u[:46], n))
    print("\n  targets derived from expected_volume_kes_m; NO budget invented -")
    print("  partnerships are measured on volume against expectation, and an")
    print("  invented spend would produce an ROI nobody agreed to.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    backup = path + ".pre_reshape"
    shutil.copy2(path, backup)
    for r, unit, code, vol in changes:
        r["owner_type"] = "unit"
        r["owner"] = unit
        r["department"] = unit
        r["rm_code"] = code
        if vol:
            r["target_value_kes"] = round(vol, 2)
            # A rough account target so progress has something to read against.
            r["target_accounts"] = max(1, int(vol // 5_000_000))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
    os.replace(tmp, path)
    print("\nreshaped %d partnerships (backup: %s)"
          % (len(changes), os.path.basename(backup)))
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
