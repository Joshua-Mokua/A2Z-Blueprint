#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Clicking a funnel row opens the deals in it, not only the exact stage name.

The funnel row is a BUCKET. Credit Analysis counts deals at "Credit Analysis",
"Credit Analysis & Assesment", "Credit Analyst & Assesment" - whatever the
bucket names.

The drill matched the label exactly:

    if stage and d.get("stage") != stage:
        return False

So a row showing 11 opened to fewer, or to nothing, and the click looked dead.

Now it matches any stage the bucket contains, falling back to the exact match
when the label is not a bucket.

    python scripts/patch_fd1_drill_matches_the_bucket.py            # dry run
    python scripts/patch_fd1_drill_matches_the_bucket.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''        if stage and d.get("stage") != stage:
            return False'''

NEW = '''        # ── THE ROW IS A BUCKET, NOT A STAGE ──────────────────────────
        # Credit Analysis counts deals at several stage names. Matching the
        # label exactly opened a row of 11 to nothing, and the click looked
        # dead. Falls back to the exact match when the label names no bucket.
        if stage:
            _in_bucket = _stages_in_bucket(stage)
            if _in_bucket:
                if str(d.get("stage") or "") not in _in_bucket:
                    return False
            elif d.get("stage") != stage:
                return False'''

HELPER_ANCHOR = "def pipeline_funnel_drill"

HELPER = '''def _stages_in_bucket(label: str) -> set:
    """Every stage name a funnel bucket counts, by its label.

    Empty when the label names no bucket - the caller then matches the stage
    exactly, which is what it always did.
    """
    want = str(label or "").strip().lower()
    if not want:
        return set()
    out = set()
    try:
        from utils.core import get_pipeline_settings
        cfg = get_pipeline_settings() or {}
        for _fam, buckets in (cfg.get("stage_buckets") or {}).items():
            for b in (buckets or []):
                lab = str(b.get("label") or b.get("key") or "").strip().lower()
                if lab == want:
                    for st in (b.get("steps") or []):
                        if str(st).strip():
                            out.add(str(st).strip())
    except Exception:
        return set()
    return out


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "THE ROW IS A BUCKET, NOT A STAGE" in s:
        print("Already applied.")
        return 1
    if s.count(HELPER_ANCHOR) != 1:
        print("The drill route matched %d times." % s.count(HELPER_ANCHOR))
        return 1

    # Only the one inside the drill, not any other exact-stage test.
    i = s.index(HELPER_ANCHOR)
    j = s.index("\n@app.", i)
    block = s[i:j]
    if block.count(OLD) != 1:
        print("The stage filter matched %d times inside the drill."
              % block.count(OLD))
        return 1

    # The decorator sits on the line directly above "def pipeline_funnel_drill".
    # Inserting HELPER at `i` (the start of that def line) would land it AFTER
    # the decorator instead of before it, rebinding @app.get to the helper and
    # leaving the real endpoint unregistered - found by hitting the live route
    # and getting a 422 for a "label" field, which is _stages_in_bucket's own
    # argument, not anything the drill takes.
    deco_start = s.rfind("\n@app.", 0, i) + 1
    s = s[:deco_start] + HELPER + s[deco_start:i] + block.replace(OLD, NEW, 1) + s[j:]

    if "elif d.get(\"stage\") != stage" not in NEW:
        print("A label that is not a bucket would match everything.")
        return 1
    if "except Exception" not in HELPER:
        print("A missing config would break the drill entirely.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A funnel row opens the deals it counts.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_fd1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn and hard-refresh. The row count and the number of")
    print("deals it opens should now be the same.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
