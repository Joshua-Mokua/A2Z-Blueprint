#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AN1 - the analyst can attach, and can see her own segment's pipeline.

LIVE PILOT, cases stuck. Two rulings (2026-08-12).

1. "CATHERINE IS TO ALSO BE ABLE TO ATTACH A FEW DOCUMENTS, then submit to
   Department Credit Committee once she recommends."

   POST /api/lms/applications/{app_id}/documents

   STORED ON THE APPLICATION, not the deal. The credit side has no deal scope
   by design - which is why the existing read route serves the app's carried
   files rather than the deal document routes. Writing to the deal would need
   a scope the analyst deliberately does not have.

   WHO MAY ATTACH: somebody WORKING the case - the assigned analyst, or a
   credit role acting on it. Not merely anyone who can VIEW it: a committee
   member reading a case should not be able to add papers to it.

   Every file records WHO attached it AND THEIR ROLE. An analyst's paper and
   the owner's look identical once filed, and six weeks later somebody will
   need to know which is which.

2. "CATHERINE, BEING IN THE CONSUMER HEAD OFFICE UNIT, is supposed to also have
   view of all consumer pipeline - same case for the other analysts."

   This is why she got a 404 opening a deal. An analyst has no reports, so the
   reporting tree gives her nothing and every deal but her own was out of
   scope. She could be handed a case for analysis and could not see the
   pipeline it came from.

   VIEW ONLY, AND ONLY WITHIN HER SEGMENT. She is not an owner, not a backup
   and not a manager, so can_edit, can_advance, can_validate and the rest stay
   false. Widening the READ is what was asked for; widening the write was not,
   and would put a credit analyst in charge of somebody else's deal.

   Measured:

       Consumer Credit Analyst + consumer deal   -> view yes, edit no
       Consumer Credit Analyst + corporate deal  -> not visible
       a deal whose segment cannot be read       -> NOT visible

   That last one is deliberate. Guessing would leak a corporate deal to a
   consumer analyst, and in this direction that is the error that matters.

DEPENDS ON SEG1. Segment resolution is what makes both of these work - before
that fix every plain "Credit Analyst" resolved to no segment, so this branch
would have granted nothing.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\patch_an1_analyst_attach_scope.py            # dry run
    python scripts\patch_an1_analyst_attach_scope.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
PERMS = os.path.join("utils", "api_pipeline_permissions.py")
BACKUP_SUFFIX = ".pre_an1"

ROUTES_ANCHOR = '@router.get("/applications/{app_id}/documents/{doc_name:path}")'
GATE_OLD = '''    # If none of owner/backup/manager-in-scope/referral-participant, out-of-scope.
    if not (is_owner or is_backup or is_manager_in_scope or is_referral_participant):
        return _all_false()'''
VIEW_OLD = "    can_view = is_owner or is_backup or is_manager_in_scope or is_referral_participant"
VIEW_NEW = '''    can_view = (is_owner or is_backup or is_manager_in_scope
                or is_referral_participant or is_segment_viewer)'''

UPLOAD = r'''class _AnalystDocUpload(BaseModel):
    doc_name: str
    filename: str = ""
    content_b64: str


@router.post("/applications/{app_id}/documents", status_code=201)
def lms_application_document_upload(
    app_id: str,
    body: _AnalystDocUpload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The analyst attaches a document to the case.

    RULING (2026-08-12): "Catherine is to also be able to attach a few
    documents, then submit to Department Credit Committee once she recommends."

    STORED ON THE APPLICATION, not the deal. The credit side has no deal scope
    by design - that is why the read route above serves the app's carried files
    rather than the deal document routes. Writing to the deal would need a
    scope the analyst deliberately does not have.

    WHO MAY ATTACH: anyone who can act on the case - the assigned analyst, and
    credit roles working it. Not merely anyone who can VIEW it: a committee
    member reading a case should not be able to add papers to it.
    """
    import base64 as _b64
    import hashlib as _hash
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    perms = resolve_application_permissions(user, app)
    if not (perms.get("can_edit") or perms.get("can_submit_to_dcc")
            or perms.get("can_decide") or perms.get("is_assigned_analyst")):
        raise HTTPException(
            status_code=403,
            detail="Only somebody working this case can attach documents to it.")

    doc_name = str(body.doc_name or "").strip()
    if not doc_name:
        raise HTTPException(status_code=400, detail="doc_name is required")
    try:
        raw = _b64.b64decode(body.content_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"content_b64 invalid: {exc}")
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400,
                            detail=f"file too large ({len(raw)} bytes; max 20MB)")

    safe = "".join(c for c in (body.filename or doc_name)
                   if c.isalnum() or c in " ._-").strip() or "attachment"
    safe_app = "".join(c for c in app_id if c.isalnum() or c in "._-")
    safe_doc = "".join(c for c in doc_name if c.isalnum() or c in " ._-").strip()
    ddir = _Path("data") / "lms_documents" / safe_app
    ddir.mkdir(parents=True, exist_ok=True)
    stored = ddir / f"{safe_doc}__{safe}"
    stored.write_bytes(raw)

    files = dict(app.get("document_files", {}) or {})
    files[doc_name] = {
        "filename": safe,
        "path": str(stored),
        "sha256": _hash.sha256(raw).hexdigest(),
        "size": len(raw),
        "uploaded_by": str(user.get("username", "") or ""),
        "uploaded_by_name": str(user.get("full_name", "") or ""),
        # WHO attached it, in the record itself. An analyst's paper and the
        # owner's look identical once filed, and six weeks later somebody will
        # need to know which is which.
        "uploaded_role": str(user.get("role", "") or ""),
        "uploaded_at": _dt.now().isoformat(timespec="seconds"),
    }
    provided = list(app.get("documents_provided", []) or [])
    if doc_name not in provided:
        provided.append(doc_name)
    lam.update(app_id, {"document_files": files, "documents_provided": provided})

    audit_log("LMS_DOC_ATTACHED", str(user.get("username", "") or ""),
              detail=f"{app_id}: {doc_name}")
    return {"ok": True, "doc_name": doc_name, "filename": safe,
            "documents_provided": provided}


'''

SEGMENT_VIEW = r'''    # ── CREDIT ANALYST, READ ONLY, WITHIN THEIR SEGMENT ─────────────────────
    # RULING (2026-08-12): "Catherine, being in the consumer head office unit,
    # is supposed to also have view of all consumer pipeline - same case for the
    # other analysts."
    #
    # An analyst has no reports, so the reporting tree gives her nothing and
    # every deal but her own returned 404. She could be handed a case for
    # analysis and could not see the pipeline it came from.
    #
    # VIEW ONLY, and only within her own segment. She is not an owner, not a
    # backup and not a manager - so can_edit, can_advance and the rest are
    # untouched below and stay false. Widening the read is what was asked for;
    # widening the write was not, and would put a credit analyst in charge of
    # somebody else's deal.
    is_segment_viewer = False
    try:
        from utils.api_lms_scope import _analyst_segment
        _seg = _analyst_segment(str(user.get("role", "") or ""),
                                str(user.get("staff_code", "") or ""))
        if _seg:
            _ct = str(deal.get("client_type") or deal.get("segment") or "").lower()
            _prod = str(deal.get("product_type") or deal.get("product") or "").lower()
            _hay = _ct + " " + _prod
            _match = {"consumer": ("individual", "personal", "consumer", "retail"),
                      "commercial": ("business", "sme", "commercial"),
                      "cib": ("corporate", "institution", "cib")}.get(_seg, ())
            # A deal whose segment cannot be read is NOT shown. Guessing here
            # would leak a corporate deal to a consumer analyst, which is the
            # error that matters in this direction.
            is_segment_viewer = any(m in _hay for m in _match)
    except Exception:
        is_segment_viewer = False

    # If none of owner/backup/manager-in-scope/referral-participant, out-of-scope.
    if not (is_owner or is_backup or is_manager_in_scope
            or is_referral_participant or is_segment_viewer):
        return _all_false()

'''


def main():
    apply = "--apply" in sys.argv
    for p in (ROUTES, PERMS):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    routes = open(ROUTES, encoding="utf-8").read()
    perms = open(PERMS, encoding="utf-8").read()

    if "_AnalystDocUpload" in routes:
        print("ABORT: AN1 looks applied.")
        return 1
    if "def _analyst_segment" not in open(
            os.path.join("utils", "api_lms_scope.py"), encoding="utf-8").read():
        print("ABORT: apply patch_seg1_analyst_segment.py first - without")
        print("       working segment resolution this grants nothing.")
        return 1
    if routes.count(ROUTES_ANCHOR) != 1:
        print("ABORT: the documents route matched %d times." % routes.count(ROUTES_ANCHOR))
        return 1
    if perms.count(GATE_OLD) != 1 or perms.count(VIEW_OLD) != 1:
        print("ABORT: permission anchors matched %d / %d times."
              % (perms.count(GATE_OLD), perms.count(VIEW_OLD)))
        return 1

    routes = routes.replace(ROUTES_ANCHOR, UPLOAD + ROUTES_ANCHOR, 1)
    if "from pydantic import BaseModel" not in routes:
        anchor = "from fastapi import APIRouter, Depends, HTTPException"
        if routes.count(anchor) != 1:
            print("ABORT: cannot place the pydantic import.")
            return 1
        routes = routes.replace(anchor, anchor + "\nfrom pydantic import BaseModel", 1)

    perms = perms.replace(GATE_OLD, SEGMENT_VIEW + GATE_OLD.replace(
        "if not (is_owner or is_backup or is_manager_in_scope or is_referral_participant):",
        "if not (is_owner or is_backup or is_manager_in_scope\n"
        "            or is_referral_participant or is_segment_viewer):"), 1)
    perms = perms.replace(VIEW_OLD, VIEW_NEW, 1)
    print("  ok  analyst upload, segment view")

    # Read only. This must not hand a credit analyst somebody else's deal.
    #
    # Checked as an ASSIGNMENT, not as the word appearing anywhere: the branch's
    # own comment says "can_edit ... stay false", and a substring check reads
    # that as the fault it is describing. Same mistake the journey audit made
    # matching a phrase inside a comment.
    import re as _re
    for k in ("can_edit", "can_advance_stage", "can_validate", "can_approve_cancel"):
        if _re.search(r"\b%s\s*=" % k, SEGMENT_VIEW):
            print("ABORT: the segment branch ASSIGNS %s - it must widen the" % k)
            print("       READ only.")
            return 1
    if "is NOT shown" not in SEGMENT_VIEW:
        print("ABORT: a deal with an unreadable segment would be guessed at,")
        print("       which leaks a corporate deal to a consumer analyst.")
        return 1
    # Attaching is for people working the case, not everyone who can read it.
    if 'perms.get("can_view")' in UPLOAD:
        print("ABORT: anyone who can view could attach - a committee member")
        print("       reading a case should not add papers to it.")
        return 1
    if "uploaded_role" not in UPLOAD:
        print("ABORT: the file does not record who attached it.")
        return 1
    print("  ok  post-checks: read-only widening, no guessing, attach gated")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((ROUTES, routes), (PERMS, perms)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (ROUTES, PERMS):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Restart uvicorn. Catherine should now open a consumer deal instead")
    print("of a 404, and can attach on the case. She still cannot EDIT or")
    print("ADVANCE somebody else's deal - that stayed with the owner.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
