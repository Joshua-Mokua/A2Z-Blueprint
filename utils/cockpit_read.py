"""
================================================================================
A2Z MIS 360 — Cockpit Read Helpers
================================================================================

Phase 3 utility: provides read-side access to engine records that lets
cockpit pages display "live data" tabs without duplicating the
per-engine `_load` logic.

Engines own their write paths; this module provides a uniform read
path so the cockpit can compose data across engines.

The helpers are deliberately conservative:
  - They read through the same dual-storage layer the engines use
  - They never modify records — read-only access
  - They tolerate missing files (returns empty list)
  - They tolerate stale/legacy record shapes (passes through; the
    cockpit applies its own filter+warning if needed)

Usage:
    from utils.cockpit_read import load_records, filter_records

    sessions = load_records(
        path="data/cims_capture_sessions.json",
        table="cims_capture_sessions",
        index_cols=("session_id",),
    )

    recent = filter_records(
        sessions,
        since_iso=(datetime.utcnow() - timedelta(days=7)).isoformat(),
        date_field="registered_at",
    )

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


def load_records(
    path: str | Path,
    table: str,
    index_cols: Tuple[str, ...],
) -> List[Dict[str, Any]]:
    """Load records through the dual-storage layer.

    Returns an empty list on any error — cockpit reads should never
    crash because data isn't there yet.
    """
    try:
        from utils.db import db as _db
        data = _db.dual_load(
            Path(path), table=table, index_cols=index_cols,
        )
        return data if isinstance(data, list) else []
    except Exception:
        return []


def filter_records(
    records: List[Dict[str, Any]],
    since_iso: Optional[str] = None,
    until_iso: Optional[str] = None,
    date_field: str = "registered_at",
    state: Optional[str] = None,
    state_field: str = "state",
    custom_predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> List[Dict[str, Any]]:
    """Filter records by date window, state, and/or custom predicate.

    All filters are inclusive of records where the relevant field is
    missing UNLESS that filter is explicitly applied — this preserves
    legacy-data tolerance.
    """
    out = []
    for r in records:
        if since_iso is not None:
            rd = r.get(date_field, "")
            if not rd or rd < since_iso:
                continue
        if until_iso is not None:
            rd = r.get(date_field, "")
            if not rd or rd > until_iso:
                continue
        if state is not None:
            if r.get(state_field) != state:
                continue
        if custom_predicate is not None:
            try:
                if not custom_predicate(r):
                    continue
            except Exception:
                continue
        out.append(r)
    return out


def sort_records(
    records: List[Dict[str, Any]],
    by_field: str = "registered_at",
    descending: bool = True,
) -> List[Dict[str, Any]]:
    """Sort records by a field; missing values sort last."""
    def keyfn(r):
        v = r.get(by_field, "")
        return (v == "", v)
    sorted_records = sorted(records, key=keyfn, reverse=descending)
    return sorted_records


def group_by(
    records: List[Dict[str, Any]],
    by_field: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Group records by a field value."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        k = str(r.get(by_field, ""))
        out.setdefault(k, []).append(r)
    return out


def count_by(
    records: List[Dict[str, Any]],
    by_field: str,
) -> Dict[str, int]:
    """Count records by field value."""
    out: Dict[str, int] = {}
    for r in records:
        k = str(r.get(by_field, ""))
        out[k] = out.get(k, 0) + 1
    return out


def find_by_id(
    records: List[Dict[str, Any]],
    id_field: str,
    id_value: str,
) -> Optional[Dict[str, Any]]:
    """Find first record where record[id_field] == id_value."""
    for r in records:
        if r.get(id_field) == id_value:
            return r
    return None


def latest_n(
    records: List[Dict[str, Any]],
    n: int = 25,
    by_field: str = "registered_at",
) -> List[Dict[str, Any]]:
    """Return the latest N records ordered most-recent-first."""
    return sort_records(records, by_field=by_field, descending=True)[:n]


# ---------- CIMS-specific composers ----------
# Cross-engine read-side composability: given a linked_session_id,
# join capture + classification + STP + exception + SLA + history.

# ── CIMS vocabulary harmonization (B-001 closure, v10.303) ────────────────
# Different CIMS engines use different names for the same semantic
# concept:
#   - Capture #166 INSTRUCTION_TYPES includes `COMPLAINT`.
#   - NLP #167 INTENT_CATEGORIES includes `COMPLAINT` and
#     `INFORMATION_REQUEST`.
#   - SLA #171 INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS keys on
#     `CUSTOMER_COMPLAINT`, `GENERAL_INQUIRY`,
#     `DISPUTE_INVESTIGATION`, `BILLING_ERROR`,
#     `REGULATORY_REPORTING`.
#
# Without translation, a `COMPLAINT` captured at #166 won't match
# SLA's `CUSTOMER_COMPLAINT` deadline key — the regulatory deadline
# never auto-attaches.
#
# Approach: TRANSLATION LAYER here in cockpit_read, not engine
# rewrites. Engines stay byte-for-byte locked under G182-G185.
# Canonical vocabulary = SLA framework's regulatory-aligned names
# because they map to Reg E / Reg Z / CBK Banking Act categories.

# Mapping from non-canonical (capture/NLP) to canonical (SLA)
# vocabulary. Source is keyed by uppercased lookup; canonical
# values are SLA's INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS keys.
_CIMS_INSTRUCTION_TYPE_CANONICAL_MAP: Dict[str, str] = {
    # Capture #166 INSTRUCTION_TYPES → SLA #171 keys
    "COMPLAINT": "CUSTOMER_COMPLAINT",
    # NLP #167 INTENT_CATEGORIES → SLA #171 keys
    "INFORMATION_REQUEST": "GENERAL_INQUIRY",
    # Already-canonical values pass through (idempotency)
    "CUSTOMER_COMPLAINT": "CUSTOMER_COMPLAINT",
    "GENERAL_INQUIRY": "GENERAL_INQUIRY",
    "DISPUTE_INVESTIGATION": "DISPUTE_INVESTIGATION",
    "BILLING_ERROR": "BILLING_ERROR",
    "REGULATORY_REPORTING": "REGULATORY_REPORTING",
}


def normalize_instruction_type(raw: Any) -> Any:
    """Translate any CIMS instruction_type to the canonical
    (SLA framework) vocabulary so cross-engine joins work.

    Behavior:
      - Known mappings: return canonical SLA key (e.g.
        `COMPLAINT` → `CUSTOMER_COMPLAINT`).
      - Already canonical values: pass through unchanged.
      - Unknown values: pass through unchanged (legacy /
        vendor / typo tolerance). Cockpit still displays them;
        operators investigate.
      - None / empty: return as-is. The caller decides whether
        to substitute a placeholder.
      - Case-insensitive: `complaint` → `CUSTOMER_COMPLAINT`.

    The function is idempotent: normalize(normalize(x)) == normalize(x).
    """
    if raw is None or raw == "":
        return raw
    if not isinstance(raw, str):
        # Numbers, dicts, etc. — return unchanged
        return raw
    key = raw.strip().upper()
    if key in _CIMS_INSTRUCTION_TYPE_CANONICAL_MAP:
        return _CIMS_INSTRUCTION_TYPE_CANONICAL_MAP[key]
    return raw


def cims_vocabulary_map() -> Dict[str, Any]:
    """Operator-facing reference of the CIMS vocabulary
    translation table. Groups mappings by source vocabulary so
    operators (and the React SPA) can render a reference table.

    Returns:
      {
        "capture":   {raw: canonical, ...},   # capture #166
        "nlp":       {raw: canonical, ...},   # NLP #167
        "canonical": [list of all SLA keys],  # SLA #171 target
        "rationale": "<one-line explanation>",
      }
    """
    return {
        "capture": {
            "COMPLAINT": "CUSTOMER_COMPLAINT",
        },
        "nlp": {
            "INFORMATION_REQUEST": "GENERAL_INQUIRY",
            # NLP also emits COMPLAINT — same mapping as capture
            "COMPLAINT": "CUSTOMER_COMPLAINT",
        },
        "canonical": [
            "CUSTOMER_COMPLAINT",
            "GENERAL_INQUIRY",
            "DISPUTE_INVESTIGATION",
            "BILLING_ERROR",
            "REGULATORY_REPORTING",
        ],
        "rationale": (
            "SLA framework #171 keys are the canonical "
            "instruction-type vocabulary because they map to "
            "Reg E / Reg Z / CBK Banking Act regulatory "
            "categories. Capture #166 and NLP #167 vocabularies "
            "predate the SLA framework; cockpit_read.normalize_"
            "instruction_type bridges them at read time."
        ),
    }


def cims_instruction_trace(
    linked_session_id: str,
    data_dir: str | Path = "data",
) -> Dict[str, Any]:
    """Compose all CIMS engine records for a single linked_session_id.

    Returns a dict with keys: capture, classification_requests,
    stp_requests, exceptions, sla_obligations, history. Each value
    is a list (possibly empty). Operators can use this to see the
    full lifecycle of one instruction across all 15 CIMS engines.
    """
    base = Path(data_dir)

    # Capture session itself
    sessions = load_records(
        base / "cims_capture_sessions.json",
        "cims_capture_sessions", ("session_id",),
    )
    capture = find_by_id(sessions, "session_id", linked_session_id)

    # v10.303 — B-001 vocabulary harmonisation. Enrich the
    # capture record with canonical_instruction_type so
    # operators + the React SPA can join against SLA deadlines
    # without each consumer re-implementing the mapping.
    if isinstance(capture, dict) and "instruction_type" in capture:
        canonical = normalize_instruction_type(
            capture.get("instruction_type"))
        # Create a shallow copy to avoid mutating the source
        # (find_by_id returns a reference; trace must remain
        # read-only on disk + in memory beyond the trace dict
        # we hand back).
        capture = dict(capture)
        capture["canonical_instruction_type"] = canonical

    # NLP classification requests linked to this session
    classification_requests = load_records(
        base / "cims_classification_requests.json",
        "cims_classification_requests", ("request_id",),
    )
    classification_requests = filter_records(
        classification_requests,
        custom_predicate=lambda r: (
            r.get("session_id") == linked_session_id
            or r.get("linked_session_id") == linked_session_id
        ),
    )

    # STP requests for this session
    stp_requests = load_records(
        base / "cims_stp_requests.json",
        "cims_stp_requests", ("request_id",),
    )
    stp_requests = filter_records(
        stp_requests,
        custom_predicate=lambda r: (
            r.get("session_id") == linked_session_id
            or r.get("linked_session_id") == linked_session_id
        ),
    )

    # Exceptions for this session
    exceptions = load_records(
        base / "cims_exceptions.json",
        "cims_exceptions", ("exception_id",),
    )
    exceptions = filter_records(
        exceptions,
        custom_predicate=lambda r: (
            r.get("linked_session_id") == linked_session_id
            or r.get("session_id") == linked_session_id
        ),
    )

    # SLA obligations linked to this session
    sla_obligations = load_records(
        base / "cims_sla_obligations.json",
        "cims_sla_obligations", ("obligation_id",),
    )
    sla_obligations = filter_records(
        sla_obligations,
        custom_predicate=lambda r: (
            r.get("linked_session_id") == linked_session_id
        ),
    )

    # Audit history for this session
    history = load_records(
        base / "cims_audit_history.json",
        "cims_audit_history", ("record_id",),
    )
    history = filter_records(
        history,
        custom_predicate=lambda r: (
            r.get("linked_session_id") == linked_session_id
        ),
    )
    history = sort_records(history, by_field="registered_at",
                              descending=False)

    return {
        "linked_session_id": linked_session_id,
        "capture": capture,
        "classification_requests": classification_requests,
        "stp_requests": stp_requests,
        "exceptions": exceptions,
        "sla_obligations": sla_obligations,
        "history": history,
    }


def cims_open_work(
    data_dir: str | Path = "data",
    limit: int = 50,
) -> Dict[str, Any]:
    """Aggregate the current open-work landscape across CIMS engines.

    Returns counts and recent items for queues that an operations
    head needs to see at a glance: open capture sessions, pending
    NLP classifications, pending STP reviews, open exceptions,
    upcoming SLA deadlines, pending merges.

    All counts come from live engine data — no precomputed snapshots.
    """
    base = Path(data_dir)

    # Open capture sessions (not COMPLETED/ABANDONED)
    sessions = load_records(
        base / "cims_capture_sessions.json",
        "cims_capture_sessions", ("session_id",),
    )
    open_sessions = filter_records(
        sessions,
        custom_predicate=lambda r: r.get("state") not in (
            "COMPLETED", "ABANDONED", "CANCELLED",
        ),
    )

    # Pending NLP classifications (not COMPLETED)
    nlp_requests = load_records(
        base / "cims_classification_requests.json",
        "cims_classification_requests", ("request_id",),
    )
    pending_nlp = filter_records(
        nlp_requests,
        custom_predicate=lambda r: r.get("state") not in (
            "COMPLETED", "OVERRIDDEN", "FAILED",
        ),
    )

    # STP pending manual review
    stp_requests = load_records(
        base / "cims_stp_requests.json",
        "cims_stp_requests", ("request_id",),
    )
    pending_stp_manual = filter_records(
        stp_requests,
        state="MANUAL_REVIEW",
    )

    # Open exceptions
    exceptions = load_records(
        base / "cims_exceptions.json",
        "cims_exceptions", ("exception_id",),
    )
    open_exceptions = filter_records(
        exceptions,
        custom_predicate=lambda r: r.get("state") not in (
            "RESOLVED", "CANCELLED",
        ),
    )

    # SLA obligations approaching/past deadline
    sla_obligations = load_records(
        base / "cims_sla_obligations.json",
        "cims_sla_obligations", ("obligation_id",),
    )
    now_iso = datetime.utcnow().isoformat()
    upcoming_sla = filter_records(
        sla_obligations,
        custom_predicate=lambda r: (
            r.get("state") in ("PENDING", "IN_PROGRESS")
            and r.get("deadline_at", "9999") >= now_iso
        ),
    )
    breached_sla = filter_records(
        sla_obligations,
        custom_predicate=lambda r: (
            r.get("state") == "BREACHED"
            or (
                r.get("state") in ("PENDING", "IN_PROGRESS")
                and r.get("deadline_at", "9999") < now_iso
            )
        ),
    )

    # Pending identity merges
    merges = load_records(
        base / "cims_identity_merges.json",
        "cims_identity_merges", ("merge_id",),
    )
    pending_merges = filter_records(
        merges,
        custom_predicate=lambda r: r.get("state") not in (
            "APPROVED", "REJECTED", "REVERSED",
        ),
    )

    return {
        "open_capture_sessions": len(open_sessions),
        "pending_nlp": len(pending_nlp),
        "pending_stp_manual": len(pending_stp_manual),
        "open_exceptions": len(open_exceptions),
        "upcoming_sla": len(upcoming_sla),
        "breached_sla": len(breached_sla),
        "pending_merges": len(pending_merges),
        "recent_open_sessions":
            latest_n(open_sessions, n=limit),
        "recent_open_exceptions":
            latest_n(open_exceptions, n=limit),
        "recent_breached_sla":
            latest_n(breached_sla, n=limit,
                       by_field="deadline_at"),
    }


# ---------- Treasury-specific composer ----------
# v10.296 — Treasury live cockpit aggregator. Reads regulatory
# JSON files (liquidity_metrics, irrbb, treasury_fx) and reports
# the bank-wide treasury landscape. Read-only; never mutates
# upstream data.

def _safe_load_json(path: Path) -> Optional[Any]:
    """Load JSON; return None on any error (missing file,
    malformed content, permission issues, etc.). The cockpit
    must degrade gracefully — operators sometimes hand-edit
    these files."""
    try:
        if not path.exists():
            return None
        import json as _json
        with open(path, "r") as f:
            return _json.load(f)
    except Exception:
        return None


def treasury_open_work(
    data_dir: str | Path = "data",
) -> Dict[str, Any]:
    """Aggregate bank-wide Treasury work landscape.

    Reads liquidity_metrics.json, irrbb.json, and treasury_fx.json
    from `data_dir` and returns a single dict with the headline
    counts the cockpit displays.

    Read-only: never modifies any source file.
    Legacy-tolerant: missing or malformed files return sensible
    defaults.

    Returns dict with documented keys:
      fx_positions_count   — count of records in treasury_fx.json
      open_fx_deals        — count where status not in
                             ('SETTLED', 'CANCELLED', 'CLOSED')
      irrbb_breaches       — count of scenarios where ear_pct or
                             eve_pct exceeds CBK limit
      lcr_pct              — current LCR or None
      lcr_min_pct          — minimum LCR threshold or None
      lcr_breached         — True if lcr < lcr_min
      as_at                — ISO timestamp of THIS read
                             (not source data's as_at)
    """
    base = Path(data_dir)

    # ---- FX ----
    fx_records = _safe_load_json(base / "treasury_fx.json") or []
    if not isinstance(fx_records, list):
        fx_records = []
    fx_positions_count = len(fx_records)
    # Open = not in a terminal status. Records without `status`
    # are counted as open (legacy-tolerant — operators see them
    # rather than have them silently disappear).
    terminal_states = {"SETTLED", "CANCELLED", "CLOSED"}
    open_fx_deals = sum(
        1 for r in fx_records
        if isinstance(r, dict)
        and r.get("status") not in terminal_states
    )

    # ---- IRRBB ----
    irrbb = _safe_load_json(base / "irrbb.json")
    irrbb_breaches = 0
    if isinstance(irrbb, dict):
        ear_limit = irrbb.get("cbk_limit_ear_pct")
        eve_limit = irrbb.get("cbk_limit_eve_pct")
        scenarios = irrbb.get("scenarios", [])
        if isinstance(scenarios, list):
            for s in scenarios:
                if not isinstance(s, dict):
                    continue
                ear = s.get("ear_pct")
                eve = s.get("eve_pct")
                # Test against absolute value — limits work both ways
                if (ear_limit is not None and ear is not None
                        and abs(float(ear)) > float(ear_limit)):
                    irrbb_breaches += 1
                    continue  # Don't double-count one scenario
                if (eve_limit is not None and eve is not None
                        and abs(float(eve)) > float(eve_limit)):
                    irrbb_breaches += 1

    # ---- Liquidity / LCR ----
    liq = _safe_load_json(base / "liquidity_metrics.json")
    lcr_pct: Optional[float] = None
    lcr_min: Optional[float] = None
    lcr_breached = False
    if isinstance(liq, dict):
        lcr_pct = liq.get("lcr")
        lcr_min = liq.get("lcr_minimum_pct")
        if (isinstance(lcr_pct, (int, float))
                and isinstance(lcr_min, (int, float))):
            lcr_breached = float(lcr_pct) < float(lcr_min)

    return {
        "fx_positions_count": fx_positions_count,
        "open_fx_deals": open_fx_deals,
        "irrbb_breaches": irrbb_breaches,
        "lcr_pct": lcr_pct,
        "lcr_min_pct": lcr_min,
        "lcr_breached": lcr_breached,
        "as_at": datetime.utcnow().isoformat(),
    }


def treasury_liquidity_metrics(
    data_dir: str | Path = "data",
) -> Optional[Dict[str, Any]]:
    """Load liquidity_metrics.json safely. Returns None if
    missing or malformed."""
    return _safe_load_json(Path(data_dir) / "liquidity_metrics.json")


def treasury_irrbb(
    data_dir: str | Path = "data",
) -> Optional[Dict[str, Any]]:
    """Load irrbb.json safely. Returns None if missing or
    malformed."""
    return _safe_load_json(Path(data_dir) / "irrbb.json")


def treasury_capital_adequacy(
    data_dir: str | Path = "data",
) -> Optional[Dict[str, Any]]:
    """Load capital_adequacy.json safely. Returns None if
    missing or malformed."""
    return _safe_load_json(Path(data_dir) / "capital_adequacy.json")


# ---------- Credit-specific composer ----------
# v10.300 — Credit live cockpit aggregator. Reads loan
# applications, IFRS9 stages, watchlist into a single dict
# for the cockpit headline tiles. Read-only; never mutates
# upstream data.

# Loan application states considered "open work" (non-terminal).
# Anything else (approved/rejected/funded/cancelled) is closed.
_LOAN_OPEN_LANES = {
    "pipeline", "review", "underwriting", "risk_review",
    "committee", "awaiting_docs", "pending",
    "in_progress", "intake",
}

# IFRS9 stage 3 — Non-Performing Loans per IAS / CBK Prudential.
# Stage classification is integer 1/2/3 in the standard schema.
_IFRS9_STAGE_NPL = 3


def _coerce_stage(raw: Any) -> Optional[int]:
    """IFRS9 stage values arrive as int OR string OR missing.
    Coerce to int 1/2/3 or None; the cockpit's stage counters
    skip records with non-coercible stages."""
    if raw is None:
        return None
    try:
        s = int(raw)
        if s in (1, 2, 3):
            return s
        return None
    except (ValueError, TypeError):
        return None


def _coerce_amount(raw: Any) -> float:
    """Outstanding amounts may be int, float, or numeric string.
    Coerce to float; non-coercible → 0.0 (legacy tolerance)."""
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


def credit_open_work(
    data_dir: str | Path = "data",
) -> Dict[str, Any]:
    """Aggregate bank-wide Credit work landscape.

    Reads loan_applications.json, ifrs9_loans.json, and
    credit_monitoring.json from `data_dir`. Returns a single
    dict with the headline counts the Credit cockpit
    displays.

    Read-only: never modifies any source file.
    Legacy-tolerant: missing or malformed files return sensible
    defaults; legacy record shapes (string stages, missing
    amounts) are counted in totals but skipped in stage-specific
    aggregates.

    Returns dict with documented keys:
      applications_total       — count of records in
                                  loan_applications.json
      applications_open        — applications in non-terminal
                                  swim_lane states
      applications_by_stage    — {swim_lane: count}
      ifrs9_total              — count of records in
                                  ifrs9_loans.json
      ifrs9_stage1             — performing loans
      ifrs9_stage2             — significant credit increase
      ifrs9_stage3             — NPL (Non-Performing Loans)
      npl_pct                  — Stage 3 outstanding ÷ total
                                  outstanding × 100. None if
                                  no records, 0.0 if no Stage 3.
      watchlist_count          — entries in monitoring watchlist
      as_at                    — ISO timestamp of THIS read
    """
    base = Path(data_dir)

    # ---- Loan applications ----
    apps = _safe_load_json(base / "loan_applications.json") or []
    if not isinstance(apps, list):
        apps = []
    apps_total = len(apps)
    apps_open = 0
    apps_by_stage: Dict[str, int] = {}
    for r in apps:
        if not isinstance(r, dict):
            continue
        lane = str(r.get("swim_lane", "")).lower() or "unknown"
        apps_by_stage[lane] = apps_by_stage.get(lane, 0) + 1
        if lane in _LOAN_OPEN_LANES:
            apps_open += 1

    # ---- IFRS9 loans ----
    loans = _safe_load_json(base / "ifrs9_loans.json") or []
    if not isinstance(loans, list):
        loans = []
    ifrs9_total = len(loans)
    stage1 = stage2 = stage3 = 0
    total_outstanding = 0.0
    stage3_outstanding = 0.0
    for r in loans:
        if not isinstance(r, dict):
            continue
        stage = _coerce_stage(r.get("stage"))
        amount = _coerce_amount(r.get("outstanding"))
        total_outstanding += amount
        if stage == 1:
            stage1 += 1
        elif stage == 2:
            stage2 += 1
        elif stage == 3:
            stage3 += 1
            stage3_outstanding += amount

    if total_outstanding > 0:
        npl_pct: Optional[float] = round(
            (stage3_outstanding / total_outstanding) * 100.0,
            2,
        )
    elif ifrs9_total == 0:
        npl_pct = None
    else:
        # We have loan records but no parseable outstanding
        # amounts — return None rather than misleading 0.
        npl_pct = None

    # ---- Watchlist ----
    monitoring = _safe_load_json(base / "credit_monitoring.json")
    watchlist_count = 0
    if isinstance(monitoring, dict):
        wl = monitoring.get("watchlist", [])
        if isinstance(wl, list):
            watchlist_count = len(wl)

    return {
        "applications_total": apps_total,
        "applications_open": apps_open,
        "applications_by_stage": apps_by_stage,
        "ifrs9_total": ifrs9_total,
        "ifrs9_stage1": stage1,
        "ifrs9_stage2": stage2,
        "ifrs9_stage3": stage3,
        "npl_pct": npl_pct,
        "watchlist_count": watchlist_count,
        "as_at": datetime.utcnow().isoformat(),
    }


def credit_loan_applications(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Safe loader for loan_applications.json. Returns empty
    list on missing or malformed file."""
    rec = _safe_load_json(Path(data_dir) / "loan_applications.json")
    return rec if isinstance(rec, list) else []


def credit_ifrs9_loans(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Safe loader for ifrs9_loans.json. Returns empty list on
    missing or malformed file."""
    rec = _safe_load_json(Path(data_dir) / "ifrs9_loans.json")
    return rec if isinstance(rec, list) else []


def credit_watchlist(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Safe loader for credit_monitoring.json watchlist.
    Returns empty list on missing or malformed file."""
    rec = _safe_load_json(Path(data_dir) / "credit_monitoring.json")
    if isinstance(rec, dict):
        wl = rec.get("watchlist", [])
        return wl if isinstance(wl, list) else []
    return []


# ---------- Compliance-specific composer ----------
# v10.301 — CMS arc cockpit aggregator. Record-registry pattern
# (CIMS-style): counts of work-in-progress across four
# regulatory registries (compliance cases, AML alerts,
# sanctions screening, regulatory returns). Read-only; never
# mutates state.

# Compliance case statuses considered closed (terminal). Anything
# else is open work.
_CASE_CLOSED_STATUSES = {
    "closed", "resolved", "cleared", "rejected", "dismissed",
}

# Sanctions screening statuses that have completed human review.
_SANCTIONS_TERMINAL_STATUSES = {
    "cleared", "confirmed", "rejected", "closed", "false_positive",
}


def _norm_status(raw: Any) -> str:
    """Normalise status string for case-insensitive comparison."""
    return str(raw or "").strip().lower()


def _norm_risk(raw: Any) -> str:
    """Normalise risk_level for case-insensitive comparison."""
    return str(raw or "").strip().lower()


def compliance_open_work(
    data_dir: str | Path = "data",
) -> Dict[str, Any]:
    """Aggregate bank-wide Compliance work landscape.

    Reads compliance_cases.json, aml_alerts.json,
    sanctions_register.json, and compliance.json (regulatory
    returns) from `data_dir`. Returns headline counts the
    Compliance cockpit shows.

    Read-only: never modifies any source file.
    Legacy-tolerant: missing fields are counted in totals but
    skipped from status/risk aggregates.

    Returns dict with documented keys:
      compliance_cases_total          — count of records in
                                         compliance_cases.json
      compliance_cases_open           — non-terminal statuses
      compliance_cases_by_risk        — {risk_level: count}
      aml_alerts_total                — aml_alerts.json count
      aml_alerts_open                 — non-closed alerts
      aml_alerts_high_risk            — open + high-risk
      sanctions_screening_total       — sanctions_register count
      sanctions_hits_pending_review   — non-terminal sanctions
                                         statuses (most reg-
                                         critical metric)
      regulatory_returns_total        — compliance.json count
      regulatory_returns_overdue      — past due_date + not filed
      regulatory_returns_on_time_pct  — filed-on-time / filed-
                                         total × 100 (None if
                                         no filed returns)
      as_at                           — ISO timestamp of THIS
                                         read
    """
    import datetime as _dt
    base = Path(data_dir)

    # ---- Compliance cases ----
    cases = _safe_load_json(base / "compliance_cases.json") or []
    if not isinstance(cases, list):
        cases = []
    cases_total = len(cases)
    cases_open = 0
    cases_by_risk: Dict[str, int] = {}
    for r in cases:
        if not isinstance(r, dict):
            continue
        status = _norm_status(r.get("status"))
        if status and status not in _CASE_CLOSED_STATUSES:
            cases_open += 1
        risk = _norm_risk(r.get("risk_level"))
        if risk:
            cases_by_risk[risk] = cases_by_risk.get(risk, 0) + 1

    # ---- AML alerts ----
    alerts = _safe_load_json(base / "aml_alerts.json") or []
    if not isinstance(alerts, list):
        alerts = []
    alerts_total = len(alerts)
    alerts_open = 0
    alerts_high = 0
    for r in alerts:
        if not isinstance(r, dict):
            continue
        status = _norm_status(r.get("status"))
        is_open = status and status not in _CASE_CLOSED_STATUSES
        if is_open:
            alerts_open += 1
            risk = _norm_risk(r.get("risk_level"))
            if risk == "high":
                alerts_high += 1

    # ---- Sanctions screening ----
    screenings = _safe_load_json(
        base / "sanctions_register.json") or []
    if not isinstance(screenings, list):
        screenings = []
    sanctions_total = len(screenings)
    sanctions_pending = 0
    for r in screenings:
        if not isinstance(r, dict):
            continue
        status = _norm_status(r.get("status"))
        if status and status not in _SANCTIONS_TERMINAL_STATUSES:
            sanctions_pending += 1

    # ---- Regulatory returns ----
    returns = _safe_load_json(base / "compliance.json") or []
    if not isinstance(returns, list):
        returns = []
    returns_total = len(returns)
    returns_overdue = 0
    on_time_filed = 0
    total_filed = 0
    today = _dt.date.today()
    for r in returns:
        if not isinstance(r, dict):
            continue
        status = _norm_status(r.get("status"))
        filed_date = r.get("filed_date")

        # Overdue detection: past due_date and not filed
        due_str = r.get("due_date")
        if due_str and not filed_date:
            try:
                due = _dt.date.fromisoformat(str(due_str)[:10])
                if due < today:
                    returns_overdue += 1
            except ValueError:
                pass

        # On-time metrics (only count filed returns)
        if status == "filed" and r.get("on_time") is not None:
            total_filed += 1
            if r.get("on_time"):
                on_time_filed += 1

    if total_filed > 0:
        on_time_pct: Optional[float] = round(
            (on_time_filed / total_filed) * 100.0, 2,
        )
    else:
        on_time_pct = None

    return {
        "compliance_cases_total": cases_total,
        "compliance_cases_open": cases_open,
        "compliance_cases_by_risk": cases_by_risk,
        "aml_alerts_total": alerts_total,
        "aml_alerts_open": alerts_open,
        "aml_alerts_high_risk": alerts_high,
        "sanctions_screening_total": sanctions_total,
        "sanctions_hits_pending_review": sanctions_pending,
        "regulatory_returns_total": returns_total,
        "regulatory_returns_overdue": returns_overdue,
        "regulatory_returns_on_time_pct": on_time_pct,
        "as_at": datetime.utcnow().isoformat(),
    }


def compliance_cases(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Safe loader for compliance_cases.json."""
    rec = _safe_load_json(Path(data_dir) / "compliance_cases.json")
    return rec if isinstance(rec, list) else []


def compliance_aml_alerts(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Safe loader for aml_alerts.json."""
    rec = _safe_load_json(Path(data_dir) / "aml_alerts.json")
    return rec if isinstance(rec, list) else []


def compliance_sanctions_screening(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Safe loader for sanctions_register.json."""
    rec = _safe_load_json(Path(data_dir) / "sanctions_register.json")
    return rec if isinstance(rec, list) else []


def compliance_regulatory_returns(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Safe loader for compliance.json (regulatory filings).

    v10.307 — Routes through `_load_table_via_shim` so the read
    path respects `_data_source.per_table.
    compliance_regulatory_returns` in
    integration_layer_config.json. Default behavior
    (no config) is unchanged: reads compliance.json directly.
    Setting per_table = "auto" or "pg_view" flips to PG.

    Note the file/table name discrepancy: the historical
    JSON file is `compliance.json` but the v10.306 PG table
    is `compliance_regulatory_returns` (matching the
    composer name). The shim handles the mapping.
    """
    return _load_table_via_shim(
        table="compliance_regulatory_returns",
        json_filename="compliance.json",
        data_dir=data_dir,
    )


# ---------- PG read-path cutover infrastructure (v10.307) ----------
# Bridges cockpit composers to the existing _data_source shim in
# utils.actuals_engine. The shim has been in place since v10.116;
# v10.307 is the first batch to route cockpit reads through it.
#
# Config knob (per-table, in data/integration_layer_config.json):
#   {
#     "_data_source": {
#       "default": "json"      | "pg_view" | "auto",
#       "per_table": {
#         "<table>": "json"    | "pg_view" | "auto"
#       }
#     }
#   }
#
# Modes:
#   json     — read JSON file only (legacy)
#   pg_view  — read PG only; empty list on failure (strict)
#   auto     — try PG first, fall back to JSON silently
#
# The cutover for a table is a one-line config edit. No code
# changes needed once the composer routes through the shim.

# Registry of tables that have a v10.306+ PG migration in place
# and are therefore safely flippable. Operators consult this via
# pg_capable_tables() to know what's ready for cutover.
_PG_CAPABLE_TABLES = frozenset({
    # v10.306 batch
    "audit_reviews",
    "compliance_regulatory_returns",
    "incidents",
    "nps_responses",
    "rcsa_register",
})


def pg_capable_tables() -> List[str]:
    """Return tables that have a PG migration in place and can
    be safely flipped from JSON to PG reads via the
    _data_source.per_table config.

    Future PG migration batches should add their tables here.
    """
    return sorted(_PG_CAPABLE_TABLES)


def _load_table_via_shim(
    table: str,
    json_filename: str | None = None,
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Load a list-of-dicts operational table via the
    _data_source shim from utils.actuals_engine.

    The shim handles JSON vs PG routing per the
    integration_layer_config.json `_data_source.per_table.<table>`
    config knob. Behavior matches `_safe_load_json` for the
    default-JSON case: returns [] for missing files, list of
    dicts for valid files.

    Args:
      table: the table name (matches PG table name + the key in
        per_table config)
      json_filename: if the source JSON file has a different name
        from the table (e.g. compliance.json → table
        compliance_regulatory_returns), pass it here. Defaults to
        f"{table}.json".
      data_dir: directory for both the JSON file and the config

    Returns:
      List of dict rows. Empty list on missing file, PG failure
      in strict mode, or unreadable JSON.
    """
    base = Path(data_dir)

    # Try the shim path — but only when the helper is available
    # and config is present. Falls through to direct JSON read
    # otherwise (the legacy path).
    try:
        from utils.actuals_engine import (
            _read_data_source_config, _try_read_from_pg_view,
        )
        cfg = _read_data_source_config(base)
        per_table = cfg.get("per_table", {})
        default = cfg.get("default", "json")
        mode = per_table.get(table, default)
    except Exception:
        mode = "json"

    if mode in ("pg_view", "auto"):
        try:
            from utils.actuals_engine import _try_read_from_pg_view
            rows = _try_read_from_pg_view(table)
            if rows is not None:
                return [r for r in rows if isinstance(r, dict)]
        except Exception:
            pass
        if mode == "pg_view":
            # Strict mode: caller asked for PG explicitly and we
            # couldn't produce data. Don't silently downgrade.
            return []
        # auto mode falls through to JSON read

    # Default / JSON fallback path
    filename = json_filename or f"{table}.json"
    rec = _safe_load_json(base / filename)
    if isinstance(rec, list):
        return [r for r in rec if isinstance(r, dict)]
    return []


# ---------- PG-routed composers for v10.306-migrated tables ----------
# v10.308 — fan-out from v10.307. Each composer is the cockpit/React
# entry point for one v10.306-migrated table. Same shape: route
# through _load_table_via_shim, default to JSON, opt into PG via
# per_table config.

def audit_reviews_records(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Audit review register (#201-#210). 250 production records.
    Source: data/audit_reviews.json. PG table: audit_reviews
    (v10.306). Flip to PG by setting per_table.audit_reviews =
    "auto" or "pg_view" in integration_layer_config.json."""
    return _load_table_via_shim(
        table="audit_reviews",
        data_dir=data_dir,
    )


def incidents_records(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """IT/Ops incident register. 80 production records.
    Source: data/incidents.json. PG table: incidents (v10.306).
    Used by IT&Digital + Observability modules."""
    return _load_table_via_shim(
        table="incidents",
        data_dir=data_dir,
    )


def nps_responses_records(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Customer NPS survey responses. 150 production records.
    Source: data/nps.json (file name predates table rename).
    PG table: nps_responses (v10.306). File/table name mismatch
    handled via json_filename parameter."""
    return _load_table_via_shim(
        table="nps_responses",
        json_filename="nps.json",
        data_dir=data_dir,
    )


def rcsa_register_records(
    data_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """Risk Control Self-Assessment register. 80 production
    records. Source: data/rcsa_register.json. PG table:
    rcsa_register (v10.306). Used by Risk module (#211-#220)."""
    return _load_table_via_shim(
        table="rcsa_register",
        data_dir=data_dir,
    )


# ---------- Cat A Portfolio Analytics composer (v10.309) ----------
# First multi-engine aggregation composer in Phase 3.
# Mirrors treasury_daily_report's shape: instantiate the engines,
# call each, return a section-shaped report.
#
# Composed engines (named in the v10.300 placeholder banner):
#   1. ai_underwriting.AIUnderwritingEngine (#119, #124)
#   2. credit_risk_scoring.CreditRiskScoringEngine (#119/#129)
#   3. credit_risk_irb.IRBCapitalEngine (Basel IRB capital)
#
# Each engine contributes one section. Empty/fresh engines
# return NO_DATA cleanly; errors degrade to status="error"
# rather than crashing the cockpit.

def credit_portfolio_analytics(
    data_dir: str | Path = "data",
) -> Dict[str, Any]:
    """Compose the Credit Portfolio Analytics report from
    three upstream engines. Closes the v10.300 placeholder in
    Credit cockpit page 111 tab 6.

    Sections returned (3, one per engine):

      ai_underwriting       — board_summary from #119/#124
      pd_distribution       — portfolio_pd_summary from #119/#129
      irb_capital           — compute_portfolio against the
                              IFRS9 loans portfolio

    Honest scope note: IFRS9 loans are mostly retail (Motor
    Vehicle, Personal, Salary, etc.). v10.313 (B-008 close)
    added retail ExposureClass values and a product_to_
    exposure_class mapper, so each loan is now dispatched to
    its proper Basel class instead of being mapped to
    SME_CORPORATE. The IRB section's notes now describe the
    actual class distribution rather than carrying a shape-
    fit caveat.

    Each section is defensive — engine failures degrade to
    status="error" with the exception message in notes. The
    composer always returns 3 sections.

    Returns dict:
      report_id      — "CPA-<as_of_date>"
      sections       — list of 3 section dicts
      n_sections     — 3
      board_summary  — entity name + simple aggregates
      status         — "ok" / "no_data" / "error" (top-level)
      as_at          — ISO timestamp of THIS read
    """
    import datetime as _dt
    from decimal import Decimal as _Decimal

    as_of_date = _dt.datetime.utcnow().date().isoformat()
    report_id = f"CPA-{as_of_date}"

    sections: List[Dict[str, Any]] = []

    # ---- Section 1: AI Underwriting board summary ----
    try:
        from utils.ai_underwriting import AIUnderwritingEngine
        eng = AIUnderwritingEngine()
        summary = eng.board_summary()
        n_dec = int(summary.get("n_decisions", 0))
        if n_dec == 0:
            section_1 = {
                "section_id": "ai_underwriting",
                "section_title": (
                    "AI Underwriting — #119 / #124"
                ),
                "source_engine": "ai_underwriting",
                "status": "no_data",
                "metrics": {},
                "notes": (
                    "AIUnderwritingEngine has no decisions "
                    "recorded yet. Call decide() to populate."
                ),
            }
        else:
            approve = summary.get("approve_pct", _Decimal(0))
            automation = summary.get(
                "automation_rate_pct", _Decimal(0))
            section_1 = {
                "section_id": "ai_underwriting",
                "section_title": (
                    "AI Underwriting — #119 / #124"
                ),
                "source_engine": "ai_underwriting",
                "status": "ok",
                "metrics": {
                    "n_decisions": str(n_dec),
                    "approve_pct": str(approve),
                    "decline_pct": str(
                        summary.get("decline_pct", 0)),
                    "refer_pct": str(
                        summary.get("refer_pct", 0)),
                    "automation_rate_pct": str(automation),
                    "model_card": str(
                        summary.get("model_card", "")),
                    "eu_ai_act_compliant": str(
                        summary.get(
                            "eu_ai_act_compliant", False)),
                },
                "notes": "",
            }
    except Exception as exc:
        section_1 = {
            "section_id": "ai_underwriting",
            "section_title": "AI Underwriting — #119 / #124",
            "source_engine": "ai_underwriting",
            "status": "error",
            "metrics": {},
            "notes": (
                f"AIUnderwritingEngine raised: {exc}"
            ),
        }
    sections.append(section_1)

    # ---- Section 2: PD distribution ----
    try:
        from utils.credit_risk_scoring import (
            CreditRiskScoringEngine,
        )
        eng = CreditRiskScoringEngine()
        pd_sum = eng.portfolio_pd_summary()
        n_loans = int(pd_sum.get("loan_count", 0))
        if n_loans == 0:
            section_2 = {
                "section_id": "pd_distribution",
                "section_title": (
                    "PD Distribution — #119 / #129"
                ),
                "source_engine": "credit_risk_scoring",
                "status": "no_data",
                "metrics": {},
                "notes": (
                    "CreditRiskScoringEngine has no scored "
                    "loans yet. Call score_borrower() to "
                    "populate."
                ),
            }
        else:
            by_grade = pd_sum.get("by_grade", {})
            section_2 = {
                "section_id": "pd_distribution",
                "section_title": (
                    "PD Distribution — #119 / #129"
                ),
                "source_engine": "credit_risk_scoring",
                "status": "ok",
                "metrics": {
                    "loan_count": str(n_loans),
                    "total_expected_loss": str(
                        pd_sum.get("total_expected_loss", 0),
                    ),
                    **{
                        f"grade_{k}_count": str(v)
                        for k, v in by_grade.items()
                    },
                },
                "notes": "",
            }
    except Exception as exc:
        section_2 = {
            "section_id": "pd_distribution",
            "section_title": "PD Distribution — #119 / #129",
            "source_engine": "credit_risk_scoring",
            "status": "error",
            "metrics": {},
            "notes": (
                f"CreditRiskScoringEngine raised: {exc}"
            ),
        }
    sections.append(section_2)

    # ---- Section 3: IRB capital from ifrs9_loans portfolio ----
    section_3 = _build_irb_section(data_dir=data_dir)
    sections.append(section_3)

    # ---- Aggregate top-level status ----
    statuses = [s["status"] for s in sections]
    if "error" in statuses:
        top_status = "error"
    elif all(st == "no_data" for st in statuses):
        top_status = "no_data"
    else:
        top_status = "ok"

    # ---- Aggregate board summary ----
    # Two simple totals from the sections that have them.
    total_loans = sections[1]["metrics"].get("loan_count", "0")
    irb_total_rwa = sections[2]["metrics"].get(
        "total_rwa_kes", "0")
    board_summary = {
        "entity": "credit_portfolio",
        "n_sections": len(sections),
        "n_loans_scored": total_loans,
        "irb_total_rwa_kes": irb_total_rwa,
    }

    return {
        "report_id": report_id,
        "sections": sections,
        "n_sections": len(sections),
        "board_summary": board_summary,
        "status": top_status,
        "as_at": datetime.utcnow().isoformat(),
    }


def _build_irb_section(
    data_dir: str | Path = "data",
) -> Dict[str, Any]:
    """Build the IRB capital section for credit_portfolio_
    analytics. Reads data/ifrs9_loans.json, dispatches each
    loan to the right Basel ExposureClass via
    product_to_exposure_class, and runs compute_portfolio.

    v10.313 (B-008 close): retail-aware dispatch replaces
    the v10.309 SME_CORPORATE shape-fit. Loans like
    `Motor Vehicle` / `Personal` / `Salary` go to OTHER_RETAIL;
    `Mortgage` / `Home Loan` go to RETAIL_RESIDENTIAL_MORTGAGE;
    `Credit Card` / `Overdraft` go to QUALIFYING_REVOLVING_
    RETAIL. Corporate products keep mapping to SME_CORPORATE
    or LARGE_CORPORATE.
    """
    try:
        from utils.credit_risk_irb import (
            IRBCapitalEngine, IRBExposure,
            product_to_exposure_class,
        )
    except Exception as exc:
        return {
            "section_id": "irb_capital",
            "section_title": "IRB Capital — Basel",
            "source_engine": "credit_risk_irb",
            "status": "error",
            "metrics": {},
            "notes": f"IRB engine import failed: {exc}",
        }

    # Load the IFRS9 loan portfolio as IRB exposures
    loans = _safe_load_json(
        Path(data_dir) / "ifrs9_loans.json") or []
    if not isinstance(loans, list) or not loans:
        return {
            "section_id": "irb_capital",
            "section_title": "IRB Capital — Basel",
            "source_engine": "credit_risk_irb",
            "status": "no_data",
            "metrics": {},
            "notes": (
                "No ifrs9_loans.json portfolio to compute "
                "IRB against."
            ),
        }

    # Convert IFRS9 rows to IRBExposure, dispatching each
    # to its proper Basel class via the product mapper.
    from decimal import Decimal as _Decimal
    exposures = []
    skipped = 0
    class_distribution: Dict[str, int] = {}
    for row in loans:
        if not isinstance(row, dict):
            skipped += 1
            continue
        try:
            ead = _Decimal(str(row.get("ead", 0)))
            pd = float(row.get("pd_12m", 0))
            lgd = float(row.get("lgd", 0))
            if ead <= 0 or pd <= 0 or lgd <= 0:
                skipped += 1
                continue
            # v10.313: dispatch on product string
            product = str(row.get("product", ""))
            exposure_class = product_to_exposure_class(product)
            class_distribution[exposure_class.value] = (
                class_distribution.get(
                    exposure_class.value, 0) + 1)
            exposures.append(IRBExposure(
                exposure_id=str(row.get("account_id", "")),
                exposure_class=exposure_class,
                pd=pd,
                lgd=lgd,
                ead_kes=ead,
                maturity_years=1.0,
                notes=(
                    f"product={product} "
                    f"stage={row.get('stage', '')}"
                ),
            ))
        except Exception:
            skipped += 1
            continue

    if not exposures:
        return {
            "section_id": "irb_capital",
            "section_title": "IRB Capital — Basel",
            "source_engine": "credit_risk_irb",
            "status": "no_data",
            "metrics": {},
            "notes": (
                f"No valid exposures derivable from "
                f"ifrs9_loans.json ({skipped} skipped)"
            ),
        }

    try:
        eng = IRBCapitalEngine()
        results, total_rwa, total_el = eng.compute_portfolio(
            exposures,
        )
        # Build a compact class-distribution string for notes
        class_dist_str = ", ".join(
            f"{k}={v}" for k, v in sorted(
                class_distribution.items(),
                key=lambda kv: -kv[1])
        )
        metrics = {
            "n_exposures": str(len(exposures)),
            "n_skipped": str(skipped),
            "total_rwa_kes": str(total_rwa),
            "total_el_kes": str(total_el),
        }
        # Also surface the distribution as per-class counts
        for class_name, count in class_distribution.items():
            metrics[f"class_{class_name}_count"] = str(count)
        return {
            "section_id": "irb_capital",
            "section_title": "IRB Capital — Basel",
            "source_engine": "credit_risk_irb",
            "status": "ok",
            "metrics": metrics,
            "notes": (
                f"v10.313: retail-aware Basel dispatch. "
                f"Class distribution: {class_dist_str}. "
                f"Data caveat: the IFRS9 `product` field "
                f"often holds collateral type (Land Title, "
                f"Shares, Cash Deposit) rather than loan "
                f"product, so loans with non-retail product "
                f"strings fall back to SME_CORPORATE — "
                f"better source data would shift more loans "
                f"to retail classes. Maturity defaulted to "
                f"1.0y (IFRS9 lacks remaining-term field)."
            ),
        }
    except Exception as exc:
        return {
            "section_id": "irb_capital",
            "section_title": "IRB Capital — Basel",
            "source_engine": "credit_risk_irb",
            "status": "error",
            "metrics": {},
            "notes": f"compute_portfolio raised: {exc}",
        }


# ---------- Cat A Compliance CRA + Training composer (v10.310) ----
# Second Cat A composer. Closes the last placeholder banner across
# the cockpit estate (Compliance page 112 tab 6).
#
# Composes the two engines explicitly named in the v10.301
# placeholder:
#   1. compliance_risk_assessment.ComplianceRiskAssessmentEngine
#      (#198) — CRA scoring state
#   2. compliance_training.ComplianceTrainingEngine (#197) —
#      training assignment + certification state
#
# Same section-shaped report pattern as
# credit_portfolio_analytics (v10.309). Each engine's
# board_summary() return is mapped into a section with
# {section_id, section_title, source_engine, status, metrics,
#  notes}.

# Top-level metric keys from each engine's board_summary that
# the composer surfaces explicitly. Other keys go into a
# meta_keys count + the notes line (rather than flooding the
# UI with verbose regulatory-basis strings).
_CRA_SCALAR_METRICS = ("entity", "engine", "n_assessments")
_TRAINING_SCALAR_METRICS = (
    "entity", "engine",
    "n_courses_total", "n_courses_published",
    "n_assignments_total", "n_assignments_completed",
    "n_assignments_failed", "n_assignments_overdue",
    "n_certifications_expiring_30d",
    "n_active_certifications",
)


def compliance_cra_training(
    data_dir: str | Path = "data",
) -> Dict[str, Any]:
    """Compose the Compliance Risk Assessment + Training
    report from two upstream engines. Closes the v10.301
    placeholder in Compliance cockpit page 112 tab 6.

    Sections returned (2, one per engine):

      compliance_risk_assessment  — board_summary from #198
      compliance_training         — board_summary from #197

    Same shape contract as credit_portfolio_analytics (v10.309):
    each section has section_id, section_title, source_engine,
    status, metrics (str → str), notes.

    Defensive on each engine call — failures degrade that
    section to status="error", other section still renders.
    Composer always returns 2 sections.

    `data_dir` accepted for shape parity with other composers
    but isn't used today (both engines are pure in-memory at
    instantiation — no JSON files read). Reserved for when
    persistence wraps these engines.
    """
    sections: List[Dict[str, Any]] = []
    sections.append(_build_cra_section())
    sections.append(_build_training_section())

    # ---- Top-level status aggregation (same shape as v10.309)
    statuses = [s["status"] for s in sections]
    if "error" in statuses:
        top_status = "error"
    elif all(st == "no_data" for st in statuses):
        top_status = "no_data"
    else:
        top_status = "ok"

    # ---- Board summary
    cra_assessments = sections[0]["metrics"].get(
        "n_assessments", "0")
    training_assignments = sections[1]["metrics"].get(
        "n_assignments_total", "0")
    training_overdue = sections[1]["metrics"].get(
        "n_assignments_overdue", "0")

    board_summary = {
        "entity": "compliance_cra_training",
        "n_sections": len(sections),
        "n_cra_assessments": cra_assessments,
        "n_training_assignments": training_assignments,
        "n_training_overdue": training_overdue,
    }

    import datetime as _dt
    as_of_date = _dt.datetime.utcnow().date().isoformat()

    return {
        "report_id": f"CCT-{as_of_date}",
        "sections": sections,
        "n_sections": len(sections),
        "board_summary": board_summary,
        "status": top_status,
        "as_at": datetime.utcnow().isoformat(),
    }


def _build_cra_section() -> Dict[str, Any]:
    """Build the Compliance Risk Assessment section for
    compliance_cra_training. Wraps
    ComplianceRiskAssessmentEngine.board_summary()."""
    try:
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine,
        )
    except Exception as exc:
        return {
            "section_id": "compliance_risk_assessment",
            "section_title": (
                "Compliance Risk Assessment — #198"
            ),
            "source_engine": "compliance_risk_assessment",
            "status": "error",
            "metrics": {},
            "notes": f"engine import failed: {exc}",
        }

    try:
        eng = ComplianceRiskAssessmentEngine()
        summary = eng.board_summary()
    except Exception as exc:
        return {
            "section_id": "compliance_risk_assessment",
            "section_title": (
                "Compliance Risk Assessment — #198"
            ),
            "source_engine": "compliance_risk_assessment",
            "status": "error",
            "metrics": {},
            "notes": f"board_summary raised: {exc}",
        }

    n_assess = int(summary.get("n_assessments", 0))

    # Build the metric dict — only scalar keys, everything as
    # string for JSON-serialisability
    metrics: Dict[str, str] = {}
    for k in _CRA_SCALAR_METRICS:
        if k in summary:
            metrics[k] = str(summary[k])

    # Surface the latest assessment if present
    latest = summary.get("latest")
    if latest is not None:
        metrics["latest_assessment"] = str(latest)

    # Compose the notes — combine trend status + regulatory basis
    notes_parts: List[str] = []
    if n_assess == 0:
        notes_parts.append(
            "No CRA assessments recorded yet. Call assess() "
            "to populate."
        )
    trend_status = summary.get("trend_analysis_status", "")
    if trend_status:
        # Keep this short — the full string is verbose
        notes_parts.append(
            "Trend analysis status: " +
            (trend_status[:120] + "…"
             if len(trend_status) > 120 else trend_status)
        )
    reg_basis = summary.get("regulatory_basis", "")
    if reg_basis:
        notes_parts.append(
            f"Regulatory basis: {reg_basis}"
        )
    notes = " | ".join(notes_parts)

    status = "no_data" if n_assess == 0 else "ok"

    return {
        "section_id": "compliance_risk_assessment",
        "section_title": "Compliance Risk Assessment — #198",
        "source_engine": "compliance_risk_assessment",
        "status": status,
        "metrics": metrics,
        "notes": notes,
    }


def _build_training_section() -> Dict[str, Any]:
    """Build the Compliance Training section. Wraps
    ComplianceTrainingEngine.board_summary()."""
    try:
        from utils.compliance_training import (
            ComplianceTrainingEngine,
        )
    except Exception as exc:
        return {
            "section_id": "compliance_training",
            "section_title": (
                "Compliance Training — #197"
            ),
            "source_engine": "compliance_training",
            "status": "error",
            "metrics": {},
            "notes": f"engine import failed: {exc}",
        }

    try:
        eng = ComplianceTrainingEngine()
        summary = eng.board_summary()
    except Exception as exc:
        return {
            "section_id": "compliance_training",
            "section_title": "Compliance Training — #197",
            "source_engine": "compliance_training",
            "status": "error",
            "metrics": {},
            "notes": f"board_summary raised: {exc}",
        }

    metrics: Dict[str, str] = {}
    for k in _TRAINING_SCALAR_METRICS:
        if k in summary:
            metrics[k] = str(summary[k])

    n_assignments = int(summary.get("n_assignments_total", 0))
    n_courses = int(summary.get("n_courses_total", 0))
    n_overdue = int(summary.get("n_assignments_overdue", 0))

    # Status logic:
    #   no_data if both courses + assignments are zero
    #   warning if there are overdue assignments
    #   ok otherwise
    if n_courses == 0 and n_assignments == 0:
        status = "no_data"
    elif n_overdue > 0:
        status = "warning"
    else:
        status = "ok"

    # Notes — combine LMS status + course content status
    # + regulatory basis. Trim verbose strings.
    notes_parts: List[str] = []
    if status == "no_data":
        notes_parts.append(
            "No courses or assignments recorded yet. Call "
            "publish_course() / assign() / complete() to "
            "populate."
        )
    if n_overdue > 0:
        notes_parts.append(
            f"{n_overdue} overdue assignment(s) — escalation "
            f"to L&D + compliance officer recommended."
        )
    lms_status = summary.get("lms_integration_status", "")
    if lms_status:
        notes_parts.append(
            "LMS integration: " +
            (lms_status[:120] + "…"
             if len(lms_status) > 120 else lms_status)
        )
    course_status = summary.get("course_content_status", "")
    if course_status:
        notes_parts.append(
            "Course content: " +
            (course_status[:120] + "…"
             if len(course_status) > 120 else course_status)
        )
    reg_basis = summary.get("regulatory_basis", "")
    if reg_basis:
        notes_parts.append(
            f"Regulatory basis: {reg_basis}"
        )
    notes = " | ".join(notes_parts)

    return {
        "section_id": "compliance_training",
        "section_title": "Compliance Training — #197",
        "source_engine": "compliance_training",
        "status": status,
        "metrics": metrics,
        "notes": notes,
    }


# ---------- Treasury daily report composer (v10.302) ----------
# Wraps the now-wired TreasuryDashboardEngine so the React SPA
# can fetch the same daily treasury pack the Streamlit cockpit
# renders. Single source of truth.

def treasury_daily_report(
    as_of_date: str | None = None,
) -> Dict[str, Any]:
    """Compose the daily treasury report via a wired
    TreasuryDashboardEngine. Returns a JSON-serialisable dict
    suitable for cockpit display and HTTP transport.

    `as_of_date` defaults to today (UTC). Pass YYYY-MM-DD to
    pin to a historical date.

    Return shape:
      report_id        — e.g. "DAILY-2026-05-11"
      as_of_date       — the date passed in / today
      n_sections       — number of sections in the report
      sections         — list of dicts with section_id, title,
                          source_engine, status, metrics,
                          thresholds, headroom, notes
      board_summary    — TreasuryDashboardEngine.board_summary()
                          dict (entity + wiring flags +
                          n_reports_generated)
      as_at            — ISO timestamp of THIS read
    """
    from utils.treasury_dashboard_wiring import (
        make_wired_dashboard,
    )

    if as_of_date is None:
        as_of_date = datetime.utcnow().date().isoformat()

    dash = make_wired_dashboard()
    report_id = f"DAILY-{as_of_date}"

    try:
        report = dash.generate_daily_treasury(
            report_id=report_id,
            as_of_date=as_of_date,
        )
    except Exception as exc:
        # Defensive: the wired engines may raise on a
        # bad-data day. Return a structured error rather than
        # crashing the cockpit.
        return {
            "report_id": report_id,
            "as_of_date": as_of_date,
            "n_sections": 0,
            "sections": [],
            "board_summary": dash.board_summary(),
            "error": str(exc),
            "as_at": datetime.utcnow().isoformat(),
        }

    sections: List[Dict[str, Any]] = []
    for s in report.sections:
        # Sections use Decimal-valued dicts for precision; cast
        # to str/dict so the structure is JSON-serialisable.
        sections.append({
            "section_id": s.section_id,
            "section_title": s.section_title,
            "source_engine": s.source_engine,
            "status": (
                s.status.value
                if hasattr(s.status, "value")
                else str(s.status)
            ),
            "metrics": {k: str(v)
                        for k, v in (s.metrics or {}).items()},
            "thresholds": {k: str(v)
                            for k, v in (s.thresholds or {}).items()},
            "headroom": {k: str(v)
                          for k, v in (getattr(s, "headroom",
                                                 {}) or {}).items()},
            "notes": s.notes,
        })

    return {
        "report_id": (
            report.report_id if hasattr(report, "report_id")
            else report_id
        ),
        "as_of_date": as_of_date,
        "n_sections": len(sections),
        "sections": sections,
        "board_summary": dash.board_summary(),
        "as_at": datetime.utcnow().isoformat(),
    }


# ---------- Cash forecast composer (v10.304) ----------
# Wraps the now-primed TreasuryCashForecastingEngine so the
# React SPA + Streamlit cockpit both render the same 13-week
# projection. Single source of truth.

def treasury_cash_forecast(
    horizon_days: int = 91,
    start_date: str | None = None,
) -> Dict[str, Any]:
    """Compose the bank-wide cash forecast for the next
    `horizon_days`. Default horizon is 91 days (13 weeks) to
    match the cockpit tab title.

    Returns a JSON-serialisable dict:
      entity                — bank entity name from engine
      forecast_id           — generated ID for this read
      horizon_days          — actual horizon used
      start_date            — start date (default: today UTC)
      n_history_days_used   — engine input depth
      ml_overlay_applied    — bool, true if ML provider wired
      n_points              — number of daily points returned
      points                — list of daily forecast dicts
                              with date + total_kes + bands
      status                — "ok" | "no_data" | "error"
      notes                 — engine-side narrative
      as_at                 — ISO timestamp of THIS read

    NO_DATA shape: when the engine has no history or no
    seasonality model, the composer returns a well-formed dict
    with `status: "no_data"`, empty points list, and a notes
    field explaining what's missing. The React SPA can render
    a placeholder without handling two response shapes.
    """
    if start_date is None:
        start_date = datetime.utcnow().date().isoformat()

    forecast_id = f"FC-{start_date}-{horizon_days}d"

    try:
        from utils.cash_forecast_wiring import (
            make_primed_forecaster,
        )
    except Exception as exc:
        return {
            "entity": "unknown",
            "forecast_id": forecast_id,
            "horizon_days": horizon_days,
            "start_date": start_date,
            "n_history_days_used": 0,
            "ml_overlay_applied": False,
            "n_points": 0,
            "points": [],
            "status": "error",
            "notes": f"wiring import failed: {exc}",
            "as_at": datetime.utcnow().isoformat(),
        }

    fc = make_primed_forecaster()
    summary = fc.board_summary()

    # If engine has no history, it can't fit seasonality →
    # forecast call would fail. Surface a clean NO_DATA shape.
    if summary.get("n_history_days", 0) == 0:
        return {
            "entity": summary.get("entity", "unknown"),
            "forecast_id": forecast_id,
            "horizon_days": horizon_days,
            "start_date": start_date,
            "n_history_days_used": 0,
            "ml_overlay_applied": False,
            "n_points": 0,
            "points": [],
            "status": "no_data",
            "notes": (
                "Cash forecasting engine has no historical net-"
                "flow data. Provide data/cash_history.json with "
                "{observation_date, net_flow_kes, notes} records "
                "to enable the 13-week projection."
            ),
            "as_at": datetime.utcnow().isoformat(),
        }

    # We have history — try to fit a seasonality model and
    # produce a forecast. Best-effort: errors degrade to
    # status=error rather than crashing the cockpit.
    try:
        seasonality_model_id = "cockpit-default"
        fc.fit_seasonality(model_id=seasonality_model_id)
        result = fc.forecast(
            forecast_id=forecast_id,
            start_date=start_date,
            horizon_days=horizon_days,
            seasonality_model_id=seasonality_model_id,
        )
    except Exception as exc:
        return {
            "entity": summary.get("entity", "unknown"),
            "forecast_id": forecast_id,
            "horizon_days": horizon_days,
            "start_date": start_date,
            "n_history_days_used": summary.get(
                "n_history_days", 0),
            "ml_overlay_applied": False,
            "n_points": 0,
            "points": [],
            "status": "error",
            "notes": f"forecast call failed: {exc}",
            "as_at": datetime.utcnow().isoformat(),
        }

    # Cast all Decimals to str for JSON serialisability —
    # React's parseFloat handles the conversion on the
    # frontend, or the value can be displayed as-is.
    points: List[Dict[str, Any]] = []
    for p in result.points:
        points.append({
            "forecast_date": p.forecast_date,
            "deterministic_kes": str(p.deterministic_kes),
            "baseline_kes": str(p.baseline_kes),
            "seasonality_multiplier": str(
                p.seasonality_multiplier),
            "statistical_kes": str(p.statistical_kes),
            "total_kes": str(p.total_kes),
            "band_low_80": str(p.band_low_80),
            "band_high_80": str(p.band_high_80),
            "band_low_95": str(p.band_low_95),
            "band_high_95": str(p.band_high_95),
            "drivers_summary": p.drivers_summary,
        })

    return {
        "entity": summary.get("entity", "unknown"),
        "forecast_id": result.forecast_id,
        "horizon_days": result.horizon_days,
        "start_date": result.start_date,
        "n_history_days_used": result.n_history_days_used,
        "ml_overlay_applied": result.ml_overlay_applied,
        "n_points": len(points),
        "points": points,
        "status": "ok",
        "notes": result.notes or "",
        "as_at": datetime.utcnow().isoformat(),
    }


# ---------- Audit trail composer (v10.305) ----------
# Single composer reading data/audit_log.json with filters.
# Used by Credit cockpit tab 7, Compliance cockpit tab 7, and
# the React SPA via /api/cockpit/audit/log. CIMS cockpit tab 7
# uses its module-specific #176 history (cims_audit_history.
# json) — different file, different schema, out of scope here.

def audit_log_records(
    data_dir: str | Path = "data",
    *,
    action: str | None = None,
    module: str | None = None,
    user: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Read filtered audit log records from data/audit_log.json.

    Filters apply AND-wise. All are case-sensitive exact matches
    on the corresponding record field. Date filters compare
    ISO-formatted `ts` strings.

    Records returned most-recent-first by `ts`. `limit` caps
    the response size so the API doesn't ship 1M records to a
    React component — but `count` reports the unlimited
    filtered total so the UI can render "showing 100 of N".

    Args:
      data_dir: directory containing audit_log.json
      action: filter to records where record["action"] == this
      module: filter to records where record["module"] == this
      user: filter to records where record["user"] == this
      since: only records with ts >= this (ISO string)
      until: only records with ts <= this (ISO string)
      limit: cap on response records (default 100, min 1, no
        max — caller responsible for sensible values)

    Returns dict:
      records: list of audit records (length ≤ limit)
      count: filtered total (may exceed len(records))
      filters: dict of the filters that were applied
      as_at: ISO timestamp of THIS read
    """
    base = Path(data_dir)
    raw = _safe_load_json(base / "audit_log.json")
    records: List[Dict[str, Any]] = (
        raw if isinstance(raw, list) else []
    )

    # Apply filters in sequence. Skip non-dict rows safely.
    def _matches(r: Any) -> bool:
        if not isinstance(r, dict):
            return False
        if action is not None and r.get("action") != action:
            return False
        if module is not None and r.get("module") != module:
            return False
        if user is not None and r.get("user") != user:
            return False
        if since is not None:
            ts = r.get("ts", "")
            if not ts or ts < since:
                return False
        if until is not None:
            ts = r.get("ts", "")
            if not ts or ts > until:
                return False
        return True

    filtered = [r for r in records if _matches(r)]

    # Sort most-recent-first by ts (string comparison works for
    # ISO 8601 timestamps).
    try:
        filtered.sort(
            key=lambda r: r.get("ts", ""),
            reverse=True,
        )
    except Exception:
        # Defensive — if any row has non-comparable ts, keep
        # input order rather than crashing.
        pass

    # Defensive limit clamp.
    if limit < 1:
        limit = 1

    return {
        "records": filtered[:limit],
        "count": len(filtered),
        "filters": {
            "action": action,
            "module": module,
            "user": user,
            "since": since,
            "until": until,
            "limit": limit,
        },
        "as_at": datetime.utcnow().isoformat(),
    }


def _self_test() -> None:
    """No assertions on data shape — module is a thin read layer.
    Smoke-test that all functions are callable and return the
    documented types when handed empty inputs.
    """
    assert load_records("nonexistent.json", "x", ("y",)) == []
    assert filter_records([]) == []
    assert sort_records([]) == []
    assert group_by([], "field") == {}
    assert count_by([], "field") == {}
    assert find_by_id([], "id", "x") is None
    assert latest_n([], n=10) == []

    # Smoke composers with empty data dir
    trace = cims_instruction_trace("X", data_dir="/nonexistent")
    assert trace["linked_session_id"] == "X"
    assert trace["capture"] is None
    assert trace["history"] == []

    snapshot = cims_open_work(data_dir="/nonexistent")
    assert snapshot["open_capture_sessions"] == 0
    assert snapshot["pending_nlp"] == 0
    assert snapshot["recent_open_sessions"] == []

    print("  ✅ cockpit_read self-test PASS")


if __name__ == "__main__":
    _self_test()
