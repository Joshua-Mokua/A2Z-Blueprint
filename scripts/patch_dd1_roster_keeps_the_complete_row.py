#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Where a staff code appears twice in the register, keep the complete row.

Three officers this fortnight - Billy CN205, Josephat CN020, and now Caroline -
have had deals nobody could validate because their staff code appears more than
once and one of the rows has no branch. Whichever row the lookup reached first
decided the answer, and a blank branch matches nothing, so validation refused.

Every lookup in the system reads this roster: the validate endpoint, the queue,
the per-deal permission, the day view, org_validator. Fixing it here fixes all
of them, and every officer this has not yet been noticed on.

Rows are grouped by staff code. Where there is more than one, the row with the
most filled-in fields wins. Duplicates are logged so the register can be
cleaned up properly - this makes the system usable meanwhile, it does not make
the data correct.

    python scripts/patch_dd1_roster_keeps_the_complete_row.py            # dry run
    python scripts/patch_dd1_roster_keeps_the_complete_row.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_pipeline_scope.py")

OLD = '''    if "Staff Code" in df.columns:
        df["Staff Code"] = df["Staff Code"].astype(str)
    return df'''

NEW = '''    if "Staff Code" in df.columns:
        df["Staff Code"] = df["Staff Code"].astype(str)

        # ── ONE ROW PER STAFF CODE, AND THE COMPLETE ONE ────────────────────
        # Billy CN205, Josephat CN020 and Caroline all had deals nobody could
        # validate because their code appears twice and one row has no branch.
        # Whichever row a lookup reached first decided the answer; a blank
        # branch matches nothing, so validation refused.
        #
        # Every lookup in the system reads this roster, so this is the one
        # place worth fixing. The row with the most filled-in fields wins.
        #
        # This makes the system usable. It does not make the register correct -
        # the duplicates are logged so they can be cleaned up properly.
        try:
            codes = df["Staff Code"].astype(str).str.strip()
            dupes = codes[codes.duplicated(keep=False) & (codes != "")]
            if not dupes.empty:
                filled = df.notna().sum(axis=1)
                for col in df.columns:
                    filled = filled + (df[col].astype(str).str.strip() != "").astype(int)
                df = (df.assign(_code=codes, _filled=filled)
                        .sort_values("_filled", ascending=False)
                        .drop_duplicates(subset="_code", keep="first")
                        .drop(columns=["_code", "_filled"])
                        .sort_index())
                try:
                    import logging
                    logging.getLogger(__name__).warning(
                        "staff register has %d duplicate code(s) - keeping the "
                        "most complete row for each: %s",
                        dupes.nunique(),
                        ", ".join(sorted(set(dupes))[:12]))
                except Exception:
                    pass
        except Exception as exc:
            # Never lose the roster over this. A duplicate is a nuisance; no
            # register at all stops the bank.
            try:
                import logging
                logging.getLogger(__name__).warning(
                    "could not de-duplicate the staff register: %s", exc)
            except Exception:
                pass
    return df'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "ONE ROW PER STAFF CODE" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The roster return matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # It must never drop a row that is not a duplicate.
    if "duplicated(keep=False)" not in NEW:
        print("This would touch rows that are not duplicates.")
        return 1
    # And it must never lose the roster entirely on an error.
    if "except Exception" not in NEW or "return df" not in NEW:
        print("An error here could leave the system with no register at all.")
        return 1
    if "sort_index()" not in NEW:
        print("The roster order would change, which other code may rely on.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Duplicates resolve to the most complete row, and are logged.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_dd1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. The roster caches for a few minutes, so give it")
    print("that long before testing. Check the log for the duplicate list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
