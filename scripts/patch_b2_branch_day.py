#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
B2 - two-tier branch validation (backend).

RULING (2026-08-08):
    tier 1  Branch Manager / triad  validates each staff log, then CLOSES the
                                    branch day, carrying the branch index.
    tier 2  Head of Branches        validates the BRANCH SUBMISSION, or returns
                                    it to the BM with a reason. Never touches an
                                    individual log; may inspect them read-only.

WHAT THIS ADDS

  utils/branch_day.py  (new)
      One record per branch per day:
          draft -> submitted -> validated
                          \-> returned -> submitted (resubmit)
      Atomic writes (mkstemp/fsync/os.replace) — a crash mid-write cannot leave
      a truncated store, the failure that once cost this codebase its pipeline
      config. A corrupt store RAISES rather than degrading to {}, because a
      silent empty store would let a validated day be submitted again.

      Deliberately does NOT decide who may act, recompute the branch index, or
      apply the over-reporting gate. Authorisation is org_validator's, the index
      formula lives in the queue endpoint, and the gate is
      reconcile_branch_day's. This module records.

      Resubmitting a VALIDATED day clears its validation: the numbers changed,
      so the countersignature no longer refers to them.

  utils/org_validator.branches_validated_by(code)
      Tier-2 scope. An all-view role (MD, Head of Branches — reusing the same
      _ALL_VIEW_ROLES set the visibility engine uses) owns every branch;
      otherwise a branch belongs to whoever its Branch Manager reports to.
      Vectorised, one register pass.

  GET  /api/branch-log/branch-days?date=
      One row per branch in scope: expected / filed / validated / not filed,
      submission status, branch index, and the current over-report count.
      Branches with nobody filing still appear rather than vanishing.

  POST /api/branch-log/branch-days/submit
      Tier 1. REFUSES with 409 while any column is over-reported — "nothing
      should flow if what is being submitted is more than the actual branch
      performance" — naming the offending columns.

  POST /api/branch-log/branch-days/validate   {approved, note}
      Tier 2. approved=false returns the day to the BM and REQUIRES a note.

Verified: py_compile clean on all three modules, and the lifecycle exercised end
to end — submit, return, refusal to validate a returned day, resubmit clearing
the returned state, validate, and refusal to return without a note.

FRONTEND IS B3: the grouped branch view for tier 2, with expand-to-inspect.
The current single-branch footer in DailyLogValidation is WRONG for a
cross-branch caller (it labels every row with the first row's branch) and B3
replaces it.

Usage (from project root, .venv active):
    python scripts\\patch_b2_branch_day.py            # dry run
    python scripts\\patch_b2_branch_day.py --apply    # write + .pre_b2 backups
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "branch_day.py")
OV = os.path.join("utils", "org_validator.py")
API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_b2"

OV_ANCHOR = "def can_validate_daily_log(validator_code: str, staff_code: str) -> bool:"
API_ANCHOR = '@router.get("/validation-queue")'

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


def _key(branch: str, day: str) -> str:
    return f"{str(branch).strip()}|{str(day)[:10]}"


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


def get_branch_day(branch: str, day: str) -> Optional[dict]:
    """The submission record for one branch-day, or None."""
    return _load().get(_key(branch, day))


def list_branch_days(day: str, branches=None) -> dict:
    """{branch: record} for a date, optionally restricted to a branch list."""
    data = _load()
    want = {str(b).strip() for b in branches} if branches else None
    out = {}
    for k, rec in data.items():
        b, _, d = k.partition("|")
        if d != str(day)[:10]:
            continue
        if want is not None and b not in want:
            continue
        out[b] = rec
    return out


def submit_branch_day(branch: str, day: str, by_code: str, by_name: str,
                      branch_index: float, staff_totals: dict,
                      control_totals: dict, counts: dict) -> dict:
    """TIER 1: the Branch Manager closes the day.

    Re-submitting after a return is allowed and clears the returned state, so a
    corrected day can flow again without an admin unlock.
    """
    data = _load()
    k = _key(branch, day)
    prev = data.get(k) or {}
    now = datetime.now().isoformat()
    rec = {
        "branch": str(branch).strip(),
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
                        note: str = "") -> dict:
    """TIER 2: the Head of Branches countersigns the branch day."""
    data = _load()
    k = _key(branch, day)
    rec = data.get(k)
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
                      note: str) -> dict:
    """TIER 2: send the branch day back to the Branch Manager.

    A note is REQUIRED — a returned day with no reason leaves the BM nothing to
    act on, the same rule the individual return already enforces.
    """
    if not str(note or "").strip():
        raise ValueError("a note is required when returning a branch day")
    data = _load()
    k = _key(branch, day)
    rec = data.get(k)
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

TIER2_NEW = r'''def branches_validated_by(validator_code: str) -> dict:
    """TIER 2: which BRANCHES may this person validate (not individuals)?

    Ruling 2026-08-08: a Branch Manager validates the individuals and closes the
    branch day; the Head of Branches validates the BRANCH SUBMISSION and may
    return it to the BM. Two tiers, two different objects.

    A branch belongs to this caller when the caller is the line manager of that
    branch's triad head (its Branch Manager), or when the caller holds an
    all-view role, in which case every branch is theirs.

    Returns {"mode": "branch"|"", "branches": [name, ...], "all_view": bool}.
    Vectorised — one register pass, no per-branch resolution.
    """
    df = _register()
    vc = _s(validator_code)
    if df.empty or not vc or "Staff Code" not in df.columns:
        return {"mode": "", "branches": [], "all_view": False}

    me = df[df["Staff Code"] == vc]
    if me.empty:
        return {"mode": "", "branches": [], "all_view": False}
    my_role = _s(me.iloc[0].get("Role", "")).lower()

    if "Branch" in df.columns:
        bcol = df["Branch"].astype(str).str.strip()
        if "Unit" in df.columns:
            bcol = bcol.where(bcol.str.len() > 0, df["Unit"].astype(str).str.strip())
    else:
        bcol = df["Unit"].astype(str).str.strip()
    branch_names = sorted({b for b in bcol.tolist()
                           if b and b.lower() != _HEAD_OFFICE})

    # All-view roles (MD, Head of Branches, register roots, admins) own every
    # branch. Reuse the same sets the visibility engine uses — do not restate.
    all_view = False
    try:
        from utils.core import _ALL_VIEW_ROLES
        all_view = my_role in {r.lower() for r in _ALL_VIEW_ROLES} or "admin" in my_role
    except Exception:
        all_view = "admin" in my_role
    if all_view:
        return {"mode": "branch", "branches": branch_names, "all_view": True}

    # Otherwise: branches whose Branch Manager reports to this caller.
    if "Reports To" not in df.columns:
        return {"mode": "", "branches": [], "all_view": False}
    wanted = [w.lower() for w in _triad_roles()]
    head_role = wanted[0] if wanted else "branch manager"
    roles = df["Role"].astype(str).str.strip().str.lower()
    reports = df["Reports To"].astype(str).str.strip()
    mask = (roles == head_role) & (reports == vc)
    mine = sorted({b for b in bcol[mask].tolist() if b})
    return {"mode": "branch" if mine else "", "branches": mine, "all_view": False}


'''

ENDPOINTS_NEW = r'''@router.get("/branch-days")
def branch_log_branch_days(date: str = "", user: dict = Depends(get_current_user)):
    """TIER 2: the branches this caller countersigns, for one day.

    One row per branch: how many staff are expected, filed, validated, whether
    the Branch Manager has submitted, the branch index, and whether the
    over-reporting gate is currently breached.

    Scope comes from org_validator.branches_validated_by — an all-view role
    (MD, Head of Branches) owns every branch; otherwise a branch belongs to the
    person its Branch Manager reports to. This endpoint decides nothing.
    """
    from datetime import date as _date
    from utils.staff_code import canon as _canon_b

    me = _identity(user)
    my_code = str(me.get("staff_code", "") or "")
    try:
        day = _date.fromisoformat(str(date)[:10]) if date else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    iso = day.isoformat()

    try:
        from utils.org_validator import branches_validated_by
        scope = branches_validated_by(my_code)
    except Exception:
        scope = {"mode": "", "branches": [], "all_view": False}
    branches = scope.get("branches") or []
    if not branches:
        return {"rows": [], "date": iso, "mode": scope.get("mode", ""),
                "all_view": bool(scope.get("all_view")), "working_day": True}

    try:
        from utils import workcal as _wc
        if not _wc.is_working_day(day):
            return {"rows": [], "date": iso, "mode": scope.get("mode", ""),
                    "all_view": bool(scope.get("all_view")), "working_day": False,
                    "label": _wc.holiday_label(day)}
    except Exception:
        pass

    dims = _roster_dims()
    # Expected headcount per branch, from the roster — so a branch with nobody
    # filing still appears rather than vanishing.
    expected = {}
    for _ck, d in dims.items():
        b = str((d or {}).get("branch") or "").strip()
        if b:
            expected[b] = expected.get(b, 0) + 1

    blm = BranchLogManager()
    logs = [l for l in blm.get_history(days=45) if str(l.get("log_date"))[:10] == iso]
    by_branch_logs = {}
    for l in logs:
        d = dims.get(_canon_b(l.get("staff_code"))) or {}
        b = str(d.get("branch") or l.get("unit") or "").strip()
        by_branch_logs.setdefault(b, []).append(l)

    from utils.branch_day import list_branch_days
    subs = list_branch_days(iso, branches)

    rows = []
    for b in branches:
        blogs = by_branch_logs.get(b, [])
        filed = len(blogs)
        validated = sum(1 for l in blogs if l.get("validated"))
        rec = subs.get(b) or {}
        breaches = 0
        try:
            from utils.branch_log_reconcile import reconcile_branch_day
            breaches = int((reconcile_branch_day(logs, b, iso) or {}).get("anomaly_count", 0))
        except Exception:
            breaches = 0
        rows.append({
            "branch": b,
            "expected": expected.get(b, 0),
            "filed": filed,
            "validated": validated,
            "pending": max(filed - validated, 0),
            "not_filed": max(expected.get(b, 0) - filed, 0),
            "status": rec.get("status", "draft"),
            "branch_index": rec.get("branch_index", 0),
            "submitted_by_name": rec.get("submitted_by_name", ""),
            "submitted_at": rec.get("submitted_at", ""),
            "return_note": rec.get("return_note", ""),
            "validated_by_name": rec.get("validated_by_name", ""),
            "over_reported": breaches,
        })
    rows.sort(key=lambda r: r["branch"])
    return {"rows": rows, "date": iso, "mode": scope.get("mode", ""),
            "all_view": bool(scope.get("all_view")), "working_day": True}


@router.post("/branch-days/submit")
def branch_log_branch_day_submit(payload: dict = Body(default_factory=dict),
                                 user: dict = Depends(get_current_user)):
    """TIER 1: the Branch Manager closes the day.

    Refuses while the over-reporting gate is breached — "nothing should flow if
    what is being submitted is more than the actual branch performance".
    """
    from datetime import date as _date
    me = _identity(user)
    branch = str(payload.get("branch", "") or "").strip()
    day = str(payload.get("date") or _date.today())[:10]
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    try:
        from utils.org_validator import staff_validated_by
        scope = staff_validated_by(me.get("staff_code", ""))
    except Exception:
        scope = {"mode": "", "codes": []}
    if scope.get("mode") != "triad" and not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail="Only the branch management triad can close a branch day.")

    blm = BranchLogManager()
    logs = [l for l in blm.get_history(days=45) if str(l.get("log_date"))[:10] == day]
    try:
        from utils.branch_log_reconcile import reconcile_branch_day
        recon = reconcile_branch_day(logs, branch, day) or {}
    except Exception:
        recon = {}
    if int(recon.get("anomaly_count", 0)) > 0:
        over = [k for k, m in (recon.get("metrics") or {}).items() if m.get("anomaly")]
        raise HTTPException(
            status_code=409,
            detail="Over-reported against the branch actual: " + ", ".join(over[:6]))

    from utils.branch_day import submit_branch_day
    rec = submit_branch_day(
        branch, day, me.get("staff_code", ""), me.get("staff_name", ""),
        float(payload.get("branch_index") or 0),
        payload.get("staff_totals") or {}, payload.get("control_totals") or {},
        payload.get("counts") or {})
    audit_log("BRANCH_DAY_SUBMIT", str(user.get("username", "") or ""),
              detail=f"branch={branch} date={day} index={rec.get('branch_index')}")
    return {"branch_day": rec}


@router.post("/branch-days/validate")
def branch_log_branch_day_validate(payload: dict = Body(default_factory=dict),
                                   user: dict = Depends(get_current_user)):
    """TIER 2: countersign, or return to the Branch Manager with a reason."""
    from datetime import date as _date
    me = _identity(user)
    branch = str(payload.get("branch", "") or "").strip()
    day = str(payload.get("date") or _date.today())[:10]
    approve = bool(payload.get("approved", True))
    note = str(payload.get("note", "") or "")
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    try:
        from utils.org_validator import branches_validated_by
        scope = branches_validated_by(me.get("staff_code", ""))
    except Exception:
        scope = {"branches": []}
    if branch not in (scope.get("branches") or []) and not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail=f"{branch} is not a branch you countersign.")

    from utils.branch_day import validate_branch_day, return_branch_day
    try:
        rec = (validate_branch_day(branch, day, me.get("staff_code", ""),
                                   me.get("staff_name", ""), note)
               if approve else
               return_branch_day(branch, day, me.get("staff_code", ""),
                                 me.get("staff_name", ""), note))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    audit_log("BRANCH_DAY_VALIDATE" if approve else "BRANCH_DAY_RETURN",
              str(user.get("username", "") or ""),
              detail=f"branch={branch} date={day}")
    return {"branch_day": rec}


'''


def main():
    apply = "--apply" in sys.argv
    for p in (OV, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - B2 looks applied." % MOD)
        return 1

    ov = open(OV, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "branches_validated_by" in ov:
        print("ABORT: org_validator already has branches_validated_by.")
        return 1
    if "staff_validated_by" not in ov:
        print("ABORT: apply patch_v2a_queue_perf.py first.")
        return 1
    if "branch_index" not in api:
        print("ABORT: apply patch_b1_branch_line.py first.")
        return 1
    if ov.count(OV_ANCHOR) != 1:
        print("ABORT: org_validator anchor matched %d times." % ov.count(OV_ANCHOR))
        return 1
    if api.count(API_ANCHOR) != 1:
        print("ABORT: api_branch_log anchor matched %d times." % api.count(API_ANCHOR))
        return 1

    ov = ov.replace(OV_ANCHOR, TIER2_NEW + OV_ANCHOR, 1)
    print("  ok  org_validator - branches_validated_by (tier-2 scope)")

    api = api.replace(API_ANCHOR, ENDPOINTS_NEW + API_ANCHOR, 1)
    print("  ok  api_branch_log - GET /branch-days, POST submit, POST validate")

    for route in ('@router.get("/branch-days")',
                  '@router.post("/branch-days/submit")',
                  '@router.post("/branch-days/validate")'):
        if api.count(route) != 1:
            print("ABORT: post-check - %s appears %d times." % (route, api.count(route)))
            return 1
    if api.count('@router.get("/validation-queue")') != 1:
        print("ABORT: post-check - validation-queue route count changed.")
        return 1
    for token in ("STATUS_RETURNED", "os.replace", "a note is required"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    print("  ok  post-checks: three new routes, queue route intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    for path, content in ((OV, ov), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (MOD, OV, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn. B3 (the grouped branch view) is the frontend half.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
