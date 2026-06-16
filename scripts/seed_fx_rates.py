"""Idempotent seed/verify for the operational FX rate table (Phase 4-1).

Safe to run repeatedly. Ensures KES base row exists; does NOT overwrite admin
edits to existing currency/type/date rows. Prints a redacted summary.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.fx_engine import FxRateStore, BASE_CURRENCY

def main():
    st = FxRateStore()
    # guarantee the base row
    has_base = any(r.get("currency") == BASE_CURRENCY for r in st.list_rates())
    if not has_base:
        st.upsert_rate(BASE_CURRENCY, 1.0, "2026-01-01", rate_type="mid",
                       source="system", entered_by="system")
        st.save()
        print(f"  + added base {BASE_CURRENCY} = 1.0")
    rows = st.list_rates(active_only=True)
    # EcoBank operates across ~33 African countries plus key trade currencies.
    # Seed synthetic mid rates (rate_to_kes) for any currency not already in the
    # store — never overwrites admin-entered rates. Priority pairs (USD, CNY)
    # surface at the top of the picker (ordering handled client-side).
    SEED_CURRENCIES = [
        ("USD", 129.5), ("CNY", 18.0),               # priority trade currencies
        ("EUR", 140.0), ("GBP", 164.0),              # other internationals
        ("NGN", 0.085), ("GHS", 8.6),                # Nigeria, Ghana
        ("XOF", 0.21), ("XAF", 0.21),                # WAEMU (8) + CEMAC (6)
        ("ZAR", 7.0), ("TZS", 0.050), ("UGX", 0.035),
        ("RWF", 0.095), ("ZMW", 4.8), ("MZN", 2.0),
        ("ETB", 1.04), ("AOA", 0.142), ("CDF", 0.046),
        ("MWK", 0.075), ("GNF", 0.015), ("LRD", 0.67),
        ("SLE", 5.7), ("GMD", 1.9), ("CVE", 1.27), ("STN", 5.7),
    ]
    existing = {r.get("currency") for r in st.list_rates()}
    added = 0
    for ccy, rate in SEED_CURRENCIES:
        if ccy not in existing:
            st.upsert_rate(ccy, rate, "2026-01-01", rate_type="mid",
                           source="seed", entered_by="system")
            added += 1
    if added:
        st.save()
        print(f"  + added {added} currencies (EcoBank African footprint + CNY)")
    rows = st.list_rates(active_only=True)
    by_ccy = {}
    for r in rows:
        by_ccy.setdefault(r["currency"], []).append(r["rate_type"])
    print(f"FX store: {len(rows)} active rates across {len(by_ccy)} currencies")
    for ccy, types in sorted(by_ccy.items()):
        print(f"  {ccy}: {sorted(set(types))}")
    # smoke test the resolver
    print(f"  resolve USD mid today -> {st.resolve_rate('USD')}")
    print(f"  resolve KES (base)     -> {st.resolve_rate('KES')}")

if __name__ == "__main__":
    main()
