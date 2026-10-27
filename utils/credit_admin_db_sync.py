"""
utils/credit_admin_db_sync.py  —  Batch CA-1 (sync + normalizer) + CA-2 (live wiring).

PostgreSQL write-sync + read-normalizer for credit_admin cases, plus the CA-2
installer that makes CreditAdminManager read Postgres-first and serialize every
mutation through a transactional, row-locked read-modify-write.

Design choice vs pipeline: the COMPLETE case is stored in `data` JSONB, so no
sub-flow field (collateral / legal / perfection / insurance / authorizations /
override) is ever lost. Scalar columns are query/index helpers only. This is
what lets CA-2's distinct-case probe pass without an unmirrored-field gap (the
pipeline mirror is partial — e.g. next_action is not synced).

CA-2 concurrency model:
  * READS  — _load() pulls every case from Postgres when the table is DB-backed,
             so list (cam.cases) and detail (cam.get) are PG-first.
  * WRITES — each case-mutating method is wrapped: open a transaction, SELECT the
             target row FOR UPDATE (lock + fresh read), run the original mutation
             on that fresh case, then upsert the whole case back in the SAME
             transaction. Concurrent writes to one case serialize on the row lock
             (fixes lost appends); writes to distinct cases lock distinct rows
             (no contention, no lost update). The JSON file remains a best-effort
             mirror; Postgres is authoritative. No-op when PG is unavailable.
"""
from __future__ import annotations
import functools
import json as _json
import logging
from datetime import date as _date
from typing import Optional

_log = logging.getLogger("a2z.credit_admin")

# Scalar columns lifted to the table for query/index. Order == INSERT column order.
_SCALAR_ORDER = [
    "id", "application_id", "client_name", "product", "amount",
    "rm_code", "rm_name", "approval_date", "all_conditions_met",
    "ready_for_disbursement", "disbursed", "disbursement_date",
    "last_updated", "data",
]

# Instance methods on CreditAdminManager that mutate ONE case (case_id is the
# first positional arg) and persist via self.save(). Each is wrapped in the
# transactional row-locked RMW. Static/compute helpers and the create path are
# deliberately excluded (create is handled separately).
_MUTATION_METHODS = [
    "fulfill_condition", "set_facility_classification", "classify_condition",
    "link_collateral", "unlink_collateral",
    "assign_legal_officer", "add_legal_comment", "set_legal_outcome",
    "add_security_perfection", "update_security_perfection",
    "add_insurance_policy", "update_insurance_policy",
    "request_perfection_override", "add_override_approval",
    "request_authorization", "authorize", "clear_for_disbursement",
    "troops_book", "troops_set_value_date", "troops_disburse",
]


def _date_or_none(v):
    """Coerce '' / None / whitespace to NULL; pass through real date strings."""
    v = (str(v).strip() if v is not None else "")
    return v or None


def _row_from_case(case: dict) -> Optional[dict]:
    """Build the DB row dict (scalars + complete-case JSONB) from a case."""
    cid = str(case.get("id", "") or "")
    if not cid:
        return None
    today = _date.today().isoformat()
    return {
        "id":                     cid,
        "application_id":         case.get("application_id"),
        "client_name":            case.get("client_name"),
        "product":                case.get("product"),
        "amount":                 case.get("amount"),
        "rm_code":                case.get("rm_code"),
        "rm_name":                case.get("rm_name"),
        "approval_date":          _date_or_none(case.get("approval_date")),
        "all_conditions_met":     bool(case.get("all_conditions_met")),
        "ready_for_disbursement": bool(case.get("ready_for_disbursement")),
        "disbursed":              bool(case.get("disbursed")),
        "disbursement_date":      _date_or_none(case.get("disbursement_date")),
        "last_updated":           _date_or_none(case.get("last_updated")) or today,
        # COMPLETE, lossless mirror of the whole case:
        "data":                   _json.dumps(case, default=str),
    }


def _db_sync_credit_admin_case(case: Optional[dict], conflict: str = "update",
                               swallow: bool = True, conn=None) -> None:
    """Upsert a credit_admin case into Postgres.

    conflict='update' (default): mirror/upsert — ON CONFLICT (id) DO UPDATE.
    conflict='raise':            create path — ON CONFLICT DO NOTHING; raises if
                                 the id already exists (no silent overwrite).
    swallow=True (default):      log-and-continue on error (live mirror).
    swallow=False:               re-raise on error (backfill / transactional RMW
                                 — a failed write inside the txn MUST abort it).
    conn:                        when given (update path only), the upsert runs
                                 on this connection so it participates in an open
                                 transaction (the row-locked RMW). Commit is the
                                 caller's transaction boundary.

    No-op when Postgres is unavailable.
    """
    if not case:
        return
    try:
        from utils.db import db as _db
    except Exception as e:
        _log.error(f"credit_admin sync: cannot import db: {e}")
        return
    if not _db.is_postgres_ready():
        return

    row = _row_from_case(case)
    if row is None:
        return
    cols = _SCALAR_ORDER
    placeholders = ", ".join(["%s"] * len(cols))
    values = tuple(row[c] for c in cols)

    try:
        if conflict == "raise":
            sql = (f"INSERT INTO credit_admin ({', '.join(cols)}) "
                   f"VALUES ({placeholders}) "
                   f"ON CONFLICT (id) DO NOTHING RETURNING id")
            got = _db.fetch_one(sql, values)
            if not got:
                raise RuntimeError(
                    f"duplicate key: credit_admin id {row['id']} already in Postgres")
        else:
            updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "id")
            sql = (f"INSERT INTO credit_admin ({', '.join(cols)}) "
                   f"VALUES ({placeholders}) "
                   f"ON CONFLICT (id) DO UPDATE SET {updates}")
            _db.execute(sql, values, conn=conn)
    except Exception as e:
        _log.error(f"credit_admin DB sync FAILED for {row['id']}: {e}")
        if conflict == "raise" or not swallow:
            raise


def _normalize_db_credit_admin_row(row: Optional[dict]) -> Optional[dict]:
    """Reconstruct the full case dict from a PG row (complete case in `data`)."""
    if not row:
        return None
    data = row.get("data")
    if isinstance(data, str):
        try:
            data = _json.loads(data)
        except Exception:
            data = {}
    case = dict(data) if isinstance(data, dict) else {}
    if not case.get("id") and row.get("id"):
        case["id"] = row["id"]
    return case


# ─────────────────────────────────────────────────────────────────────────────
# CA-2: live installer — PG-first reads + transactional row-locked RMW writes.
# ─────────────────────────────────────────────────────────────────────────────
def _case_hash(case: dict) -> int:
    """Stable within-process hash of a case, for dirty-diff at save()."""
    try:
        return hash(_json.dumps(case, sort_keys=True, default=str))
    except Exception:
        return hash(repr(case))


def _wrap_mutation(method):
    """Serialize a single-case mutation through a row-locked transaction.

    On the DB-backed path: open a transaction, SELECT the target row FOR UPDATE
    (lock + fresh read), swap that fresh case into self.cases, run the original
    mutation (which edits the fresh case and writes the JSON mirror via
    self.save()), then upsert the mutated case back inside the SAME transaction.
    Concurrent same-case calls block on FOR UPDATE and apply in series.
    """
    @functools.wraps(method)
    def wrapper(self, case_id, *args, **kwargs):
        try:
            from utils.db import db as _db
        except Exception as exc:
            if __import__("os").environ.get("A2Z_AVAILMENT_TROPS_GATE", "").strip() == "enabled":
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="PostgreSQL required for Availment-controlled operations") from exc
            return method(self, case_id, *args, **kwargs)
        if not _db.table_uses_db("credit_admin"):
            if __import__("os").environ.get("A2Z_AVAILMENT_TROPS_GATE", "").strip() == "enabled":
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail="PostgreSQL required for Availment-controlled operations")
            return method(self, case_id, *args, **kwargs)   # JSON-only legacy path

        original_cases = __import__("copy").deepcopy(self.cases)
        original_snapshot = __import__("copy").deepcopy(getattr(self, "_ca_snapshot", None))
        try:
            with _db.transaction() as conn:
                # Lock + fresh-read the target case; replace any stale snapshot.
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT data FROM credit_admin WHERE id = %s FOR UPDATE",
                        (str(case_id),))
                    got = cur.fetchone()
                if got is None and __import__("os").environ.get("A2Z_AVAILMENT_TROPS_GATE", "").strip() == "enabled":
                    from fastapi import HTTPException
                    raise HTTPException(status_code=409, detail="Credit Admin case missing from PostgreSQL; controlled mutation blocked")
                if got is not None:
                    data = got[0]
                    fresh = data if isinstance(data, dict) else _json.loads(data)
                    self.cases = [c for c in self.cases if c.get("id") != case_id]
                    self.cases.append(fresh)

                self._in_rmw = True   # tells save() to skip its own PG-sync (we do it in-txn)
                try:
                    result = method(self, case_id, *args, **kwargs)   # mutate + JSON mirror
                finally:
                    self._in_rmw = False

                mutated = self.get(case_id)
                if method.__name__ == "clear_for_disbursement" and __import__("os").environ.get("A2Z_AVAILMENT_TROPS_GATE", "").strip() == "enabled" and result is True:
                    from fastapi import HTTPException
                    actor = kwargs.get("release_actor") if isinstance(kwargs.get("release_actor"), dict) else {}
                    staff_code = str(actor.get("staff_code") or "").strip()
                    if not staff_code:
                        raise HTTPException(status_code=403, detail="Releasing officer identity required")
                    with conn.cursor() as cur:
                        cur.execute("SELECT id, status, current_version, approval_assignee_code, created_by_code, approval_requested_by_code, sent_to_trops_at, data, application_id FROM credit.availment_memos WHERE credit_admin_case_id=%s FOR UPDATE", (case_id,))
                        memo = cur.fetchone()
                    if not memo or str(memo[1]).lower() != "approved" or int(memo[2] or 0) < 1 or memo[6] is not None:
                        raise HTTPException(status_code=409, detail="Approved, unreleased Availment Memo version required")
                    with conn.cursor() as cur:
                        cur.execute("SELECT snapshot FROM credit.availment_versions WHERE memo_id=%s AND version=%s", (memo[0], memo[2]))
                        approved_row = cur.fetchone()
                    snapshot = approved_row[0] if approved_row else None
                    if isinstance(snapshot, str):
                        snapshot = _json.loads(snapshot)
                    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("approval"), dict) or not isinstance(snapshot.get("memo"), dict) or snapshot.get("version") != int(memo[2]):
                        raise HTTPException(status_code=409, detail="Valid approved Availment Memo snapshot required")
                    locked_data = memo[7] if isinstance(memo[7], dict) else _json.loads(memo[7])
                    approved_data = snapshot["memo"].get("data")
                    if not isinstance(locked_data, dict) or approved_data != locked_data or snapshot["memo"].get("application_id") != memo[8]:
                        raise HTTPException(status_code=409, detail="Approved Availment Memo snapshot differs from locked memo data")
                    actual_approver = str(snapshot["approval"].get("approved_by_code") or "").strip()
                    if not actual_approver or snapshot["memo"].get("id") != memo[0] or snapshot["memo"].get("credit_admin_case_id") != case_id:
                        raise HTTPException(status_code=409, detail="Approved Availment Memo identity verification failed")
                    if staff_code.casefold() in {str(value or "").strip().casefold() for value in (memo[3], memo[4], memo[5], actual_approver, snapshot["memo"].get("created_by_code"), snapshot["approval"].get("requested_by_code"))}:
                        raise HTTPException(status_code=403, detail="Releasing officer must be independent of memo maker, requester and actual approver")
                    _db.execute("UPDATE credit.availment_memos SET sent_to_trops_by=%s, sent_to_trops_at=now() WHERE id=%s", (staff_code, memo[0]), conn=conn)
                    if mutated is not None:
                        mutated["availment_released_version"] = int(memo[2])
                        mutated["availment_released_by"] = staff_code
                if mutated:
                    # swallow=False: a failed PG write must roll the txn back, not
                    # leave JSON and PG silently diverged.
                    _db_sync_credit_admin_case(
                        mutated, conflict="update", swallow=False, conn=conn)
        except BaseException:
            self.cases = original_cases
            if original_snapshot is None:
                self.__dict__.pop("_ca_snapshot", None)
            else:
                self._ca_snapshot = original_snapshot
            raise
        if mutated:
            snap = getattr(self, "_ca_snapshot", None)
            if snap is not None:
                snap[case_id] = _case_hash(mutated)
        # PostgreSQL committed successfully; refresh the legacy JSON mirror.
        # Mirror failures must not reverse or misreport the committed DB mutation.
        try:
            self.save()
        except Exception:
            _log.exception("Credit Admin JSON mirror refresh failed after PostgreSQL commit")
        return result
    return wrapper


def install_credit_admin_concurrency(cls) -> None:
    """Idempotently install PG-first reads + transactional RMW on the manager."""
    if getattr(cls, "_ca2_installed", False):
        return

    # 1) PG-first _load (covers list + detail reads).
    _orig_load = cls._load

    def _load_pg_first(self):
        cases = None
        try:
            from utils.db import db as _db
            if _db.table_uses_db("credit_admin"):
                rows = _db.fetch_all("SELECT id, data FROM credit_admin")
                cases = [c for c in (_normalize_db_credit_admin_row(r) for r in rows if r) if c]
        except Exception as e:
            _log.error(f"credit_admin PG-first load failed; JSON fallback: {e}")
            cases = None
        if cases is None:
            cases = _orig_load(self)
        # Snapshot for dirty-diff at save() — so ANY mutation (manager method OR
        # route-level get()+field-set) that ends in save() is synced to PG.
        try:
            self._ca_snapshot = {c.get("id"): _case_hash(c) for c in cases if c.get("id")}
        except Exception:
            self._ca_snapshot = {}
        return cases

    cls._load = _load_pg_first

    # save()-hook: universal PG-sync net. Every credit-admin mutation funnels
    # through save(); diff against the load snapshot and upsert changed cases.
    # Skipped inside a wrapped RMW txn (that path syncs in-transaction).
    _orig_save = cls.save

    def _save_with_sync(self):
        if getattr(self, "_in_rmw", False):
            return  # Defer JSON mirror until the PostgreSQL transaction commits.
        _orig_save(self)
        try:
            from utils.db import db as _db
            if not _db.table_uses_db("credit_admin"):
                return
            snap = getattr(self, "_ca_snapshot", None)
            if snap is None:
                snap = {}
            for c in self.cases:
                cid = c.get("id")
                if not cid:
                    continue
                h = _case_hash(c)
                if snap.get(cid) != h:
                    _db_sync_credit_admin_case(c, conflict="update", swallow=True)
                    snap[cid] = h
            self._ca_snapshot = snap
        except Exception as e:
            _log.error(f"credit_admin save-sync failed: {e}")

    cls.save = _save_with_sync

    # 2) Wrap single-case mutations with the row-locked RMW.
    for name in _MUTATION_METHODS:
        orig = getattr(cls, name, None)
        if callable(orig):
            setattr(cls, name, _wrap_mutation(orig))

    # Create path needs no special handling: create_case_from_application appends
    # the new case and calls self.save(), so the save()-hook above upserts it
    # (a brand-new id is "changed" vs the load snapshot). (Create-RACE under
    # burst remains Phase-C / JSON-mirror retirement, same as pipeline Probe 1.)

    cls._ca2_installed = True
    _log.info("CA-2 installed on CreditAdminManager (PG-first reads + RMW writes)")
