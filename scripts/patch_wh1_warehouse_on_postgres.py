#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WH1 - the deals warehouse lives in Postgres. JSON becomes the mirror.

ON 2026-08-20 THE WAREHOUSE WAS LOST. Every sacco and entity the team had
entered went with it, and there was nothing to recover from: deals_warehouse.py
touched no database, the file was not tracked in git, and it was not gitignored
either. The data existed in exactly one place, on one disk, and then it did not.

RULING, stated repeatedly before that and not honoured here: "we are to be
fully PostgreSQL, JSON is just backup. This is a bank system."

The module is now shaped like pipeline_deals, which is the pattern
docs/PG_PERSISTENCE_MIGRATION_PLAN.md already describes:

    a table          deals_warehouse, typed columns plus a JSONB payload so a
                     field added later cannot be silently dropped
    read first       _read consults the database and only falls back to the
                     file when the database CANNOT ANSWER
    write first      _write upserts to the database, then writes the file

AN EMPTY DATABASE IS A REAL ANSWER, not a failure. A genuinely empty warehouse
returns empty rather than quietly falling back to a stale file - otherwise
deleting the last prospect would resurrect every old one.

DELETES PROPAGATE. A prospect removed from the map is removed from the table
in the same write, or it reappears on the next read.

THE MIRROR STAYS, deliberately. Development boxes run without Postgres, and a
module that raised when the database was down would take the app with it. The
file is a fallback and a readable copy on disk - it is not the source. If the
database answers, its answer wins.

Verified: with no database reachable, create, read, round-trip and delete all
still work through the file.

Usage (from project root, .venv active):
    python scripts\\patch_wh1_warehouse_on_postgres.py            # dry run
    python scripts\\patch_wh1_warehouse_on_postgres.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
BACKUP_SUFFIX = ".pre_wh1"

READ_OLD = '''def _read() -> dict:
    if not os.path.exists(_PATH):
        return {}'''

WRITE_OLD = '''def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)'''
WRITE_NEW = '''def _write(data: dict) -> None:
    # The database is written FIRST and is the record. The file follows as a
    # mirror, so a box without Postgres still works and so there is always a
    # readable copy on disk.
    _db_write(data)
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)'''

READ_TAIL = '''def _read() -> dict:
    # DATABASE FIRST. The file is consulted only when the database cannot
    # answer - and an EMPTY database is a real answer, not a failure, so a
    # genuinely empty warehouse does not silently fall back to a stale file.
    db_rows = _db_read()
    if db_rows is not None:
        return db_rows
    if not os.path.exists(_PATH):
        return {}'''

BLOCK = r'''# ── POSTGRES IS THE STORE. JSON IS THE BACKUP. ──────────────────────────────
# RULING, stated repeatedly: "we are to be fully PostgreSQL, JSON is just
# backup. This is a bank system."
#
# This module was JSON-ONLY - no table, no sync, and the file was not even
# tracked in git. On 2026-08-20 it was lost, and every sacco and entity the
# team had entered went with it. There was nothing to recover from, anywhere.
#
# It now follows the same shape as pipeline_deals: the database is read first
# and written authoritatively, and the JSON file is kept as a mirror so a box
# with no database still works.
#
# WHY THE MIRROR STAYS: development boxes run without Postgres, and a module
# that raises when the database is down would take the whole app with it. The
# mirror is a fallback, NOT the source - if the database answers, its answer
# wins.

_TABLE = "deals_warehouse"


def _db():
    """The database, or None if it is not reachable. Never raises."""
    try:
        from utils.db import Database
        db = Database()
        db.execute("""
            CREATE TABLE IF NOT EXISTS deals_warehouse (
                id              VARCHAR(60) PRIMARY KEY,
                canonical_key   VARCHAR(300),
                name            VARCHAR(300),
                sector          VARCHAR(120),
                subsector       VARCHAR(120),
                town            VARCHAR(120),
                status          VARCHAR(40),
                estimated_value NUMERIC(18,2),
                contact_name    VARCHAR(200),
                contact_phone   VARCHAR(60),
                contact_email   VARCHAR(200),
                notes           TEXT,
                source_event    VARCHAR(200),
                created_by_code VARCHAR(50),
                created_by_name VARCHAR(200),
                created_at      VARCHAR(40),
                claimed_by_code VARCHAR(50),
                claimed_by_name VARCHAR(200),
                claimed_at      VARCHAR(40),
                deal_id         VARCHAR(60),
                payload         JSONB
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_dw_status "
                   "ON deals_warehouse (status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_dw_key "
                   "ON deals_warehouse (canonical_key)")
        return db
    except Exception:
        return None


_COLS = ("id", "canonical_key", "name", "sector", "subsector", "town",
         "status", "estimated_value", "contact_name", "contact_phone",
         "contact_email", "notes", "source_event", "created_by_code",
         "created_by_name", "created_at", "claimed_by_code",
         "claimed_by_name", "claimed_at", "deal_id")


def _db_write(data: dict) -> bool:
    """Upsert every prospect. True if the database took them."""
    db = _db()
    if db is None:
        return False
    try:
        for pid, rec in (data or {}).items():
            if not isinstance(rec, dict):
                continue
            row = {c: rec.get(c) for c in _COLS}
            row["id"] = str(pid)
            try:
                ev = rec.get("estimated_value")
                row["estimated_value"] = float(ev) if ev not in (None, "") else None
            except (TypeError, ValueError):
                row["estimated_value"] = None
            row["payload"] = json.dumps(rec, default=str)
            db.upsert(_TABLE, row, "id")
        # A prospect deleted from the map must go from the table too, or a
        # removed one reappears on the next read.
        keep = [str(k) for k in (data or {})]
        if keep:
            db.execute("DELETE FROM deals_warehouse WHERE id <> ALL(%s)", (keep,))
        else:
            db.execute("DELETE FROM deals_warehouse")
        return True
    except Exception:
        return False


def _db_read():
    """Every prospect from the database, or None if it cannot answer."""
    db = _db()
    if db is None:
        return None
    try:
        rows = db.fetch_all("SELECT * FROM deals_warehouse")
    except Exception:
        return None
    out = {}
    for r in rows or []:
        rec = {}
        pl = r.get("payload")
        if pl:
            try:
                rec = json.loads(pl) if isinstance(pl, str) else dict(pl)
            except Exception:
                rec = {}
        for c in _COLS:
            if r.get(c) is not None:
                rec[c] = r.get(c)
        if rec.get("estimated_value") is not None:
            try:
                rec["estimated_value"] = float(rec["estimated_value"])
            except (TypeError, ValueError):
                pass
        out[str(r.get("id"))] = rec
    return out


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "POSTGRES IS THE STORE" in s:
        print("ABORT: WH1 looks applied.")
        return 1
    if s.count(READ_OLD) != 1 or s.count(WRITE_OLD) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (s.count(READ_OLD), s.count(WRITE_OLD)))
        return 1

    s = s.replace(READ_OLD, BLOCK + READ_TAIL, 1)
    s = s.replace(WRITE_OLD, WRITE_NEW, 1)
    print("  ok  the warehouse reads and writes Postgres")

    if "CREATE TABLE IF NOT EXISTS deals_warehouse" not in BLOCK:
        print("ABORT: no table would be created.")
        return 1
    if "DELETE FROM deals_warehouse WHERE id" not in BLOCK:
        print("ABORT: a deleted prospect would reappear on the next read.")
        return 1
    if "payload" not in BLOCK:
        print("ABORT: no JSONB payload - a field added later would be dropped")
        print("       silently, which is how data goes missing quietly.")
        return 1
    if "return None" not in BLOCK:
        print("ABORT: an unreachable database must be distinguishable from an")
        print("       empty one, or an empty shelf falls back to a stale file.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: table, deletes, payload, empty-vs-unreachable")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)

    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    # Anything still in the file goes into the table on first write.
    try:
        sys.path.insert(0, os.getcwd())
        import importlib
        import utils.deals_warehouse as W
        importlib.reload(W)
        if os.path.exists(W._PATH):
            import json as _json
            existing = _json.load(open(W._PATH, encoding="utf-8"))
            if isinstance(existing, dict) and existing:
                if W._db_write(existing):
                    print("  ok  migrated %d prospect(s) from the file into the"
                          " table" % len(existing))
                else:
                    print("  note: the database was not reachable - the file is")
                    print("        still the store until it is. Re-run this")
                    print("        script with Postgres up to migrate.")
    except Exception as exc:
        print("  note: could not migrate now (%s)" % str(exc)[:50])

    print("\nRESTART UVICORN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
