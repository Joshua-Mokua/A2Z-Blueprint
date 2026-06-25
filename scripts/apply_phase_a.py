#!/usr/bin/env python3
"""scripts/apply_phase_a.py — PG persistence migration, Phase A (race-free id +
atomic create) applied IN PLACE to your working tree.

WHY a patcher instead of a ZIP: the sandbox that generated this lost network
access and reset to an older commit, so a whole-file ZIP would REVERT your
committed Phase 3 fixes (privileged-field strip, export scrub, _load_json cache).
This script edits only the specific Phase A blocks, leaving everything else —
including Phase 3 — untouched.

It is idempotent (re-running is a no-op) and backs up each file with a
.pre_phaseA suffix before writing. Dry-run by default.

    python scripts/apply_phase_a.py            # preview
    python scripts/apply_phase_a.py --apply     # write

After --apply: restart the API, then run stress_concurrency.py + the harness.
"""
from __future__ import annotations
import argparse, os, shutil, sys
from datetime import datetime

API = os.path.join("utils", "api.py")
CORE = os.path.join("utils", "core.py")

# ── Edit 1: core.py add_deal — accept a pre-assigned race-free id ──────────────
CORE_OLD = '''    def add_deal(self, d):
        d['id']         = f"D{len(self.deals)+1:04d}"
        d['created_at'] = datetime.now().isoformat()
        d['updated_at'] = datetime.now().isoformat()
        # Batch A: stamp open_date so new deals have a real date for the
        # open_date-DESC list ordering (was unset -> created deals sorted oddly).
        d.setdefault('open_date', datetime.now().strftime('%Y-%m-%d'))
        d['staff_code'] = clean_code(d.get('staff_code',''))
        self.deals.append(d)
        self._save_deals()
        return d['id']'''

CORE_NEW = '''    def add_deal(self, d):
        # Phase A (PG persistence migration): the id may be PRE-ASSIGNED by the
        # caller from a race-free source (PG-derived next id). The legacy
        # len()+1 scheme races under concurrency (two creates compute the same
        # id) and is only a fallback when no id was supplied (JSON-only / no PG).
        if not str(d.get('id') or '').strip():
            d['id'] = f"D{len(self.deals)+1:04d}"
        d['created_at'] = datetime.now().isoformat()
        d['updated_at'] = datetime.now().isoformat()
        # Batch A: stamp open_date so new deals have a real date for the
        # open_date-DESC list ordering (was unset -> created deals sorted oddly).
        d.setdefault('open_date', datetime.now().strftime('%Y-%m-%d'))
        d['staff_code'] = clean_code(d.get('staff_code',''))
        self.deals.append(d)
        self._save_deals()
        return d['id']'''

# ── Edit 2: api.py — add _next_deal_id_from_pg helper before _db_sync ──────────
API_HELPER_ANCHOR = '''def _db_sync_pipeline_deal(deal: Optional[dict]) -> None:
    """Upsert a pipeline deal into Postgres so DB-backed reads reflect runtime'''

API_HELPER_NEW = '''def _next_deal_id_from_pg() -> Optional[str]:
    """Race-free next deal id derived from Postgres (the source of truth).

    Phase A (PG persistence migration). The legacy `D{len(deals)+1}` scheme
    races: two concurrent creates compute the same id, producing duplicates or
    lost writes (confirmed by stress_concurrency.py). Here we derive the next id
    from the MAX existing numeric suffix in pipeline_deals.

    NOTE on ordering: ids are `D` + zero-padded integer. We extract the integer
    and take MAX numerically (not string MAX, which breaks once the width grows
    past 9999: 'D9999' > 'D10000' lexically). Returns None if PG is unavailable,
    so the caller falls back to the JSON scheme (dev / no-PG).

    This is NOT by itself a hard guarantee against a concurrent collision — two
    requests can still read the same MAX in the gap before either inserts. The
    create path therefore relies on the pipeline_deals PRIMARY KEY as the final
    backstop and RETRIES on a unique-violation. This helper just makes
    collisions rare; the PK makes them impossible to persist.
    """
    if not _db_available():
        return None
    try:
        from utils.db import db as _db
        mx = _db.fetch_scalar(
            "SELECT COALESCE(MAX(CAST(NULLIF(regexp_replace(id, '\\\\D', '', 'g'), '') AS BIGINT)), 0) "
            "FROM pipeline_deals", ())
        n = int(mx or 0) + 1
        return f"D{n:04d}"
    except Exception as e:
        logger.warning(f"_next_deal_id_from_pg failed ({e}); falling back to JSON id scheme")
        return None


def _db_sync_pipeline_deal(deal: Optional[dict], conflict: str = "update") -> None:
    """Upsert a pipeline deal into Postgres so DB-backed reads reflect runtime'''

# ── Edit 3: api.py — parameterize the conflict clause in _db_sync ──────────────
API_UPSERT_OLD = '''        if not row["id"]:
            return
        cols = list(row.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "id")
        sql = (f"INSERT INTO pipeline_deals ({', '.join(cols)}) "
               f"VALUES ({placeholders}) "
               f"ON CONFLICT (id) DO UPDATE SET {updates}")
        _db.execute(sql, tuple(row[c] for c in cols))'''

API_UPSERT_NEW = '''        if not row["id"]:
            return
        cols = list(row.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        if conflict == "raise":
            # Create path (Phase A): fail-closed on a duplicate id. DO NOTHING
            # suppresses the insert on conflict; RETURNING id is then empty, which
            # we detect and raise so the caller's retry derives a fresh id. This
            # makes concurrent creates with a colliding id IMPOSSIBLE to persist
            # as a silent overwrite (the PK is the hard guarantee, not a hint).
            sql = (f"INSERT INTO pipeline_deals ({', '.join(cols)}) "
                   f"VALUES ({placeholders}) "
                   f"ON CONFLICT (id) DO NOTHING RETURNING id")
            from utils.db import db as _db2
            got = _db2.fetch_one(sql, tuple(row[c] for c in cols))
            if not got:
                raise RuntimeError(
                    f"duplicate key: deal id {row['id']} already exists in Postgres")
        else:
            # Update/mirror path (default): upsert. Existing row is refreshed.
            updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "id")
            sql = (f"INSERT INTO pipeline_deals ({', '.join(cols)}) "
                   f"VALUES ({placeholders}) "
                   f"ON CONFLICT (id) DO UPDATE SET {updates}")
            _db.execute(sql, tuple(row[c] for c in cols))'''

# ── Edit 4: api.py — main create path: race-free id + fail-closed insert ───────
API_MAIN_OLD = '''    new_id = pm.add_deal(deal_dict)
    try:
        _db_sync_pipeline_deal(pm.get_deal(new_id))  # mirror to Postgres (raises on failure)
        # B13: verify the row actually landed (guards against a silent no-op).
        if _db_available():
            from utils.db import db as _db
            if not _db.fetch_all(
                    "SELECT id FROM pipeline_deals WHERE id = %s", (new_id,)):
                raise RuntimeError(
                    f"Deal {new_id} not present in Postgres after sync")
    except Exception as e:
        # Atomic create: roll back the JSON add so JSON and Postgres never
        # diverge — the deal is in BOTH stores or NEITHER. Honors the standing
        # rule that PostgreSQL is the source of truth.
        try:
            pm.delete_deal(new_id, str(user.get("username", "")))
        except Exception:
            logger.error(f"Rollback delete failed for {new_id}")
        _audit("API_PIPELINE_CREATE_DB_FAILED", user, f"deal_id={new_id} err={e}")
        raise HTTPException(
            status_code=500,
            detail="Could not persist the deal to PostgreSQL — no deal was created.")'''

API_MAIN_NEW = '''    # Phase A (PG persistence migration): assign a race-free id from Postgres
    # BEFORE the JSON add, and retry on a primary-key collision so two concurrent
    # creates can never persist a duplicate id or clobber each other. The create
    # uses an INSERT ... ON CONFLICT (id) DO NOTHING RETURNING id (conflict=
    # "raise"): if the id was taken in the race window, no row returns and we
    # raise -> roll back the JSON add -> derive a fresh id -> retry. The PK is the
    # hard guarantee; _next_deal_id_from_pg just keeps collisions rare. Falls
    # back to the JSON len()+1 scheme only when PG is unavailable (dev / no-PG).
    new_id = None
    _last_err = None
    for _attempt in range(5):
        _pg_id = _next_deal_id_from_pg()
        if _pg_id:
            deal_dict["id"] = _pg_id
        else:
            deal_dict.pop("id", None)  # let add_deal fall back to len()+1
        candidate = pm.add_deal(deal_dict)
        try:
            # conflict="raise": fail-closed insert — raises on a duplicate id
            # rather than silently UPDATE-ing (overwriting) the existing deal.
            _db_sync_pipeline_deal(pm.get_deal(candidate), conflict="raise")
            new_id = candidate
            break
        except Exception as e:
            _last_err = e
            # Roll back the JSON add so the stores never diverge (both or neither).
            try:
                pm.delete_deal(candidate, str(user.get("username", "")))
            except Exception:
                logger.error(f"Rollback delete failed for {candidate}")
            _msg = str(e).lower()
            is_collision = ("duplicate key" in _msg or "unique" in _msg
                            or "already exists" in _msg
                            or "primary key" in _msg)
            if is_collision and _db_available():
                _audit("API_PIPELINE_CREATE_ID_COLLISION", user,
                        f"id={candidate} attempt={_attempt+1}; retrying")
                continue
            break
    if not new_id:
        _audit("API_PIPELINE_CREATE_DB_FAILED", user, f"err={_last_err}")
        raise HTTPException(
            status_code=500,
            detail="Could not persist the deal to PostgreSQL — no deal was created.")'''

# ── Edit 5: api.py — referral create path: same race-free pattern ──────────────
API_REF_OLD = '''    from utils.core import PipelineManager as _PM_for_api
    pm = _PM_for_api()
    new_id = pm.add_deal(referral_record)
    _db_sync_pipeline_deal(pm.get_deal(new_id))  # H5: mirror to DB-backed reads'''

API_REF_NEW = '''    from utils.core import PipelineManager as _PM_for_api
    pm = _PM_for_api()
    # Phase A (PG persistence migration): race-free id + fail-closed insert,
    # same pattern as the main create path (retry on PK collision).
    new_id = None
    _ref_err = None
    for _attempt in range(5):
        _pg_id = _next_deal_id_from_pg()
        if _pg_id:
            referral_record["id"] = _pg_id
        else:
            referral_record.pop("id", None)
        candidate = pm.add_deal(referral_record)
        try:
            _db_sync_pipeline_deal(pm.get_deal(candidate), conflict="raise")
            new_id = candidate
            break
        except Exception as e:
            _ref_err = e
            try:
                pm.delete_deal(candidate, str(user.get("username", "")))
            except Exception:
                logger.error(f"Rollback delete failed for {candidate}")
            _msg = str(e).lower()
            if (("duplicate key" in _msg or "unique" in _msg or "already exists" in _msg
                 or "primary key" in _msg) and _db_available()):
                _audit("API_PIPELINE_REFER_ID_COLLISION", user,
                        f"id={candidate} attempt={_attempt+1}; retrying")
                continue
            break
    if not new_id:
        _audit("API_PIPELINE_REFER_DB_FAILED", user, f"err={_ref_err}")
        raise HTTPException(
            status_code=500,
            detail="Could not persist the referral deal to PostgreSQL — nothing was created.")'''

EDITS = [
    (CORE,  "core.add_deal pre-assigned id",        CORE_OLD,           CORE_NEW),
    (API,   "api._next_deal_id_from_pg helper",     API_HELPER_ANCHOR,  API_HELPER_NEW),
    (API,   "api._db_sync conflict param",          API_UPSERT_OLD,     API_UPSERT_NEW),
    (API,   "api.main create race-free",            API_MAIN_OLD,       API_MAIN_NEW),
    (API,   "api.referral create race-free",        API_REF_OLD,        API_REF_NEW),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    for f in (API, CORE):
        if not os.path.exists(f):
            print(f"FATAL: {f} not found — run from the a2z project root."); sys.exit(2)

    contents = {API: open(API, encoding="utf-8").read(),
                CORE: open(CORE, encoding="utf-8").read()}
    plan = []
    for path, label, old, new in EDITS:
        txt = contents[path]
        if new.split("\n")[0] in txt and old not in txt:
            plan.append((path, label, "ALREADY APPLIED (skip)")); continue
        c_old = txt.count(old)
        if c_old == 1:
            plan.append((path, label, "will apply"))
        elif c_old == 0:
            plan.append((path, label, "!! ANCHOR NOT FOUND — check Phase 3 is present"))
        else:
            plan.append((path, label, f"!! anchor found {c_old}x (ambiguous)"))

    print("Phase A patch plan:")
    for path, label, status in plan:
        print(f"  [{status:35s}] {label}  ({path})")

    bad = [p for p in plan if p[2].startswith("!!")]
    if bad:
        print("\nABORT: one or more anchors not uniquely found. No files written.")
        print("This usually means the file differs from expectation — paste this "
              "output back so the anchors can be adjusted.")
        sys.exit(1)

    if not args.apply:
        print("\n[DRY-RUN] No files written. Re-run with --apply.")
        return

    # apply
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in (API, CORE):
        shutil.copy2(path, f"{path}.pre_phaseA_{ts}")
    for path, label, old, new in EDITS:
        if old in contents[path]:
            contents[path] = contents[path].replace(old, new, 1)
    for path in (API, CORE):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(contents[path]); fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp, path)
    print(f"\nApplied Phase A. Backups: *.pre_phaseA_{ts}")
    print("Now: py_compile check, restart API, run stress_concurrency.py + harness.")

if __name__ == "__main__":
    main()
