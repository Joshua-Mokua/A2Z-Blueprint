#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AS2 - per-unit activity weights. The target stays the same; the weights vary.

RULING (2026-08-10): "the target will be the same, maybe the weights is what
shall vary on the various activities."

AS1 gave each unit its own SET of activities but left weights global, so
Treasury and a contact centre would value a referral identically and there was
no way to say otherwise. Applying the sets without this would have put real
people under target for a configuration reason rather than a performance one -
which on a pilot costs trust in the whole index.

AN OVERLAY, NOT A REPLACEMENT. A unit sets only the activities whose value
differs for it; everything else keeps the bank-wide weight. A unit forced to
restate every weight would silently drift out of step the moment a global one
changed.

    branch_log_config.unit_activity_weights = {
        "Director, Treasury & FICC, EAC": {"loans_referred": 8.0}
    }

WHAT CHANGES
    unit_activity_weights()      the raw overrides
    weights_for_unit(unit)       global weights with the unit's overlaid
    compute_index(metrics, unit) unit defaults to "" so EVERY existing caller
                                 keeps bank-wide weights and nothing moves until
                                 a unit is actually configured

    All four submit/draft sites pass the person's unit. The analytics recompute
    passes the LOG'S OWN unit, so a read-time index cannot disagree with the
    stored one.

    fields_for_unit() restates each weight as that unit sees it. Otherwise the
    admin panel would show the bank-wide number while the index used the unit's
    - the kind of quiet disagreement that makes people stop trusting a figure
    rather than report it.

MEASURED with Treasury set to value a referral at 8.0:
    global referral weight        3.0
    Treasury referral weight      8.0
    Operations (unconfigured)     3.0   <- inherits, as it should
    index for 2 referrals         6.0 bank-wide / 16.0 Treasury
    schema shows Treasury         8.0   <- same number the index used

The daily target is untouched and stays global, exactly as ruled.

NOW the AS1 sets can be applied alongside weights, so no unit is ever visibly
under target for a reason that is not its people's.

Verified: py_compile clean across branch_log, branch_log_analytics and
api_branch_log; every compute_index call site passes a unit.

REQUIRES AS1.

Usage (from project root, .venv active):
    python scripts\patch_as2_unit_weights.py            # dry run
    python scripts\patch_as2_unit_weights.py --apply
"""
import os
import shutil
import sys

BL = os.path.join("utils", "branch_log.py")
AN = os.path.join("utils", "branch_log_analytics.py")
API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_as2"

W_OLD = '''def activity_weights() -> dict:
    return load_log_config().get("activity_weights", {}) or {}'''

CI_OLD = '''def compute_index(metrics: dict) -> float:
    """Productivity index for a log = sum(activity count x admin weight)."""
    w = activity_weights()'''

FU_OLD = "def fields_for_unit(unit: str) -> list:"

SET_OLD = '''    sets = activity_sets()
    keys = sets.get(str(unit or "").strip())
    base = fields_schema()
    if not keys:
        return base'''
SET_NEW = '''    sets = activity_sets()
    u = str(unit or "").strip()
    keys = sets.get(u)
    base = _reweight(fields_schema(), u)
    if not keys:
        return base'''

# After RF1, _effective_index assigns rather than returns, and does so TWICE
# (the stored-index fallback and the no-stored-index path). Both must carry the
# unit or an override would apply on write and vanish on read.
AN_OLD = "base = compute_index({k: log.get(k, 0) for k in metric_keys()})"
AN_NEW = ('base = compute_index({k: log.get(k, 0) for k in metric_keys()},\n'
          '                             str(log.get("unit", "") or ""))')

API_OLD = '            idx = compute_index({k: l.get(k, 0) for k in metric_keys()})'
API_NEW = '''            idx = compute_index({k: l.get(k, 0) for k in metric_keys()},
                                str(l.get("unit", "") or ""))'''

WEIGHTS = r'''def activity_weights() -> dict:
    return load_log_config().get("activity_weights", {}) or {}


def unit_activity_weights() -> dict:
    """{unit: {activity key: weight}} — per-unit OVERRIDES, from config."""
    try:
        v = (load_log_config() or {}).get("unit_activity_weights")
        if isinstance(v, dict):
            out = {}
            for u, m in v.items():
                if not isinstance(m, dict):
                    continue
                got = {}
                for k, w in m.items():
                    try:
                        got[str(k)] = float(w)
                    except (TypeError, ValueError):
                        continue
                if got:
                    out[str(u)] = got
            return out
    except Exception:
        pass
    return {}


def weights_for_unit(unit: str = "") -> dict:
    """The weights that apply to a person in this unit.

    RULING 2026-08-10: "the target will be the same, maybe the weights is what
    shall vary on the various activities." So the TARGET is global and the
    weights are per unit.

    An OVERLAY, not a replacement: a unit sets only the activities whose value
    differs for it, and everything else keeps the bank-wide weight. A unit that
    had to restate every weight would drift out of step the moment a global one
    changed, and nobody would notice.
    """
    base = dict(activity_weights())
    over = unit_activity_weights().get(str(unit or "").strip())
    if over:
        base.update(over)
    return base'''

COMPUTE = r'''def compute_index(metrics: dict, unit: str = "") -> float:
    """Productivity index for a log = sum(activity count x admin weight).

    `unit` selects that unit's weights where it has overridden them. It defaults
    to "" so every existing caller keeps the bank-wide weights and nothing
    changes until a unit is actually configured.
    """
    w = weights_for_unit(unit) if unit else activity_weights()
    total = 0.0
    for k, v in (metrics or {}).items():
        try:
            total += float(v or 0) * float(w.get(k, 0) or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)'''

REWEIGHT = r'''def _reweight(fields: list, unit: str) -> list:
    """Restate each field's weight as the UNIT sees it.

    Without this the admin panel would show the bank-wide number while the
    index used the unit's - the kind of quiet disagreement that makes people
    stop trusting the figure rather than report it.
    """
    if not unit:
        return fields
    w = weights_for_unit(unit)
    out = []
    for f in fields:
        g = dict(f)
        g["weight"] = float(w.get(f.get("key"), f.get("weight", 0)) or 0)
        out.append(g)
    return out


'''


def main():
    apply = "--apply" in sys.argv
    for p in (BL, AN, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    bl = open(BL, encoding="utf-8").read()
    an = open(AN, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "def weights_for_unit(" in bl:
        print("ABORT: weights_for_unit already present - AS2 looks applied.")
        return 1
    if "def fields_for_unit(" not in bl:
        print("ABORT: apply patch_as1_unit_activities.py first.")
        return 1
    for name, hay, needle in (("activity_weights", bl, W_OLD),
                              ("compute_index", bl, CI_OLD),
                              ("fields_for_unit body", bl, SET_OLD),

                              ("api recompute", api, API_OLD)):
        if hay.count(needle) != 1:
            print("ABORT: %s matched %d times (expected 1)." % (name, hay.count(needle)))
            return 1

    bl = bl.replace(W_OLD, WEIGHTS, 1)
    bl = bl.replace(CI_OLD, COMPUTE, 1)
    bl = bl.replace(FU_OLD, REWEIGHT + FU_OLD, 1)
    bl = bl.replace(SET_OLD, SET_NEW, 1)
    bl = bl.replace('existing["index"] = compute_index(metrics)',
                    'existing["index"] = compute_index(metrics, unit)')
    bl = bl.replace('"index": compute_index(metrics),',
                    '"index": compute_index(metrics, unit),')
    print("  ok  branch_log - overlay, unit-aware index, reweighted schema")

    n_an = an.count(AN_OLD)
    if n_an < 1:
        print("ABORT: analytics recompute matched %d times." % n_an)
        return 1
    an = an.replace(AN_OLD, AN_NEW)          # BOTH paths in _effective_index
    print("  ok  analytics - %d recompute site(s) carry the unit" % n_an)
    api = api.replace(API_OLD, API_NEW, 1)
    print("  ok  analytics and api pass the log's own unit")

    # Every call site must carry a unit, or an override would apply on write
    # and vanish on read.
    import re
    for name, blob in (("branch_log", bl), ("analytics", an), ("api", api)):
        for m in re.finditer(r"compute_index\(([^\n]*)", blob):
            frag = m.group(1)
            if "def " in frag:
                continue
            if "unit" not in frag and not frag.rstrip().endswith(","):
                print("ABORT: %s has a compute_index call with no unit: %s"
                      % (name, frag[:60]))
                return 1
    if "unit_activity_weights" not in bl or "def weights_for_unit(" not in bl:
        print("ABORT: post-check - the overlay helpers are missing.")
        return 1
    if "daily_index_target" not in bl:
        print("ABORT: post-check - the global target helper vanished.")
        return 1
    print("  ok  post-checks: every call site carries a unit, target still global")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((BL, bl), (AN, an), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (BL, AN, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Nothing moves until a unit is configured. Set overrides in")
    print("data/branch_log_config.json under unit_activity_weights, e.g.")
    print('   {"Director, Treasury & FICC, EAC": {"loans_referred": 8.0}}')
    print("Then apply the AS1 sets:  python scripts\\seed_unit_activities.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
