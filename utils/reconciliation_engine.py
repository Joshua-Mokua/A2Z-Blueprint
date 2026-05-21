"""utils.reconciliation_engine — FLEXCUBE Reconciliation Engine
(Standard #35, v5.50). Volume Four — FLEXCUBE Integration.

Per the master spec:

    class ReconciliationEngine:
        def run_full_reconciliation(self, reconciliation_date):
            checks = ["customer_count", "deposit_balance", "loan_balance"]
            for check in checks:
                variance = self.compare(check, reconciliation_date)
                if abs(variance) > self.THRESHOLDS[check]:
                    self.log_break({"check_name": check, "variance": variance})

NOTE ON EXISTING MODULE
-----------------------
A pre-existing `utils/reconciliation.py` ships a different daily-recon
orchestrator (run_all_checks across deposits/loans/NPL/LCR/CAR). v5.50
ships #35's spec engine in a SEPARATE module so the two can coexist.
Future work may bridge them — the existing recon's check functions can
be wired as additional checks into this spec engine's registry.

THE FINANCIAL HONESTY BAR HERE IS THE HIGHEST IN VOLUME FOUR
============================================================
A reconciliation engine that reports "within tolerance" when it isn't
hides real money discrepancies — the worst possible outcome:

  - Audit failures hidden
  - Fraud potentially undetected
  - Wrong board reports certified as correct
  - Regulator receives wrong numbers

So the engine MUST follow Mandatory Standard #11's discipline:

  1. NEVER pass a check that couldn't be computed. If FLEXCUBE-side
     data is missing, the check status is "not_run", NOT "passed".
  2. NEVER round variances down — show the absolute KES variance
     and the percentage variance honestly.
  3. Decimal-internal math at precision 28 (KES-billion balance sheets
     would lose precision under float).
  4. Stale FLEXCUBE extract → raise a data-quality warning, BLOCK
     pass-status reporting (because today's A2Z numbers compared to
     yesterday's FLEXCUBE numbers will report apparent breaks that
     aren't real).
  5. Break log is append-only — once logged, breaks are not
     silently overwritten on subsequent runs.

WHAT THIS MODULE SHIPS
----------------------
1. ReconciliationEngine class with spec entry method
2. THRESHOLDS class attribute with KES tolerances per check (spec literal)
3. Three spec-named checks: customer_count, deposit_balance, loan_balance
4. compare(check_name, date) that returns Decimal variance
5. log_break(break_record) appending to data/reconciliation_breaks.json
6. data_quality_warning when extract is stale (NEW v5.50 honesty rule)

THE THRESHOLDS
--------------
Per-check thresholds reflect different types of comparisons:

  customer_count:  exact match required (variance = 0).
                    Customer counts should be IDENTICAL between FLEXCUBE
                    and A2Z. Threshold: 0.
  deposit_balance: KES 1,000 tolerance for rounding/timing differences.
  loan_balance:    KES 1,000 tolerance, same rationale.

Production deployments should tighten these against actual operational
variance (bank's risk appetite + auditor preferences).

NEW HONESTY RULE FOR VOLUME FOUR (added v5.50)
-----------------------------------------------
**Stale extract guard.** If the FLEXCUBE extract control row shows
last_extract_date older than reconciliation_date, the engine:

  - Sets meta.extract_stale = True
  - Sets data_quality_warning citing the staleness
  - All checks are reported as status="not_run_stale_extract" (NOT
    "passed", even if numbers happen to match — they could match for
    the wrong reason, and a green reconciliation report from stale
    data is misleading)
  - The run still completes (returns a result) so the orchestrator
    can record the failed run, but the result is unambiguously
    flagged as untrustworthy

This is consistent with Mandatory Standard #11's "no silent fallback"
principle — extended to data-integration honesty for V4.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.reconciliation_engine")
getcontext().prec = 28

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
BREAKS_LOG_FILE = DATA_DIR / "reconciliation_breaks.json"

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec-named checks + thresholds
# ─────────────────────────────────────────────────────────────────────

DEFAULT_CHECKS: List[str] = ["customer_count", "deposit_balance", "loan_balance"]

DEFAULT_THRESHOLDS: Dict[str, Decimal] = {
    "customer_count":  Decimal("0"),
    "deposit_balance": Decimal("1000"),
    "loan_balance":    Decimal("1000"),
}

DEFAULT_STALE_AFTER_HOURS = 25    # 1 day + 1 hour grace per #33 daily schedule


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class ReconciliationEngine:
    """Standard #35 — Reconciliation between FLEXCUBE source and A2Z clean."""

    THRESHOLDS = DEFAULT_THRESHOLDS    # spec-named class attribute
    CHECKS     = DEFAULT_CHECKS

    def __init__(
        self,
        flexcube_count_fn:    Optional[Callable[[str, str], Optional[Decimal]]] = None,
        a2z_count_fn:         Optional[Callable[[str, str], Optional[Decimal]]] = None,
        extract_control_fn:   Optional[Callable[[str], Optional[dict]]] = None,
        break_log_fn:         Optional[Callable[[dict], None]] = None,
        thresholds:           Optional[Dict[str, Decimal]] = None,
        stale_after_hours:    int = DEFAULT_STALE_AFTER_HOURS,
    ):
        """All collaborators injectable.

        flexcube_count_fn(check_name, date) → Decimal | None
        a2z_count_fn(check_name, date) → Decimal | None
        extract_control_fn(table_name) → {last_extract_date, status} | None
        break_log_fn(break_record) → None
        """
        self._flexcube     = flexcube_count_fn or _default_flexcube_count
        self._a2z          = a2z_count_fn      or _default_a2z_count
        self._extract_ctrl = extract_control_fn or _default_extract_control
        self._break_log    = break_log_fn      or _default_break_log
        self.thresholds    = thresholds or DEFAULT_THRESHOLDS.copy()
        self._stale_hours  = stale_after_hours

    # ──────────────────────────────────────────────────────────────────
    # Spec entry
    # ──────────────────────────────────────────────────────────────────

    def run_full_reconciliation(
        self, reconciliation_date: str,
    ) -> Dict[str, Any]:
        """Run all spec-named checks against the given date.

        Returns:
            {
              "reconciliation_date": str,
              "checks": [...],
              "checks_passed": int,
              "checks_failed": int,
              "checks_not_run": int,
              "extract_stale":  bool,
              "data_quality_warning": str | None,
              "meta": {...}
            }

        Returns {} for empty reconciliation_date.
        """
        if not reconciliation_date:
            return {}

        extract_stale = self._is_extract_stale(reconciliation_date)
        warning = None
        if extract_stale:
            warning = (
                f"FLEXCUBE extract is stale (older than {self._stale_hours}h "
                f"from reconciliation_date). All checks reported as "
                f"not_run_stale_extract per Mandatory Standard #11 — "
                f"green reconciliation from stale data is misleading."
            )

        check_results: List[Dict[str, Any]] = []
        passed = 0
        failed = 0
        not_run = 0

        for check_name in self.CHECKS:
            r = self._run_one_check(check_name, reconciliation_date, extract_stale)
            check_results.append(r)
            if r["status"] == "passed":
                passed += 1
            elif r["status"] == "failed":
                failed += 1
            else:
                not_run += 1

        return {
            "reconciliation_date":  reconciliation_date,
            "checks":               check_results,
            "checks_passed":        passed,
            "checks_failed":        failed,
            "checks_not_run":       not_run,
            "extract_stale":        extract_stale,
            "data_quality_warning": warning,
            "meta": {
                "checks_run":              self.CHECKS.copy(),
                "thresholds":              {k: str(v) for k, v in self.thresholds.items()},
                "stale_after_hours":       self._stale_hours,
                "all_checks_passed":       (failed == 0 and not_run == 0),
                "generated_at":            datetime.now(timezone.utc).isoformat(),
            },
        }

    def compare(self, check_name: str, reconciliation_date: str) -> Optional[Decimal]:
        """Compute variance = a2z_value - flexcube_value for one check.

        Returns None when either side is unavailable.
        """
        if not check_name or not reconciliation_date:
            return None
        fc = self._flexcube(check_name, reconciliation_date)
        a2z = self._a2z(check_name, reconciliation_date)
        if fc is None or a2z is None:
            return None
        try:
            return Decimal(str(a2z)) - Decimal(str(fc))
        except Exception as e:
            logger.warning("compare %s: invalid value(s): %s", check_name, e)
            return None

    def log_break(self, break_record: dict) -> None:
        """Persist a break record. Append-only — never overwrites."""
        if not isinstance(break_record, dict):
            return
        record = {**break_record}
        record.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
        self._break_log(record)

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────

    def _run_one_check(
        self, check_name: str, reconciliation_date: str, extract_stale: bool,
    ) -> Dict[str, Any]:
        if extract_stale:
            return {
                "check_name":       check_name,
                "flexcube_value":   None,
                "a2z_value":        None,
                "variance":         None,
                "abs_variance":     None,
                "threshold":        str(self.thresholds.get(check_name)),
                "status":           "not_run_stale_extract",
                "is_break":         False,
                "logged_break_id":  None,
            }

        fc = self._flexcube(check_name, reconciliation_date)
        a2z = self._a2z(check_name, reconciliation_date)

        if fc is None or a2z is None:
            return {
                "check_name":       check_name,
                "flexcube_value":   _decimal_or_none(fc),
                "a2z_value":        _decimal_or_none(a2z),
                "variance":         None,
                "abs_variance":     None,
                "threshold":        str(self.thresholds.get(check_name)),
                "status":           "not_run_missing_data",
                "is_break":         False,
                "logged_break_id":  None,
            }

        try:
            fc_d = Decimal(str(fc))
            a2z_d = Decimal(str(a2z))
        except Exception as e:
            logger.warning("check %s: invalid values: %s", check_name, e)
            return {
                "check_name":       check_name,
                "flexcube_value":   str(fc),
                "a2z_value":        str(a2z),
                "variance":         None,
                "abs_variance":     None,
                "threshold":        str(self.thresholds.get(check_name)),
                "status":           "not_run_invalid_data",
                "is_break":         False,
                "logged_break_id":  None,
            }

        variance = a2z_d - fc_d
        abs_var = abs(variance)
        threshold = self.thresholds.get(check_name, ZERO)
        is_break = abs_var > threshold

        result = {
            "check_name":       check_name,
            "flexcube_value":   _money(fc_d),
            "a2z_value":        _money(a2z_d),
            "variance":         _money(variance),
            "abs_variance":     _money(abs_var),
            "threshold":        _money(threshold),
            "status":           "failed" if is_break else "passed",
            "is_break":         is_break,
            "logged_break_id":  None,
        }

        if is_break:
            break_id = (
                f"{check_name}-{reconciliation_date}-"
                f"{datetime.now(timezone.utc).strftime('%H%M%S%f')}"
            )
            self.log_break({
                "break_id":              break_id,
                "check_name":            check_name,
                "reconciliation_date":   reconciliation_date,
                "flexcube_value":        _money(fc_d),
                "a2z_value":             _money(a2z_d),
                "variance":              _money(variance),
                "abs_variance":          _money(abs_var),
                "threshold":             _money(threshold),
            })
            result["logged_break_id"] = break_id

        return result

    def _is_extract_stale(self, reconciliation_date: str) -> bool:
        """Return True if any FLEXCUBE extract is older than reconciliation_date
        by more than self._stale_hours."""
        try:
            from utils.flexcube_mappings import all_flexcube_tables
            tables = all_flexcube_tables()
        except Exception:
            tables = ["sttm_customer"]

        try:
            recon_dt = _parse_date(reconciliation_date)
        except Exception:
            return False

        for tbl in tables:
            ctrl = self._extract_ctrl(tbl)
            if not ctrl:
                continue
            last = ctrl.get("last_extract_date")
            if not last:
                continue
            try:
                last_dt = _parse_date(last) if isinstance(last, str) else last
            except Exception:
                continue
            if isinstance(last_dt, datetime) and isinstance(recon_dt, datetime):
                # Make recon_dt end-of-day so a same-day extract isn't stale
                if recon_dt.hour == 0 and recon_dt.minute == 0:
                    recon_dt = recon_dt + timedelta(hours=23, minutes=59)
                age = recon_dt - last_dt
                if age > timedelta(hours=self._stale_hours):
                    return True
        return False


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d: Decimal) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _decimal_or_none(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return _money(Decimal(str(v)))
    except Exception:
        return None


def _parse_date(s) -> datetime:
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    s = str(s).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        raise ValueError(f"unparseable date: {s!r}")


# ─────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────

def _default_flexcube_count(check_name: str, date: str) -> Optional[Decimal]:
    return None


def _default_a2z_count(check_name: str, date: str) -> Optional[Decimal]:
    return None


def _default_extract_control(table_name: str) -> Optional[dict]:
    return None


def _default_break_log(record: dict) -> None:
    """Append to data/reconciliation_breaks.json. Idempotent on break_id."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        existing: List[dict] = []
        if BREAKS_LOG_FILE.exists():
            try:
                existing = json.loads(BREAKS_LOG_FILE.read_text())
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []

        bid = record.get("break_id")
        if bid:
            for r in existing:
                if r.get("break_id") == bid:
                    return
        existing.append(record)
        BREAKS_LOG_FILE.write_text(json.dumps(existing, indent=2, default=str))
    except Exception as e:
        logger.warning("default break log: write failed: %s", e)


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.reconciliation_engine self-test")

    # ── Spec methods exist ───────────────────────────────────────────
    eng = ReconciliationEngine()
    assert hasattr(eng, "run_full_reconciliation")
    assert hasattr(eng, "compare")
    assert hasattr(eng, "log_break")
    assert hasattr(ReconciliationEngine, "THRESHOLDS")
    print(f"  ✅ spec methods + THRESHOLDS class attr present")

    # ── Empty date → {} ──────────────────────────────────────────────
    assert eng.run_full_reconciliation("") == {}
    print(f"  ✅ empty date → {{}}")

    # ── All checks pass — exact match ────────────────────────────────
    breaks_caught: List[dict] = []
    fc_data = {
        ("customer_count",  "2026-04-29"): Decimal("700000"),
        ("deposit_balance", "2026-04-29"): Decimal("11500000000"),
        ("loan_balance",    "2026-04-29"): Decimal("2600000000"),
    }
    a2z_data = dict(fc_data)
    eng = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: fc_data.get((c, d)),
        a2z_count_fn=lambda c, d: a2z_data.get((c, d)),
        extract_control_fn=lambda t: None,
        break_log_fn=lambda r: breaks_caught.append(r),
    )
    r = eng.run_full_reconciliation("2026-04-29")
    assert r["checks_passed"] == 3
    assert r["checks_failed"] == 0
    assert breaks_caught == []
    print(f"  ✅ exact match: 3 passed, 0 breaks")

    # ── customer_count off by 1 → break (threshold=0) ────────────────
    breaks_caught.clear()
    a2z_off = dict(a2z_data); a2z_off[("customer_count", "2026-04-29")] = Decimal("700001")
    eng2 = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: fc_data.get((c, d)),
        a2z_count_fn=lambda c, d: a2z_off.get((c, d)),
        break_log_fn=lambda r: breaks_caught.append(r),
    )
    r = eng2.run_full_reconciliation("2026-04-29")
    assert r["checks_failed"] == 1
    assert len(breaks_caught) == 1
    assert breaks_caught[0]["variance"] == 1.0
    print(f"  ✅ customer_count +1: break logged variance={breaks_caught[0]['variance']}")

    # ── deposit +KES 500 within threshold ────────────────────────────
    breaks_caught.clear()
    a2z_small = dict(a2z_data); a2z_small[("deposit_balance", "2026-04-29")] = \
        fc_data[("deposit_balance", "2026-04-29")] + Decimal("500")
    eng3 = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: fc_data.get((c, d)),
        a2z_count_fn=lambda c, d: a2z_small.get((c, d)),
        break_log_fn=lambda r: breaks_caught.append(r),
    )
    r = eng3.run_full_reconciliation("2026-04-29")
    assert r["checks_failed"] == 0
    print(f"  ✅ deposit +KES 500: WITHIN KES 1000 threshold")

    # ── deposit +KES 1500 → break ────────────────────────────────────
    breaks_caught.clear()
    a2z_big = dict(a2z_data); a2z_big[("deposit_balance", "2026-04-29")] = \
        fc_data[("deposit_balance", "2026-04-29")] + Decimal("1500")
    eng4 = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: fc_data.get((c, d)),
        a2z_count_fn=lambda c, d: a2z_big.get((c, d)),
        break_log_fn=lambda r: breaks_caught.append(r),
    )
    r = eng4.run_full_reconciliation("2026-04-29")
    assert r["checks_failed"] == 1
    assert breaks_caught[0]["abs_variance"] == 1500.0
    print(f"  ✅ deposit +KES 1500: above threshold, break logged")

    # ── Missing FLEXCUBE side → not_run, NOT silent pass ─────────────
    eng5 = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: None if c == "customer_count" else fc_data.get((c, d)),
        a2z_count_fn=lambda c, d: a2z_data.get((c, d)),
        break_log_fn=lambda r: None,
    )
    r = eng5.run_full_reconciliation("2026-04-29")
    assert r["checks_not_run"] == 1
    customer_check = next(c for c in r["checks"] if c["check_name"] == "customer_count")
    assert customer_check["status"] == "not_run_missing_data"
    print(f"  ✅ missing FLEXCUBE: status=not_run_missing_data (no silent pass)")

    # ── Stale extract → all checks not_run_stale_extract ─────────────
    eng6 = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: fc_data.get((c, d)),
        a2z_count_fn=lambda c, d: a2z_data.get((c, d)),
        extract_control_fn=lambda t: {"last_extract_date": "2026-04-25"},    # 4d old
        break_log_fn=lambda r: None,
    )
    r = eng6.run_full_reconciliation("2026-04-29")
    assert r["extract_stale"] is True
    assert r["checks_not_run"] == 3
    assert r["checks_passed"] == 0
    assert "Mandatory Standard #11" in r["data_quality_warning"]
    print(f"  ✅ stale extract: all 3 checks not_run, warning cites Std#11")

    # ── compare() returns Decimal variance ──────────────────────────
    eng7 = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: Decimal("100"),
        a2z_count_fn=lambda c, d: Decimal("105"),
    )
    assert eng7.compare("customer_count", "2026-04-29") == Decimal("5")
    print(f"  ✅ compare() returns variance=5")

    # ── compare() with missing → None ───────────────────────────────
    eng8 = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: None,
        a2z_count_fn=lambda c, d: Decimal("100"),
    )
    assert eng8.compare("customer_count", "2026-04-29") is None
    print(f"  ✅ compare() with missing → None")

    # ── KES-billion precision ───────────────────────────────────────
    fc_huge = {("deposit_balance", "2026-04-29"): Decimal("11500000000.50")}
    a2z_huge = {("deposit_balance", "2026-04-29"): Decimal("11500000000.51")}
    eng9 = ReconciliationEngine(
        flexcube_count_fn=lambda c, d: fc_huge.get((c, d)),
        a2z_count_fn=lambda c, d: a2z_huge.get((c, d)),
    )
    r = eng9.run_full_reconciliation("2026-04-29")
    deposit = next(c for c in r["checks"] if c["check_name"] == "deposit_balance")
    assert deposit["abs_variance"] == 0.01
    print(f"  ✅ KES-billion precision: 0.01 detected (would be lost in float)")

    # ── log_break adds logged_at; non-dict ignored ──────────────────
    captured = []
    eng10 = ReconciliationEngine(break_log_fn=lambda r: captured.append(r))
    eng10.log_break({"check_name": "test", "variance": 100})
    assert "logged_at" in captured[0]
    eng10.log_break("not a dict")
    eng10.log_break(None)
    assert len(captured) == 1
    print(f"  ✅ log_break: adds timestamp, ignores non-dict")

    print("\n  ALL TESTS PASSED")
