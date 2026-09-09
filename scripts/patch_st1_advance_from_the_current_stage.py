#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A committee advances from where the deal is now, not where it was.

D0868: submit advanced the deal Documentation -> Branch Credit Committee
Review at 14:21:10. The committee approved 90 seconds later and its
auto-advance targeted Branch Credit Committee Review - the stage the deal was
already at.

The advance reads `deal`, fetched when the request began. In a request that
only votes, that is the same thing. Where the deal moved in an earlier request
- a submit, another vote, an alignment - it is a stale copy, and the advance
computes the next stage from a position the deal left behind.

The deal is re-read immediately before the stage is worked out.

    python scripts/patch_st1_advance_from_the_current_stage.py            # dry run
    python scripts/patch_st1_advance_from_the_current_stage.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''                _flow = _stage_flow_for(deal.get("product_type")
                                        or deal.get("product", "")) or []
                _cur = str(deal.get("stage", "") or "")'''

NEW = '''                # ── FROM WHERE IT IS NOW ─────────────────────────────────
                # `deal` was fetched when the request began. Where the deal
                # moved in an EARLIER request - a submit, another vote - that
                # copy is stale, and the next stage gets computed from a
                # position the deal has left. D0868 advanced to the stage it
                # was already standing on.
                _now = None
                try:
                    _now = pm.get_deal(deal_id)
                except Exception:
                    _now = None
                _src = _now or deal
                _flow = _stage_flow_for(_src.get("product_type")
                                        or _src.get("product", "")) or []
                _cur = str(_src.get("stage", "") or "")'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "FROM WHERE IT IS NOW" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The advance block matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if "_now or deal" not in NEW:
        print("A failed re-read would lose the deal entirely.")
        return 1
    if "except Exception" not in NEW:
        print("A re-read failure would break the vote.")
        return 1
    # The manager must be in scope where this runs. Look inside the route,
    # from its decorator - not a fixed slice, which found the wrong code.
    i = s.index("FROM WHERE IT IS NOW")
    start = s.rfind("@app.post(", 0, i)
    route = s[start:i]
    if "_pm, deal = _deal_for_docs" not in route:
        print("This route does not bind _pm the way expected.")
        return 1
    s = s.replace("_now = pm.get_deal(deal_id)",
                  "_now = _pm.get_deal(deal_id)", 1)
    print("Re-reads through _pm, which is what this route binds.")
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A committee advances from the deal's current stage.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_st1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. D0868 needs advancing once by hand - it is at the")
    print("stage it was already on. This stops the next one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
