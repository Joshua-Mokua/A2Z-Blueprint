#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Does this deployment have the CONFIG its CODE expects? READ ONLY.

WHY THIS EXISTS. The pilot merged the release and got the funnel code, but not
the funnel config - stage_buckets, stage_probabilities and credit_bands are
written by scripts someone has to remember to run after merging. Nobody did, so
the pilot has been drawing the old stage vocabulary and falling back to the
legacy probability map, where deals at Application and Credit Assessment are
silently worth zero.

Code ships with git. Config does not. A feature that needs both is only half
deployed until someone checks - which is what this does.

Run it on ANY deployment after a release:

    python scripts\\diag_deploy_check.py
"""
import os
import sys

sys.path.insert(0, os.getcwd())

OK = "  ok  "
BAD = "  ***"


def rule(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


def main():
    problems = []

    rule("1. PIPELINE JOURNEY (funnel, weighted value, credit bands)")
    try:
        from utils.core import get_pipeline_settings
        ps = get_pipeline_settings() or {}
    except Exception as exc:
        print("%s could not read pipeline settings: %s" % (BAD, exc))
        return 1

    buckets = ps.get("stage_buckets") or {}
    probs = ps.get("stage_probabilities") or {}
    bands = ps.get("credit_bands") or []
    flows = ps.get("stage_flows") or {}

    if buckets:
        print("%sstage_buckets: %d flows" % (OK, len(buckets)))
    else:
        print("%s stage_buckets MISSING" % BAD)
        problems.append(("stage_buckets absent - the funnel cannot draw the "
                         "Initiation-to-Disbursement journey",
                         "python scripts\\migrate_stage_buckets.py   (review, then --apply)"))

    if probs:
        print("%sstage_probabilities: %d flows" % (OK, len(probs)))
    else:
        print("%s stage_probabilities MISSING" % BAD)
        problems.append(("stage_probabilities absent - every weighted figure "
                         "falls back to the legacy 6-stage map, where deals at "
                         "Application and Credit Assessment are worth ZERO",
                         "python scripts\\seed_funnel_config.py --apply"))

    if bands:
        print("%scredit_bands: %d" % (OK, len(bands)))
    else:
        print("%s credit_bands MISSING" % BAD)
        problems.append(("credit_bands absent",
                         "python scripts\\seed_funnel_config.py --apply"))

    # The vocabulary tells you whether the migration ever ran.
    asset = [str(x) for x in (flows.get("asset") or [])]
    old_vocab = {"Lead", "Contacted", "Qualified"}
    if asset and old_vocab.intersection(asset):
        print("%s stage_flows still uses the RETIRED vocabulary: %s"
              % (BAD, ", ".join(asset[:4])))
        problems.append(("stage_flows was never rebuilt from the buckets, so "
                         "the funnel is drawing stages the bank no longer uses",
                         "python scripts\\migrate_stage_buckets.py --apply"))
    elif asset:
        print("%sstage_flows asset: %s" % (OK, ", ".join(asset[:4])))

    rule("2. DAILY LOG")
    try:
        from utils.branch_log import load_log_config
        cfg = load_log_config() or {}
    except Exception as exc:
        print("%s could not read branch log config: %s" % (BAD, exc))
        cfg = {}

    for key, why, fix in (
        ("impact_tiers",
         "the 80/20 analytics show every activity as one colour",
         "python scripts\\seed_impact_tiers.py --apply"),
    ):
        if cfg.get(key):
            print("%s%s: present" % (OK, key))
        else:
            print("%s %s MISSING" % (BAD, key))
            problems.append((why, fix))

    # field_bounds is CODE, not config - it has defaults - so checking for the
    # config key was a false alarm. What actually matters is whether the guard
    # RUNS, and on 2026-08-11 it did not: AS1 deleted the definitions while
    # leaving submit() calling them, so every daily-log entry raised NameError.
    # Drafts still saved, so nobody noticed. Test the behaviour, not the key.
    # WHAT ACTUALLY MATTERS is the call/definition PAIR. A tree with neither is
    # simply pre-BD and fine; a tree with the CALL and no DEFINITION raises
    # NameError on every submit. On 2026-08-11 AS1 produced exactly that by
    # replacing the region where BD defines them, and it shipped to a release
    # branch twice before anyone checked. Drafts still save, so it is invisible
    # until someone files.
    # The submit path itself - the thing users actually do.
    try:
        import inspect as _inspect
        from utils.branch_log import BranchLogManager as _BLM
        src = _inspect.getsource(_BLM.submit)
        called = [n for n in ("check_bounds", "auto_fields", "compute_index")
                  if n + "(" in src]
        import utils.branch_log as _bl
        missing = [n for n in called if not hasattr(_bl, n)]
        # Only report the guard when it is actually wired in.
        if "check_bounds" in called and "check_bounds" not in missing:
            try:
                if _bl.check_bounds({"dfs_registrations": 708000000}) and not \
                        _bl.check_bounds({"dfs_registrations": 12}):
                    print("%splausibility guard: rejects 708,000,000, accepts 12" % OK)
                else:
                    print("%s plausibility guard is not rejecting the implausible" % BAD)
                    problems.append(("check_bounds runs but accepts a KES amount "
                                     "in a count field",
                                     "inspect field_bounds in utils/branch_log.py"))
            except Exception as exc:
                print("%s plausibility guard raised: %s" % (BAD, str(exc)[:40]))
        elif "check_bounds" not in called:
            print("  plausibility guard not wired into submit (pre-BD tree)")
        if missing:
            print("%s submit() calls undefined name(s): %s" % (BAD, ", ".join(missing)))
            problems.append(("submit() calls %s which is not defined in the "
                             "module - every entry raises NameError"
                             % ", ".join(missing),
                             "python scripts\\hotfix_bounds_defs.py --apply"))
        else:
            print("%ssubmit() calls %d helper(s), all defined" % (OK, len(called)))
    except Exception as exc:
        print("  submit inspection skipped: %s" % str(exc)[:40])

    for key in ("activity_sets", "unit_activity_weights"):
        v = cfg.get(key) or {}
        print("%s%s: %d configured%s"
              % (OK, key, len(v), "" if v else "  (branch base everywhere)"))

    rule("3. ORG CONFIG")
    try:
        from utils.config import load_org_config
        org = load_org_config() or {}
    except Exception:
        org = {}
    for key, why in (
        ("daily_log_branch_validator_roles",
         "the branch triad cannot be resolved - daily-log validation falls back "
         "to an admin default"),
        ("unit_display_names",
         "units read as job titles rather than departments"),
    ):
        if org.get(key):
            print("%s%s: present" % (OK, key))
        else:
            print("%s %s MISSING - %s" % (BAD, key, why))
            problems.append((why, "re-run the seed script for this key"))

    rule("4. DATABASE")
    try:
        from utils.db import db
        if db.is_postgres_ready():
            seq = db.fetch_scalar(
                "SELECT 1 FROM pg_class WHERE relname='pipeline_deal_seq'", ())
            if seq:
                print("%spipeline_deal_seq exists" % OK)
            else:
                print("%s pipeline_deal_seq MISSING" % BAD)
                problems.append(("every deal-create will 500 on an id collision",
                                 "python scripts\\create_deal_id_sequence.py"))
        else:
            print("  postgres not reachable from here - skipped")
    except Exception as exc:
        print("  db check skipped: %s" % str(exc)[:50])

    rule("VERDICT")
    if not problems:
        print("Config matches the code. Nothing outstanding.")
        return 0

    print("%d thing(s) the code expects but this deployment does not have:\n"
          % len(problems))
    for why, fix in problems:
        print("   * %s" % why)
        print("     -> %s" % fix)
        print("")
    print("Code arrives with git; config does not. Until these are run, the")
    print("features are only half deployed - and they fail QUIETLY, which is")
    print("why nobody notices until a number looks wrong.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
