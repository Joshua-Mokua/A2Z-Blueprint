#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RC2 - a referral carries the customer type the officer chose.

FROM THE PILOT (2026-09-04), from Alex's run of diag_why_unclassified:

    NO SEGMENT - no segment analyst owns it: 33
       client types: Existing=33 (all of them)

EVERY ONE. And "Existing" is not a customer type at all - it is a RELATIONSHIP
STATUS, the answer to "new to bank or existing?". The customer type is Consumer,
Commercial or CIB, and _app_segment reads it to decide which analyst owns a
case. "Existing" matches none of them, so a referred deal reaches no segment
analyst.

WHERE IT COMES FROM. The refer endpoint hardcodes it:

    referral_record = {
        ...
        "client_type":  "Existing",

That was copied from the Streamlit page it replaced, where it meant "this is an
existing customer" - a different field that happened to share a name.

THE OFFICER ALREADY ANSWERS THIS. The refer form shows a Customer type
dropdown and the officer fills it in. The value is simply never sent: it is not
on ReferDealRequest, and the server would ignore it if it were.

WHAT THIS CHANGES:

    the payload accepts client_type      optional - the refer form asks for
                                         the minimum, and this stays optional
    the frontend sends what was chosen
    the server uses it, and writes ""    NOT "Existing" - a blank is honest
       when nothing was chosen           about being unknown, whereas a wrong
                                         value looks like data and silently
                                         routes the case to nobody

THE 33 EXISTING DEALS ARE NOT FIXED BY THIS. They carry the wrong value
already; this stops the next one. Correcting them is a separate, deliberate
pass - and it needs a person to say what each of them actually is.

Usage (from project root, .venv active):
    python scripts\patch_rc2_referral_carries_client_type.py            # dry run
    python scripts\patch_rc2_referral_carries_client_type.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
MODEL = os.path.join("utils", "api_pipeline_models.py")
FORM = os.path.join("frontend", "web", "src", "pages", "PipelineCreate.tsx")
CLIENT = os.path.join("frontend", "web", "src", "lib", "api.ts")

API_OLD = '''        "client_type":          "Existing",'''
API_NEW = '''        # ── NOT "Existing" ──────────────────────────────────────────────
        # "Existing" is a RELATIONSHIP STATUS, not a customer type. It was
        # copied from the Streamlit page this replaced, where it meant "this
        # is an existing customer" - a different field that happened to share
        # a name.
        #
        # _app_segment reads client_type to decide which analyst owns a case,
        # and "Existing" matches none of Consumer / Commercial / CIB. Every
        # one of the pilot's 33 unsegmented deals carried it.
        #
        # A BLANK IS HONEST ABOUT BEING UNKNOWN. A wrong value looks like data
        # and silently routes the case to nobody.
        "client_type":          str(getattr(payload, "client_type", "") or ""),'''

# Anchored on the CLASS, not on client_name - two models declare a client_name
# and the patch must not land in the wrong one.
# Anchored on a line INSIDE the class body - two models declare a client_name,
# and anchoring on the class name put the field above the docstring, which is a
# stray expression rather than a field.
MODEL_OLD = '''    client_name: str = Field(description="Customer display name")
    staff_code: Optional[str] = Field('''
MODEL_NEW = '''    client_name: str = Field(description="Customer display name")
    # Optional: the refer form asks for the minimum, and the recipient
    # completes the deal on acceptance. But when the officer HAS chosen a
    # customer type it must reach the record - it decides which segment
    # analyst owns the case, and the endpoint used to overwrite it with
    # "Existing", which is a relationship status and matches no segment.
    client_type: Optional[str] = Field(
        default=None, description="Consumer / Commercial / CIB, when known")
    staff_code: Optional[str] = Field('''

FORM_OLD = '''        account_number:        accountNumber.trim() || undefined,'''
FORM_NEW = '''        account_number:        accountNumber.trim() || undefined,
        // The officer answers "Customer type" on this form. It used to be
        // discarded here and the server wrote "Existing" - a relationship
        // status - so no segment analyst ever owned a referred deal.
        client_type:           clientType || undefined,'''

TYPES = os.path.join("frontend", "web", "src", "types", "pipeline.ts")

# The interface has to accept the field or tsc refuses the object literal.
TYPES_OLD = '''  // Optional
  referral_note?:         string;
  account_number?:        string;
  unit?:                  string;
}'''
TYPES_NEW = '''  // Optional
  referral_note?:         string;
  account_number?:        string;
  unit?:                  string;
  // The customer type the officer chose on the refer form. Optional, because
  // the refer form asks for the minimum - but when it IS chosen it must reach
  // the record: the endpoint used to overwrite it with "Existing", which is a
  // relationship status and matches no segment, so no analyst owned the case.
  client_type?:           string;
}'''


def main():
    apply = "--apply" in sys.argv
    for f in (API, MODEL, FORM, TYPES):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    a = open(API, encoding="utf-8").read()
    m = open(MODEL, encoding="utf-8").read()
    f = open(FORM, encoding="utf-8").read()
    t = open(TYPES, encoding="utf-8").read()

    if 'NOT "Existing"' in a:
        print("ABORT: RC2 looks applied.")
        return 1
    for nm, src, anchor in (("the hardcoded client_type", a, API_OLD),
                            ("the refer model", m, MODEL_OLD),
                            ("the refer body", f, FORM_OLD),
                            ("the refer interface", t, TYPES_OLD)):
        if src.count(anchor) != 1:
            print("ABORT: %s matched %d times." % (nm, src.count(anchor)))
            return 1
    if "Optional" not in m.split("class PipelineDealRefer")[0][-4000:]:
        print("ABORT: Optional is not imported in the models module.")
        return 1

    a = a.replace(API_OLD, API_NEW, 1)
    m = m.replace(MODEL_OLD, MODEL_NEW, 1)
    f = f.replace(FORM_OLD, FORM_NEW, 1)
    t = t.replace(TYPES_OLD, TYPES_NEW, 1)
    print("  ok  a referral carries the customer type that was chosen")

    if '"Existing"' in API_NEW.split("client_type\":")[-1]:
        print("ABORT: the hardcoded value survives.")
        return 1
    if 'or ""' not in API_NEW:
        print("ABORT: an unknown type must be blank, not a guess.")
        return 1
    import ast
    for path, src in ((API, a), (MODEL, m)):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            print("ABORT: %s would not parse - line %s"
                  % (os.path.basename(path), exc.lineno))
            return 1
    if f.count("{") != f.count("}") or f.count("(") != f.count(")"):
        print("ABORT: the form's braces are unbalanced.")
        return 1
    print("  ok  post-checks: no hardcode, blank when unknown, parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, src in ((API, a), (MODEL, m), (FORM, f), (TYPES, t)):
        shutil.copy2(path, path + ".pre_rc2")
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)

    import py_compile
    for path in (API, MODEL):
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:
            print("  FAIL %s: %s" % (os.path.basename(path), exc))
            return 1
    print("  ok  compiles")
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
