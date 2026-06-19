#!/usr/bin/env python3
"""
fx_diag.py — READ-ONLY. Pin the exact deals behind the analytics-vs-dashboard FCY gap.

Dashboard FCY reads the JSON store (PipelineManager); analytics FCY reads Postgres.
This computes each deal's FCY contribution under BOTH paths, then lists the deals
where they disagree — summing to the ~1.53B gap. Writes nothing.

    python scripts\\fx_diag.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def book_of(d):
    return d.get("currency_book") or (
        "FCY" if str(d.get("currency", "KES")).strip() not in ("", "KES") else "LCY")


def main():
    from utils.core import PipelineManager
    from utils.api import _deal_value, _referral_blocked, _safe_float

    def dash_amt(d):
        a = d.get("amount_kes")
        return _safe_float(a) if a is not None else _safe_float(d.get("deal_value") or d.get("amount", 0))

    def counts(d):
        return not d.get("draft") and not _referral_blocked(d) and book_of(d) == "FCY"

    # ---- JSON store (dashboard path) ----
    jd = {str(d.get("id")): d for d in PipelineManager().get_deals()}
    json_fcy = {i: dash_amt(d) for i, d in jd.items() if counts(d)}

    # ---- Postgres (analytics path) ----
    dd = {}
    try:
        from utils.db import db as _db
        from utils.api import _normalize_db_deal_row
        try:
            from utils.api import _serialize
            rows = _serialize(_db.fetch_all("SELECT * FROM pipeline_deals", ()))
        except Exception:
            rows = _db.fetch_all("SELECT * FROM pipeline_deals", ())
        dd = {str(r.get("id")): _normalize_db_deal_row(r) for r in rows}
    except Exception as e:
        print(f"[db read error] {type(e).__name__}: {e}")
    db_fcy = {i: _deal_value(d) for i, d in dd.items() if counts(d)}

    js, ds = sum(json_fcy.values()), sum(db_fcy.values())
    print(f"JSON (dashboard) FCY: {js:,.1f}  over {len(json_fcy)} FCY deals")
    print(f"DB   (analytics) FCY: {ds:,.1f}  over {len(db_fcy)} FCY deals")
    print(f"GAP (JSON - DB):      {js - ds:,.1f}\n")
    print(f"deal counts — JSON store: {len(jd)} | DB store: {len(dd)}")

    all_ids = set(json_fcy) | set(db_fcy)
    diffs = []
    for i in all_ids:
        a, b = json_fcy.get(i, 0.0), db_fcy.get(i, 0.0)
        if abs(a - b) > 0.5:
            diffs.append((i, a, b))
    diffs.sort(key=lambda x: abs(x[1] - x[2]), reverse=True)
    print(f"\n--- {len(diffs)} deals differ between paths "
          f"(sum of diffs = {sum(a - b for _, a, b in diffs):,.1f}) ---")
    print(f"{'id':<10} {'JSON_fcy':>16} {'DB_fcy':>16}  reason")
    for i, a, b in diffs[:25]:
        j, k = jd.get(i), dd.get(i)
        if j is None:
            reason = "in DB only (missing from JSON)"
        elif k is None:
            reason = "in JSON only (missing from DB)"
        else:
            bits = []
            if j.get("draft") != k.get("draft"):
                bits.append(f"draft J={j.get('draft')} D={k.get('draft')}")
            if book_of(j) != book_of(k):
                bits.append(f"book J={book_of(j)} D={book_of(k)}")
            if (j.get("amount_kes") is None) != (k.get("amount_kes") is None):
                bits.append(f"amount_kes J={j.get('amount_kes')} D={k.get('amount_kes')}")
            if str(j.get("staff_code")) != str(k.get("staff_code")):
                bits.append(f"owner J={j.get('staff_code')} D={k.get('staff_code')}")
            reason = "; ".join(bits) or "amount differs (deal_value vs amount_kes)"
        print(f"{i:<10} {a:>16,.1f} {b:>16,.1f}  {reason}")


if __name__ == "__main__":
    main()
