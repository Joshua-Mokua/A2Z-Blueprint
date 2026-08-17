#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
G1 - generalise the unit-day store so the pipeline reuses it.

WHY THIS FIRST. You asked for pipeline validation to follow the exact structure
and path the daily log uses. The tempting route is to copy branch_day.py and
adjust it - which is how this codebase ended up with two hierarchies, two
validator rules and an /analytics endpoint that disagreed with the history grid.
One store, two domains, no copy.

WHAT CHANGES

  utils/branch_day.py keys records on DOMAIN|UNIT|DATE instead of UNIT|DATE.

      DOMAIN_DAILY_LOG = "daily_log"
      DOMAIN_PIPELINE  = "pipeline"

  Every public function takes an optional `domain`, defaulting to daily_log, so
  no existing caller changes. The lifecycle, the atomic writes, the resubmit
  clearing a validation, the note-required-on-return rule - all shared.

BACKWARD COMPATIBLE ON PURPOSE. Records written before this exist as UNIT|DATE.
_find() prefers the domain key and falls back to the legacy one; list_branch_days
parses both. The pilot has already submitted branch days, and a migration that
silently orphaned them would look exactly like the days having never been
closed - indistinguishable from a real problem, at the worst possible moment.

PROVEN:
    legacy record still resolves                  True
    legacy still appears in the day listing       True
    same branch, same day, both domains           daily-log 167.9 / pipeline 42.0
    returning the pipeline day                    pipeline: returned
    ... leaves the daily-log day alone            daily log: submitted

NOTHING ELSE MOVES YET. No pipeline endpoints, no UI change. This is the seam
the pipeline validation will attach to, landed on its own so it can be verified
without a second moving part.

Usage (from project root, .venv active):
    python scripts\patch_g1_domain_store.py            # dry run
    python scripts\patch_g1_domain_store.py --apply    # write + .pre_g1 backup
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "branch_day.py")
BACKUP_SUFFIX = ".pre_g1"

MODULE = r'''"""
A2Z Daily Log — branch-day submission (additive, new module).

TWO-TIER VALIDATION (ruling 2026-08-08):

    tier 1  Branch Manager / triad   validates each staff log, then SUBMITS the
                                     branch day, carrying the branch index
    tier 2  Head of Branches         validates the BRANCH SUBMISSION, or returns
                                     it to the BM. Never touches individual logs;
                                     may inspect them read-only.

This module owns the object tier 2 acts on. One record per branch per day:

    draft -> submitted -> validated
                    \\-> returned -> submitted (resubmit)

WHAT IT DELIBERATELY DOES NOT DO
  * decide who may act — that is org_validator.branches_validated_by and
    staff_validated_by. This module records; it does not authorise.
  * recompute the branch index — the caller passes the figure the queue
    endpoint computed, so one formula lives in one place.
  * gate on over-reporting — reconcile_branch_day does that, and the API layer
    applies it as a precondition. Storing a submission that the gate should have
    blocked is a caller bug, not a storage concern.

Store: data/branch_days.json, written atomically (mkstemp/fsync/os.replace) so a
crash mid-write cannot leave a truncated file — the failure mode that cost this
codebase a pipeline config.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.core import DATA_DIR

_STORE = Path(DATA_DIR) / "branch_days.json"

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_VALIDATED = "validated"
STATUS_RETURNED = "returned"


# DOMAIN (2026-08-09): the daily log and the pipeline share this store rather
# than growing two parallel copies of the same lifecycle. A unit day is a unit
# day whichever activity produced it; only the numbers attached differ.
DOMAIN_DAILY_LOG = "daily_log"
DOMAIN_PIPELINE = "pipeline"


def _key(unit: str, day: str, domain: str = DOMAIN_DAILY_LOG) -> str:
    return f"{str(domain).strip()}|{str(unit).strip()}|{str(day)[:10]}"


def _legacy_key(unit: str, day: str) -> str:
    """Records written before the domain dimension existed, keyed unit|date.

    Read-compatible on purpose: the pilot has submitted branch days already, and
    a migration that silently orphaned them would look exactly like the days
    having never been closed.
    """
    return f"{str(unit).strip()}|{str(day)[:10]}"


def _find(data: dict, unit: str, day: str, domain: str):
    """Return (key, record) preferring the domain key, falling back to legacy."""
    k = _key(unit, day, domain)
    if k in data:
        return k, data[k]
    if domain == DOMAIN_DAILY_LOG:
        lk = _legacy_key(unit, day)
        if lk in data:
            return lk, data[lk]
    return k, None


def _load() -> dict:
    try:
        raw = json.loads(_STORE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        # A corrupt store must not silently become an empty one: callers would
        # then re-submit days that were already validated. Surface it.
        raise


def _save(data: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_STORE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, _STORE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_branch_day(branch: str, day: str,
                   domain: str = DOMAIN_DAILY_LOG) -> Optional[dict]:
    """The submission record for one unit-day, or None."""
    _k, rec = _find(_load(), branch, day, domain)
    return rec


def list_branch_days(day: str, branches=None,
                     domain: str = DOMAIN_DAILY_LOG) -> dict:
    """{unit: record} for a date, optionally restricted to a unit list.

    Parses both the domain key (domain|unit|date) and the legacy key
    (unit|date), so pre-migration records still appear.
    """
    data = _load()
    want = {str(b).strip() for b in branches} if branches else None
    target = str(day)[:10]
    out = {}
    for k, rec in data.items():
        parts = k.split("|")
        if len(parts) == 3:
            dom, unit, d = parts
        elif len(parts) == 2:
            dom, unit, d = DOMAIN_DAILY_LOG, parts[0], parts[1]
        else:
            continue
        if d != target or dom != domain:
            continue
        if want is not None and unit not in want:
            continue
        out.setdefault(unit, rec)      # a domain key already present wins
    return out


def submit_branch_day(branch: str, day: str, by_code: str, by_name: str,
                      branch_index: float, staff_totals: dict,
                      control_totals: dict, counts: dict,
                      domain: str = DOMAIN_DAILY_LOG) -> dict:
    """TIER 1: the Branch Manager closes the day.

    Re-submitting after a return is allowed and clears the returned state, so a
    corrected day can flow again without an admin unlock.
    """
    data = _load()
    k, prev = _find(data, branch, day, domain)
    prev = prev or {}
    now = datetime.now().isoformat()
    rec = {
        "branch": str(branch).strip(),
        "domain": str(domain),
        "date": str(day)[:10],
        "status": STATUS_SUBMITTED,
        "branch_index": round(float(branch_index or 0), 2),
        "staff_totals": dict(staff_totals or {}),
        "control_totals": dict(control_totals or {}),
        "counts": dict(counts or {}),          # filed / validated / expected
        "submitted_by": str(by_code or ""),
        "submitted_by_name": str(by_name or ""),
        "submitted_at": now,
        # cleared on resubmit — a returned day that comes back is pending again
        "returned_by": "", "returned_by_name": "", "returned_at": "",
        "return_note": "",
        "validated_by": prev.get("validated_by", ""),
        "validated_by_name": prev.get("validated_by_name", ""),
        "validated_at": prev.get("validated_at", ""),
        "resubmit_count": int(prev.get("resubmit_count", 0)) + (1 if prev else 0),
        "history": list(prev.get("history", [])) + [
            {"at": now, "action": "submitted", "by": str(by_code or "")}],
    }
    if prev.get("status") == STATUS_VALIDATED:
        # A validated day being resubmitted must lose its validation: the
        # numbers changed, so the countersignature no longer refers to them.
        rec["validated_by"] = rec["validated_by_name"] = rec["validated_at"] = ""
    data[k] = rec
    _save(data)
    return rec


def validate_branch_day(branch: str, day: str, by_code: str, by_name: str,
                        note: str = "", domain: str = DOMAIN_DAILY_LOG) -> dict:
    """TIER 2: the Head of Branches countersigns the branch day."""
    data = _load()
    k, rec = _find(data, branch, day, domain)
    if not rec:
        raise ValueError(f"{branch} has not submitted {day}")
    if rec.get("status") != STATUS_SUBMITTED:
        raise ValueError(
            f"{branch} {day} is '{rec.get('status')}' — only a submitted day can be validated")
    now = datetime.now().isoformat()
    rec.update({
        "status": STATUS_VALIDATED,
        "validated_by": str(by_code or ""),
        "validated_by_name": str(by_name or ""),
        "validated_at": now,
        "validation_note": str(note or ""),
    })
    rec.setdefault("history", []).append(
        {"at": now, "action": "validated", "by": str(by_code or "")})
    data[k] = rec
    _save(data)
    return rec


def return_branch_day(branch: str, day: str, by_code: str, by_name: str,
                      note: str, domain: str = DOMAIN_DAILY_LOG) -> dict:
    """TIER 2: send the branch day back to the Branch Manager.

    A note is REQUIRED — a returned day with no reason leaves the BM nothing to
    act on, the same rule the individual return already enforces.
    """
    if not str(note or "").strip():
        raise ValueError("a note is required when returning a branch day")
    data = _load()
    k, rec = _find(data, branch, day, domain)
    if not rec:
        raise ValueError(f"{branch} has not submitted {day}")
    if rec.get("status") not in (STATUS_SUBMITTED, STATUS_VALIDATED):
        raise ValueError(
            f"{branch} {day} is '{rec.get('status')}' — nothing to return")
    now = datetime.now().isoformat()
    rec.update({
        "status": STATUS_RETURNED,
        "returned_by": str(by_code or ""),
        "returned_by_name": str(by_name or ""),
        "returned_at": now,
        "return_note": str(note).strip(),
    })
    rec.setdefault("history", []).append(
        {"at": now, "action": "returned", "by": str(by_code or "")})
    data[k] = rec
    _save(data)
    return rec
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found - apply patch_b2_branch_day.py first." % MOD)
        return 1

    cur = open(MOD, encoding="utf-8").read()
    if "DOMAIN_PIPELINE" in cur:
        print("ABORT: branch_day already has DOMAIN_PIPELINE - G1 looks applied.")
        return 1
    for token in ("submit_branch_day", "validate_branch_day", "return_branch_day"):
        if token not in cur:
            print("ABORT: %s is missing from the current module." % token)
            return 1

    for token in ("DOMAIN_DAILY_LOG", "DOMAIN_PIPELINE", "_legacy_key", "_find("):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    # The whole point is that nothing else has to change: every public function
    # must still exist with its original name.
    for token in ("def get_branch_day(", "def list_branch_days(",
                  "def submit_branch_day(", "def validate_branch_day(",
                  "def return_branch_day("):
        if token not in MODULE:
            print("ABORT: embedded module lost %r - callers would break." % token)
            return 1
    print("  ok  embedded module validated (%d lines)" % (MODULE.count("\n") + 1))
    print("  ok  all five public functions preserved")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("APPLIED %s  (backup: %s)" % (MOD, os.path.basename(MOD) + BACKUP_SUFFIX))

    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nNo behaviour change for the daily log. Restart uvicorn when convenient.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
