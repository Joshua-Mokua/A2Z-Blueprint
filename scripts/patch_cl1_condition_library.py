#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CL1 - the condition library is the bank's, not the developer's.

RULING (2026-08-18): "the items we listed in the pre-approval and
pre-disbursement conditions can now be added to the admin config. We can
maintain those as they are, but the admin should be able to amend and add to
suit the bank's terminologies without seeming like we are introducing new
concepts. They should be configured and not hard-coded."

The reason matters more than the mechanism. A list written into the software is
a DEVELOPER'S GUESS at a bank's credit policy. Worded differently from the
credit manual it makes the system look as though it is inventing terms, and
nobody can correct it without a release. I wrote 33 pre-approval conditions
from general knowledge; the bank has its own wording and should use it.

    GET  /api/lms/config/conditions    anybody signed in - an analyst needs
                                       the list to tick from
    POST /api/lms/config/conditions    config admin only

`configured` tells the screen whether the bank has worded its own yet. Until it
has, the analyst still sees the built-in set - the system is usable on day one -
but ADMINISTRATION SAYS PLAINLY that it is a starting set and not the bank's.
Presenting a guess as policy is how a system loses the room.

TWO THINGS THE WRITE REFUSES:

  AN EMPTY LIST OVER A POPULATED ONE. Clearing every condition is almost always
  an accident - a paste gone wrong, a form submitted before it loaded - and the
  cost of being wrong is an approval carrying no conditions at all. Removing
  them one at a time is still allowed.

  DUPLICATES AND BLANK LINES, silently dropped. A list edited by hand collects
  both, and a duplicate condition is ticked twice and reported once.

Backup-before-mutation and an atomic write, the same as every other config
write here: a half-written credit policy is worse than none.

Verified: py_compile clean; dedupe, blank-stripping and the clear-guard driven.

Usage (from project root, .venv active):
    python scripts\\patch_cl1_condition_library.py            # dry run
    python scripts\\patch_cl1_condition_library.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_cl1"

ANCHOR = '@router.get("/config/pool-visibility")'

BLOCK = r'''@router.get("/config/conditions")
def lms_conditions_get(user: dict = Depends(get_current_user)):
    """The condition library, worded as the bank words it.

    RULING (2026-08-18): "the items we listed in the pre-approval and
    pre-disbursement conditions can now be added to the admin config ... the
    admin should be able to amend and add to suit the bank\u2019s terminologies
    without seeming like we are introducing new concepts. They should be
    configured and not hard-coded."

    The reason matters more than the mechanism. A list written into the
    software is a developer\u2019s guess at a bank\u2019s credit policy. Worded
    differently from the credit manual it makes the system look as though it is
    inventing terms, and nobody can correct it without a release.

    ANYBODY SIGNED IN MAY READ IT - an analyst needs the list to tick from.
    Only a config admin may change it.

    `configured` tells the screen whether the bank has worded its own yet, so
    it can fall back to the built-in set WITHOUT presenting it as the bank\u2019s.
    """
    from pathlib import Path as _Path
    import json as _json
    lib = {}
    try:
        _p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
        if _p.exists():
            _cfg = _json.loads(_p.read_text(encoding="utf-8"))
            lib = (_cfg or {}).get("condition_library") or {}
    except Exception:
        lib = {}
    return {
        "pre_approval": list(lib.get("pre_approval") or []),
        "pre_disbursement": list(lib.get("pre_disbursement") or []),
        "configured": bool(lib.get("pre_approval") or lib.get("pre_disbursement")),
    }


@router.post("/config/conditions")
def lms_conditions_set(
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(require_config_admin),
):
    """Replace one or both condition lists. Config admin only.

    Whichever list is supplied is replaced entirely; the other is untouched.
    Blank lines and duplicates are dropped, because a list edited by hand
    collects both - and a duplicate condition is ticked twice and reported
    once.

    IT REFUSES TO WRITE AN EMPTY LIST OVER A POPULATED ONE. Clearing every
    condition is almost always an accident - a paste gone wrong, a form
    submitted before it loaded - and the cost of being wrong is an approval
    that carries no conditions at all.
    """
    import json as _json, os as _os, tempfile as _tempfile
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
    try:
        cfg = _json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    lib = cfg.get("condition_library")
    if not isinstance(lib, dict):
        lib = {}

    touched = []
    for key in ("pre_approval", "pre_disbursement"):
        if key not in payload:
            continue
        incoming = payload.get(key)
        if not isinstance(incoming, list) or not all(isinstance(x, str) for x in incoming):
            raise HTTPException(status_code=400,
                                detail=f"{key} must be a list of strings")
        seen, clean = set(), []
        for x in incoming:
            t = str(x).strip()
            k = t.lower()
            if t and k not in seen:
                seen.add(k)
                clean.append(t)
        if not clean and (lib.get(key) or []):
            raise HTTPException(
                status_code=400,
                detail=("Refusing to clear every %s condition at once. If that "
                        "is really intended, remove them one at a time."
                        % key.replace("_", "-")))
        lib[key] = clean
        touched.append(key)
    if not touched:
        raise HTTPException(status_code=400,
                            detail="Provide pre_approval and/or pre_disbursement")
    cfg["condition_library"] = lib

    # Backup-before-mutation + atomic write, the same as every other config
    # write here. A half-written credit policy is worse than none.
    try:
        if p.exists():
            backup = p.with_suffix(f".pre_conditions_{_dt.now():%Y%m%d-%H%M%S}.json")
            backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        fd, tmp = _tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with _os.fdopen(fd, "w", encoding="utf-8") as fh:
            _json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.flush()
            _os.fsync(fh.fileno())
        _os.replace(tmp, str(p))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save config: {e}")

    audit_log("LMS_CONDITIONS_SET", str(user.get("username", "") or ""),
              "pre_approval=%d pre_disbursement=%d"
              % (len(lib.get("pre_approval") or []),
                 len(lib.get("pre_disbursement") or [])))
    return {"pre_approval": list(lib.get("pre_approval") or []),
            "pre_disbursement": list(lib.get("pre_disbursement") or []),
            "configured": True}


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "/config/conditions" in s:
        print("ABORT: CL1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the pool-visibility route matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  the condition library can be read and configured")

    if "require_config_admin" not in BLOCK:
        print("ABORT: anybody could rewrite the bank's credit conditions.")
        return 1
    if "Refusing to clear every" not in BLOCK:
        print("ABORT: one bad paste could clear every condition, and an")
        print("       approval would carry none.")
        return 1
    if "_tempfile" not in BLOCK or "backup" not in BLOCK:
        print("ABORT: no atomic write or backup - a half-written credit policy")
        print("       is worse than none.")
        return 1
    if "configured" not in BLOCK:
        print("ABORT: the screen could not tell a built-in starting set from")
        print("       the bank's own, and would present a guess as policy.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: admin only, refuses a wipe, atomic, honest")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(ROUTES, ROUTES + BACKUP_SUFFIX)
    open(ROUTES, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % ROUTES)

    import py_compile
    try:
        py_compile.compile(ROUTES, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN, then rebuild the frontend (UI3 carries the panel).")
    print("Administration > Credit Conditions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
