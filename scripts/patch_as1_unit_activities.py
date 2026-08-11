#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AS1 - per-unit daily-log activity sets. The mechanism, plus a first cut.

PILOT REQUEST (2026-08-10): "each department has unique set of activities, and
the one that will cut across currently is the referral ... enable the admin to
select from a list of all units and create the unique listing ... the branches
one seems ok and can be left like that."

RULINGS: the daily target stays the SAME for everyone - only the WEIGHTS vary.
Head Office units keep NOTHING from the branch base except the REFERRAL.

WHY THIS MATTERS. 169 Head Office staff across 17 units are currently logging
BRANCH activities - Customers Served, Transactions Processed, Accounts Opened.
For an Internal Auditor, an FX Trader or a Compliance Officer those are
meaningless, so the index for a third of the bank is measuring the wrong thing.

WHAT LANDS
  branch_log.activity_sets()   {unit: [field key]} from config
  branch_log.fields_for_unit() a unit's base set
  branch_log.fields_for(role, unit)  unit set + extras scoped to role OR UNIT
  extra_activities now scope by `units` as well as the `roles` they already had

  COMMON_KEYS = ("loans_referred",) travels to every unit whatever it
  configures - the referral is the one activity that genuinely cuts across.

THE SAFE DEFAULT, and the reason nothing breaks today: a unit with NO configured
set keeps the FULL BRANCH BASE. Switching a unit to an empty set would drop
every activity its people log and their index would read zero - not because they
did nothing, but because nothing is configured. Absence of config must never
look like absence of work.

  scripts/seed_unit_activities.py writes a FIRST CUT derived from the roles
  actually present in each unit on the live roster. It is a starting point for
  the admin, not an answer.

  It writes ONLY units that have applicable existing fields. The other eleven
  are left on the branch base, because most Head Office work has no matching
  field yet - an Internal Auditor has no "Audits Completed", an FX Trader has no
  "Deals Executed". The script PRINTS the 31 new activities those units need so
  the admin creates them deliberately, with weights the bank decides. Inventing
  weights here would bake guesses into everyone's index, and a guessed weight is
  worse than an absent one: it looks authoritative and nobody questions it.

  The seeder also ABORTS if a proposed set names a field that does not exist -
  which it did on the first run, catching four invented key names.

Verified: py_compile clean; an unconfigured unit still returns all 18 fields;
branch roles unchanged.

Usage (from project root, .venv active):
    python scripts\patch_as1_unit_activities.py            # dry run
    python scripts\patch_as1_unit_activities.py --apply

Then review the first cut - it writes nothing until you say so:
    python scripts\seed_unit_activities.py
    python scripts\seed_unit_activities.py --apply
"""
import os
import shutil
import sys

BL = os.path.join("utils", "branch_log.py")
SEED = os.path.join("scripts", "seed_unit_activities.py")
BACKUP_SUFFIX = ".pre_as1"

ANCHOR = "def fields_for_role(role: str) -> list:"

SEGMENT = r'''# ── PER-UNIT ACTIVITY SETS (pilot request, 2026-08-10) ──────────────────────
# "each department has unique set of activities, and the one that will cut
#  across currently is the referral ... enable the admin to select from a list
#  of all units and create the unique listing."
#
# RULINGS: the daily target stays the SAME for everyone - only the WEIGHTS vary
# per activity. Head Office units keep NOTHING from the branch base except the
# referral.
#
# Until a unit has a set defined, it keeps the branch base. That is deliberate:
# switching a unit to an empty set would drop every activity its people log and
# their index would read zero - not because they did nothing, but because
# nothing is configured. Absence of config must not look like absence of work.
COMMON_KEYS = ("loans_referred",)


def activity_sets() -> dict:
    """{unit: [field key, ...]} from branch_log_config.activity_sets."""
    try:
        cfg = load_log_config() or {}
        v = cfg.get("activity_sets")
        if isinstance(v, dict):
            return {str(k): [str(x) for x in (vv or [])] for k, vv in v.items()}
    except Exception:
        pass
    return {}


def fields_for_unit(unit: str) -> list:
    """The base activity set for a unit.

    A unit with no configured set falls back to the FULL branch base - see the
    note above on why an empty set is the wrong default.
    """
    sets = activity_sets()
    keys = sets.get(str(unit or "").strip())
    base = fields_schema()
    if not keys:
        return base
    # COMMON_KEYS always travel, whatever the unit configured. The referral is
    # the one activity that genuinely cuts across every desk in the bank.
    want = list(dict.fromkeys(list(keys) + list(COMMON_KEYS)))
    by_key = {f["key"]: f for f in base}
    return [by_key[k] for k in want if k in by_key]


'''

FIELDS_FOR = r'''def fields_for_role(role: str) -> list:
    """Activity fields for a role: the common base + admin extras whose 'roles'
    is empty (common) or includes this role."""
    return fields_for(role, "")


def fields_for(role: str, unit: str = "") -> list:
    """Activity fields for a person: their UNIT's set, plus admin extras scoped
    to their role or unit (or scoped to neither, meaning common)."""
    out = fields_for_unit(unit) if unit else fields_schema()
    w = activity_weights()
    rl = str(role or "").strip().lower()
    un = str(unit or "").strip().lower()
    for a in _extra_activities():
        k = str(a.get("key") or "").strip()
        if not k:
            continue
        roles = [str(x).strip().lower() for x in (a.get("roles") or [])]
        if roles and rl and rl not in roles:
            continue
        # Unit scoping, alongside the role scoping that already existed.
        units = [str(x).strip().lower() for x in (a.get("units") or [])]
        if units and un and un not in units:
            continue
        out.append({"key": k, "label": a.get("label", k), "type": a.get("type", "int"),
                    "unit": a.get("unit", ""), "bsc_kpi": None,
                    "weight": float(w.get(k, a.get("weight", 0)) or 0),
                    "roles": a.get("roles") or [],
                    "units": a.get("units") or []})
    return out


'''

SEEDER = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
First-cut activity sets per Head Office unit. A STARTING POINT, not an answer.

Pilot request (2026-08-10): "each department has unique set of activities, and
the one that will cut across currently is the referral ... enable the admin to
select from a list of all units and create the unique listing ... if we can look
at the various roles within each unit we can come up with a first cut that the
admin can build on."

So this is drawn from the roles actually in each unit on the live roster - not
invented - and written into branch_log_config.activity_sets for the admin panel
to edit. Every unit below is a proposal the bank should correct.

RULINGS HONOURED
    the daily target stays the SAME for everyone; only WEIGHTS vary
    Head Office units keep NOTHING from the branch base except the REFERRAL
    Branches are unchanged - the branch set is already right

WHY NEW ACTIVITIES ARE PROPOSED, NOT CREATED. Most Head Office work has no
matching field today: an Internal Auditor has no "Audits Completed", an FX
Trader has no "Deals Executed". This script writes sets from EXISTING fields
only, and PRINTS the new activities each unit needs so the admin can create
them deliberately. Inventing fields and weights here would bake guesses into
everyone's index.

THE ORDER MATTERS. Do not switch a unit off the branch base before its set
exists - its people would log nothing and their index would read zero, which
looks identical to having done no work.

    python scripts\\seed_unit_activities.py            # show the proposal
    python scripts\\seed_unit_activities.py --apply
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

# Existing field keys that plausibly apply, per unit, from the roles actually
# present. Deliberately sparse: a short honest set beats a long invented one.
PROPOSED = {
    "Director Operations & Technology": [
        "customer_visits", "transactions_count", "complaints_resolved",
        "complaints_received", "digital_txns", "teller_errors",
    ],
    "Director, Corporate Banking Kenya & EAC": [
        "new_leads", "deposits_mobilised", "loans_disbursed",
        "cross_sell_success", "accounts_opened",
    ],
    "Head of Consumer": [
        "new_leads", "accounts_opened", "dfs_registrations",
        "cards_issued", "bancassurance_sold", "cross_sell_success",
    ],
    "Director Consumer & Commercial Banking (CCB)": [
        "new_leads", "deposits_mobilised", "loans_disbursed", "cross_sell_success",
    ],
    "Director, Credit Risk Management- Kenya & EAC": [
        "loans_disbursed",
    ],
    "Director, Treasury & FICC, EAC": [
        "deposits_mobilised", "new_leads",
    ],
    "Chief Finance Officer": [],
    "Director, Internal Control": [],
    "Director, Internal Audit": [],
    "Country Risk Manager, Kenya & EAC": [],
    "Director Compliance- CESA 1": [],
    "Director, Legal Services & Company Secretary": [],
    "Ag. Head Human Resources & Senior HR Business": [],
    "Corporate Communications Manager": [],
    "Business Manager": [],
    "Personal Assistant": [],
}

# Activities these units genuinely need that DO NOT EXIST yet. Printed for the
# admin to create with weights the bank decides - not written by this script.
NEEDED = {
    "Director Operations & Technology": [
        "Calls handled", "Tickets resolved", "Payments processed",
        "Reconciliation items cleared", "SLA breaches",
    ],
    "Chief Finance Officer": [
        "Reports delivered", "Reconciliations completed", "Queries closed",
    ],
    "Director, Internal Control": [
        "Controls tested", "Exceptions raised", "Exceptions closed",
    ],
    "Director, Internal Audit": [
        "Audit engagements progressed", "Findings raised", "Findings closed",
    ],
    "Director, Credit Risk Management- Kenya & EAC": [
        "Applications appraised", "Turnaround within SLA", "Securities perfected",
    ],
    "Country Risk Manager, Kenya & EAC": [
        "Risk events logged", "Assessments completed",
    ],
    "Director Compliance- CESA 1": [
        "Alerts reviewed", "KYC reviews completed", "STRs filed",
    ],
    "Director, Legal Services & Company Secretary": [
        "Contracts reviewed", "Matters progressed",
    ],
    "Ag. Head Human Resources & Senior HR Business": [
        "Positions filled", "Cases closed", "Training sessions delivered",
    ],
    "Corporate Communications Manager": [
        "Publications issued", "Engagements run",
    ],
    "Director, Treasury & FICC, EAC": [
        "Deals executed", "Client quotes given",
    ],
}


def main():
    apply = "--apply" in sys.argv
    try:
        from utils.branch_log import load_log_config, fields_schema, COMMON_KEYS
        from utils.org_validator import unit_for_role
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    known = {f["key"] for f in fields_schema()}
    bad = {u: [k for k in ks if k not in known] for u, ks in PROPOSED.items()}
    bad = {u: v for u, v in bad.items() if v}
    if bad:
        print("ABORT: proposed sets reference fields that do not exist:")
        for u, v in bad.items():
            print("   %-46s %s" % (u[:46], ", ".join(v)))
        print("Fix the key names in this script - a set pointing at a missing")
        print("field would silently give that unit fewer activities than intended.")
        return 1

    print("=" * 74)
    print("FIRST-CUT ACTIVITY SETS - Head Office")
    print("=" * 74)
    print("Every unit also gets: %s" % ", ".join(COMMON_KEYS))
    print("")
    for u in sorted(PROPOSED):
        ks = PROPOSED[u]
        print("%s" % u[:70])
        if ks:
            print("   existing : %s" % ", ".join(ks))
        else:
            print("   existing : (none apply)")
        need = NEEDED.get(u) or []
        if need:
            print("   NEEDS NEW: %s" % "; ".join(need))
        print("")

    total_new = sum(len(v) for v in NEEDED.values())
    print("=" * 74)
    print("%d units proposed · %d NEW activities the admin must create"
          % (len(PROPOSED), total_new))
    print("=" * 74)
    print("The new activities are NOT written by this script. Their weights")
    print("decide people's index, and a guessed weight is worse than an absent")
    print("one - it looks authoritative and nobody questions it.")
    print("")
    print("Units with an empty set keep the branch base until the admin defines")
    print("theirs. Switching them off it first would show their people zero.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    cfg = load_log_config() or {}
    existing = cfg.get("activity_sets") or {}
    # Only write units that HAVE a set. An empty list would switch that unit
    # off the branch base with nothing to replace it.
    written = {u: ks for u, ks in PROPOSED.items() if ks}
    for u, ks in written.items():
        existing[u] = ks
    cfg["activity_sets"] = existing

    path = os.path.join("data", "branch_log_config.json")
    backup = path + ".pre_unitsets"
    if os.path.isfile(path):
        import shutil
        shutil.copy2(path, backup)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, path)
    print("\nwrote %d unit sets to %s (backup: %s)"
          % (len(written), path, os.path.basename(backup)))
    print("Units with no existing fields were LEFT OUT deliberately - they keep")
    print("the branch base until their activities exist.")
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BL):
        print("ABORT: %s not found. Run from the project root." % BL)
        return 1

    s = open(BL, encoding="utf-8").read()
    if "def fields_for_unit(" in s:
        print("ABORT: fields_for_unit already present - AS1 looks applied.")
        return 1
    if "def auto_fields()" not in s:
        print("ABORT: apply patch_rf3_auto_referral_field.py first.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: fields_for_role matched %d times." % s.count(ANCHOR))
        return 1

    i = s.index(ANCHOR)
    j = s.index("class BranchLogManager:")

    # PRESERVE anything else living in this region. The embedded FIELDS_FOR was
    # extracted from a tree WITHOUT the bounds patcher, so replacing the region
    # wholesale deleted field_bounds and check_bounds while leaving the call in
    # submit() - every daily-log entry then raised NameError. Verified: BD and
    # RF3 leave defs=2; AS1 alone took it to defs=0.
    region = s[i:j]
    keep = ""
    k = region.find("def field_bounds(")
    if k >= 0:
        # Everything from the bounds constant onward belongs to BD, not to us.
        c = region.rfind("_DEFAULT_BOUNDS", 0, k)
        start = region.rfind("\n", 0, c) + 1 if c >= 0 else k
        keep = region[start:]
        print("  ok  preserving %d lines of bounds code that live in this region"
              % keep.count("\n"))

    s = s[:i] + SEGMENT + FIELDS_FOR + keep + s[j:]
    print("  ok  activity_sets / fields_for_unit / fields_for added")

    # The safe default is the whole point: no config must mean no change.
    if "return base" not in SEGMENT:
        print("ABORT: fields_for_unit does not fall back to the branch base.")
        print("       Without that, an unconfigured unit shows its people zero.")
        return 1
    if "COMMON_KEYS" not in SEGMENT or "loans_referred" not in SEGMENT:
        print("ABORT: the referral is not carried as a common activity.")
        return 1
    if "def fields_for_role(" not in FIELDS_FOR:
        print("ABORT: fields_for_role was dropped - existing callers would break.")
        return 1
    if 'a.get("units")' not in FIELDS_FOR:
        print("ABORT: extra activities do not scope by unit.")
        return 1
    if s.count("def fields_for_role(") != 1 or s.count("def fields_for(") != 1:
        print("ABORT: post-check - duplicate definitions.")
        return 1
    # A call without a definition is worse than neither: submit() raises on
    # every entry, and drafts still save, so it is not noticed until someone
    # actually files.
    if "check_bounds(metrics)" in s and "def check_bounds(" not in s:
        print("ABORT: post-check - this would leave submit() calling")
        print("       check_bounds with no definition. Every daily-log entry")
        print("       would raise NameError.")
        return 1
    print("  ok  post-checks: safe fallback, referral common, role API intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BL, BL + BACKUP_SUFFIX)
    open(BL, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s  (backup: %s)" % (BL, os.path.basename(BL) + BACKUP_SUFFIX))
    if not os.path.exists(SEED):
        open(SEED, "w", encoding="utf-8", newline="").write(SEEDER)
        print("CREATED %s" % SEED)

    import py_compile
    try:
        py_compile.compile(BL, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Nothing changes until sets are defined. Review the first cut:")
    print("  python scripts\\seed_unit_activities.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
