"""utils/statement_analysis.py — Tier-1 DETERMINISTIC statement analysis (no AI).

Computes a monthly turnover spread + cashflow-based affordability from STRUCTURED
transactions (cif, txn_date, amount, dr_cr). No AI dependency — always works. AI (Tier 2)
is a separate optional path that only EXTRACTS transactions into this structure.

Config-driven: DSR limit / monthly rate from statement_analyzer_config
(data/proposition_config.json).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from collections import defaultdict
from datetime import datetime


def _cfg() -> Dict[str, Any]:
    try:
        import json
        from utils.core import DATA_DIR
        p = DATA_DIR / "proposition_config.json"
        if p.exists():
            return (json.loads(p.read_text(encoding="utf-8")) or {}).get("statement_analyzer_config", {}) or {}
    except Exception:
        pass
    return {}


def _month_key(dstr: str) -> Optional[str]:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(dstr)[:19], fmt).strftime("%Y-%m")
        except Exception:
            continue
    # last resort: first 7 chars if they look like YYYY-MM
    s = str(dstr)[:7]
    return s if len(s) == 7 and s[4] == "-" else None


def _is_credit(dr_cr: str) -> bool:
    v = str(dr_cr or "").strip().upper()
    return v in ("C", "CR", "CREDIT", "CRD")


def analyze_transactions(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic turnover spread + cashflow affordability from structured txns.
    Each txn: {txn_date, amount, dr_cr}. Returns spread + summary + affordability."""
    cfg = _cfg()
    dsr_limit = float(cfg.get("dsr_limit", 40)) / 100.0

    buckets: Dict[str, Dict[str, float]] = defaultdict(lambda: {"credits": 0.0, "debits": 0.0})
    n_used = 0
    for t in (transactions or []):
        mk = _month_key(t.get("txn_date") or t.get("value_date") or "")
        amt = t.get("amount")
        try:
            amt = abs(float(amt))
        except Exception:
            continue
        if not mk:
            continue
        if _is_credit(t.get("dr_cr")):
            buckets[mk]["credits"] += amt
        else:
            buckets[mk]["debits"] += amt
        n_used += 1

    if not buckets:
        return {"ok": False, "reason": "no usable transactions",
                "months": 0, "spread": [], "affordability": {}}

    spread = []
    for mk in sorted(buckets):
        c = round(buckets[mk]["credits"], 2)
        d = round(buckets[mk]["debits"], 2)
        spread.append({"month": mk, "credits": c, "debits": d, "net": round(c - d, 2)})

    months = len(spread)
    avg_credit = round(sum(r["credits"] for r in spread) / months, 2)
    avg_debit = round(sum(r["debits"] for r in spread) / months, 2)
    avg_net = round(avg_credit - avg_debit, 2)
    # affordable instalment = DSR limit applied to average net inflow (proxy for surplus)
    basis = avg_net if avg_net > 0 else avg_credit
    affordable_installment = round(max(basis, 0.0) * dsr_limit, 2)

    return {
        "ok": True,
        "months": months,
        "transactions_used": n_used,
        "spread": spread,
        "summary": {"avg_monthly_credit": avg_credit, "avg_monthly_debit": avg_debit,
                    "avg_monthly_net": avg_net},
        "affordability": {
            "dsr_limit_pct": round(dsr_limit * 100, 2),
            "basis": basis,
            "affordable_installment": affordable_installment,
            "verdict": "AFFORDABLE" if affordable_installment > 0 else "INSUFFICIENT",
        },
    }


def analyze_customer_from_cbs(cif: str, months_back: int = 12) -> Dict[str, Any]:
    """Load a customer's structured transactions from CBS and analyze (no AI)."""
    txns = _load_cbs_transactions_for_cif(str(cif))
    res = analyze_transactions(txns)
    res["cif"] = str(cif)
    res["source"] = "cbs_transactions"
    return res


def _load_cbs_transactions_for_cif(cif: str) -> List[Dict[str, Any]]:
    """Read structured transactions for a CIF from the CBS transactions file. Defensive."""
    import csv
    try:
        from utils.core import BASE_DIR
    except Exception:
        BASE_DIR = None
    candidates = []
    try:
        from pathlib import Path
        roots = []
        if BASE_DIR:
            roots.append(Path(BASE_DIR))
        roots.append(Path.cwd())
        for root in roots:
            candidates += [root / "cbs_data" / "transactions_sample.csv",
                           root / "cbs_data" / "transactions.csv"]
    except Exception:
        pass
    for p in candidates:
        try:
            if p.exists():
                out = []
                with open(p, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if str(row.get("cif", "")) == cif:
                            out.append(row)
                return out
        except Exception:
            continue
    return []
