#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Two faults from the same root: a returned deal cannot resubmit, and the
credit desks cannot see documents attached after submission.

1. RESUBMIT. The submit gate requires the deal to be at its document stage
   exactly:  stage_ok = (current_stage == doc_stage). A return freezes the
   deal at Rework - which is not the document stage - so the owner attaches
   what was asked and Submit stays blocked. Rework is now accepted as a valid
   place to submit from.

2. DOCUMENTS. The case document list returns app["documents_provided"], a copy
   taken at submit time. Documents the analyst or credit risk attach to the
   deal afterwards never reach the case's copy, so the committee cannot see
   them. The list now reads the live documents from the deal.

    python scripts/patch_fx1_resubmit_and_documents.py            # dry run
    python scripts/patch_fx1_resubmit_and_documents.py --apply
"""
import os
import re
import shutil
import sys

API = os.path.join("utils", "api.py")
LMS = os.path.join("utils", "api_lms_routes.py")

# ── 1. the submit gate accepts Rework ──
OLD_GATE = '''        stage_required = doc_stage
        stage_ok = (current_stage == doc_stage)'''
NEW_GATE = '''        stage_required = doc_stage
        # Rework is where a returned deal is frozen. Submitting from there is a
        # resubmission - the same act as submitting from the document stage, so
        # it is allowed. Without this a returned deal could never resubmit.
        stage_ok = (current_stage == doc_stage
                    or str(current_stage).strip().lower() == "rework")'''

# ── 2. the case document list reads the deal's live documents ──
OLD_LIST = '''    return {"required": _required,'''
NEW_LIST = '''    # The documents that are actually on the deal now - not the copy taken at
    # submit time. An analyst or credit risk who attaches a file after
    # submission must be visible to the committee that reviews it.
    _provided = list(app.get("documents_provided", []) or [])
    try:
        _did = str(app.get("pipeline_deal_id") or "").strip()
        if _did:
            from utils.core import PipelineManager as _PM_docs
            _d = _PM_docs().get_deal(_did) or {}
            _live = list(_d.get("documents_provided", []) or [])
            _seen = {str(x.get("name") if isinstance(x, dict) else x) for x in _provided}
            for _f in _live:
                _key = str(_f.get("name") if isinstance(_f, dict) else _f)
                if _key and _key not in _seen:
                    _provided.append(_f)
                    _seen.add(_key)
    except Exception:
        pass
    return {"required": _required,'''

OLD_RET = '''            "provided": list(app.get("documents_provided", []) or []),'''
NEW_RET = '''            "provided": _provided,'''


def main():
    apply = "--apply" in sys.argv
    for f in (API, LMS):
        if not os.path.isfile(f):
            print("%s not found." % f)
            return 1
    api = open(API, encoding="utf-8").read()
    lms = open(LMS, encoding="utf-8").read()

    done = []
    # gate
    if 'str(current_stage).strip().lower() == "rework"' in api:
        print("  resubmit gate: already fixed")
    elif api.count(OLD_GATE) == 1:
        api = api.replace(OLD_GATE, NEW_GATE, 1); done.append("resubmit gate accepts Rework")
    else:
        print("  resubmit gate matched %d times - not applying." % api.count(OLD_GATE)); return 1
    # list
    if "the documents that are actually on the deal now" in lms.lower():
        print("  document list: already fixed")
    elif lms.count(OLD_RET) == 1 and lms.count(OLD_LIST) >= 1:
        # insert the live-doc computation before the documents_list return only
        i = lms.index("def lms_application_documents_list")
        j = lms.index(chr(10)+"@router.", i+10)
        block = lms[i:j]
        block2 = block.replace(OLD_LIST, NEW_LIST, 1).replace(OLD_RET, NEW_RET, 1)
        lms = lms[:i] + block2 + lms[j:]
        done.append("case document list reads the deal's live files")
    else:
        print("  document return matched %d times - not applying." % lms.count(OLD_RET)); return 1

    if not done:
        print("Both already applied.")
        return 0
    for d in done:
        print("  fixed  %s" % d)

    import ast
    for name, src in ((API, api), (LMS, lms)):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            print("%s would not parse - line %s: %s" % (name, exc.lineno, exc.msg)); return 1

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0
    for path, src in ((API, api), (LMS, lms)):
        if src != open(path, encoding="utf-8").read():
            shutil.copy2(path, path + ".pre_fx1")
            open(path, "w", encoding="utf-8", newline="").write(src)
            print("Applied %s" % path)
    import py_compile
    py_compile.compile(API, doraise=True); py_compile.compile(LMS, doraise=True)
    print("Both compile.")
    print("\nRestart uvicorn. Deals already stuck at Rework can now resubmit;")
    print("documents attached after submission are now visible to the committee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
