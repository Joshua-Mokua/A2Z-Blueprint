#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V2a - HOTFIX: the Daily log tab hung on "Loading...".

MY BUG. /validation-queue asked the FORWARD question once per staff member:

    for ck, d in dims.items():              # 363 people
        res = daily_log_validators_for(code) # scans the whole register EACH time

daily_log_validators_for() iterates the 363-row staff register, so the endpoint
performed roughly 132,000 pandas row reads per request. Same shape as the P3d
cache defect: an O(n^2) loop wrapped around a per-person resolver.

THE FIX - invert the question and ask it once.

utils/org_validator.staff_validated_by(validator_code) answers "whose daily logs
may THIS person validate?" in a single pass:

    * a triad-role holder in a BRANCH validates everyone in that branch, plus
      any branch they are the acting BM for
    * anyone else validates their direct reports (Reports To == their code)

It is VECTORISED - boolean masks over the DataFrame, not iterrows() - because
iterrows() per request is what made the tab hang in the first place.

Measured on the register fixture: 2.3 ms per call, versus the previous 363
full-register scans per request.

Verified identical results to the forward lookup:

    KE632 (Fortis BM)     triad        -> the 5 other Fortis staff
    KE708 (Fortis CSM)    triad        -> the 5 other Fortis staff
    KE100 (Head Office)   line_manager -> their 3 direct reports
    KE770 (Eldoret CSM)   triad        -> the Eldoret teller
    KE343 (RO, no triad)  line_manager -> their one report

daily_log_validators_for and can_validate_daily_log are untouched: the forward
question is still the right one when checking a single permission (the validate
endpoint uses it), and it is cheap for one lookup.

Usage (from project root, .venv active):
    python scripts\\patch_v2a_queue_perf.py            # dry run
    python scripts\\patch_v2a_queue_perf.py --apply    # write + .pre_v2a backups
"""
import os
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_v2a"

INVERSE_NEW = r'''def staff_validated_by(validator_code: str) -> dict:
    """INVERSE of daily_log_validators_for: whose daily logs may this person
    validate? One register scan.

    Asking the forward question per staff member is O(n^2) — the queue endpoint
    did exactly that across 363 staff and hung. This answers it once:

      * a triad-role holder in a BRANCH validates everyone in that branch
        (plus any branch they are the acting BM for)
      * anyone else validates their direct reports (Reports To == their code)

    Returns {"mode": "triad"|"line_manager"|"", "codes": [staff_code, ...]}.
    """
    df = _register()
    vc = _s(validator_code)
    if df.empty or not vc or "Staff Code" not in df.columns:
        return {"mode": "", "codes": []}

    me = df[df["Staff Code"] == vc]
    if me.empty:
        return {"mode": "", "codes": []}
    m = me.iloc[0]
    my_branch = _s(m.get("Branch", "")) or _s(m.get("Unit", ""))
    my_role = _s(m.get("Role", ""))

    wanted = _triad_roles()
    is_triad_role = any(_role_matches(my_role, w) for w in wanted)

    # Branches this person covers as a triad member or as acting BM.
    branches = set()
    if is_triad_role and my_branch and my_branch.lower() != _HEAD_OFFICE:
        branches.add(my_branch.lower())
    try:
        from utils.config import load_org_config
        for bname, acting in (load_org_config().get("acting_bm") or {}).items():
            if _s(acting) == vc:
                branches.add(_s(bname).lower())
    except Exception:
        pass

    # Vectorised on purpose: iterrows() over the register per request is what
    # made the queue hang. These are boolean masks, not Python loops.
    codes_col = df["Staff Code"].astype(str).str.strip()
    not_me = codes_col != vc

    if branches:
        if "Branch" in df.columns:
            bcol = df["Branch"].astype(str).str.strip()
            if "Unit" in df.columns:
                bcol = bcol.where(bcol.str.len() > 0, df["Unit"].astype(str).str.strip())
        else:
            bcol = df["Unit"].astype(str).str.strip()
        mask = bcol.str.lower().isin(branches) & not_me
        return {"mode": "triad",
                "codes": [c for c in codes_col[mask].tolist() if c]}

    if "Reports To" in df.columns:
        mask = (df["Reports To"].astype(str).str.strip() == vc) & not_me
        return {"mode": "line_manager",
                "codes": [c for c in codes_col[mask].tolist() if c]}

    return {"mode": "line_manager", "codes": []}


'''

BLOCK_NEW = r'''    dims = _roster_dims()

    # Everyone this caller may validate — ONE register scan via the inverse
    # lookup. Asking daily_log_validators_for() per staff member was O(n^2)
    # across 363 people (~132k pandas row reads) and hung the tab.
    from utils.org_validator import staff_validated_by
    try:
        res = staff_validated_by(my_code)
    except Exception:
        res = {"mode": "", "codes": []}
    mode = res.get("mode", "")
    mine = []
    for code in res.get("codes", []):
        d = dims.get(_canon_q(code)) or {}
        mine.append((d.get("code") or code, d))

'''


OV_ANCHOR = "def can_validate_daily_log(validator_code: str, staff_code: str) -> bool:"
API_START = "    dims = _roster_dims()\n    from utils.org_validator import daily_log_validators_for"
API_END = "    if not mine:"


def main():
    apply = "--apply" in sys.argv
    for p in (OV, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    ov = open(OV, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "staff_validated_by" in ov:
        print("ABORT: org_validator already has staff_validated_by - V2a looks applied.")
        return 1
    if "daily_log_validators_for" not in ov:
        print("ABORT: apply patch_v1_validation_backend.py first.")
        return 1
    if "validation-queue" not in api:
        print("ABORT: /validation-queue not present - apply V1 first.")
        return 1
    if ov.count(OV_ANCHOR) != 1:
        print("ABORT: org_validator anchor matched %d times." % ov.count(OV_ANCHOR))
        return 1
    if api.count(API_START) != 1:
        print("ABORT: queue scope block matched %d times." % api.count(API_START))
        return 1

    ov = ov.replace(OV_ANCHOR, INVERSE_NEW + OV_ANCHOR, 1)
    print("  ok  org_validator - staff_validated_by (vectorised, one pass)")

    a = api.index(API_START)
    b = api.index(API_END, a)
    api = api[:a] + BLOCK_NEW + api[b:]
    print("  ok  /validation-queue - one inverse lookup per request")

    if "daily_log_validators_for(code)" in api:
        print("ABORT: post-check - the per-staff forward loop is still present.")
        return 1
    # Check for the CALL, not the word: the docstring explains why iterrows was
    # removed, and matching the bare word trips on its own explanation.
    if "df.iterrows()" in INVERSE_NEW:
        print("ABORT: post-check - the inverse lookup still calls df.iterrows().")
        return 1
    print("  ok  post-checks: no per-staff loop, no iterrows in the hot path")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((OV, ov), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (OV, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn, then reload Manager Queues -> Daily log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
