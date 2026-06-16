"""Seed a realistic demo pipeline so executive drill-downs populate.

WHY: the accumulated DB pipeline is dominated by simulation/test deals created
by 1-2 personas with no branch set, so Branch/RM drills collapse to
"Unassigned". This lays down deals spread across real branches, RMs, CBK
sectors, products, stages, and currencies so Branch -> RM -> deal drill-downs
demo well.

SAFE BY DESIGN:
  --dry-run   build + print the distribution; touch NOTHING (no DB, no import
              of the app). Runs anywhere.
  --reset     DELETE existing pipeline_deals AFTER writing a timestamped JSON
              backup to data/_backups/. Without --reset, seeds are upserted
              alongside whatever exists (idempotent by deterministic id).
  Deterministic ids (SEED00001..) -> re-running is idempotent, never duplicates.

Writes go through the app's canonical _db_sync_pipeline_deal (same shape as
API-created deals). KES-equivalent + currency_book are stamped per deal.

USAGE (in the project venv, API may be stopped):
  python scripts\\seed_pipeline_demo.py --dry-run
  python scripts\\seed_pipeline_demo.py --count 600 --branches 35 --rms 232 --reset
"""
from __future__ import annotations
import argparse, json, os, random, sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def _load(name, default=None):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# ── reference data ───────────────────────────────────────────────────────
CBK_SECTORS_FALLBACK = [
    "Agriculture, Forestry & Fishing", "Mining & Quarrying", "Manufacturing",
    "Electricity, Gas, Water & Air Conditioning", "Construction & Real Estate",
    "Wholesale & Retail Trade", "Transport & Storage",
    "Accommodation & Food Services", "Information & Communication",
    "Financial & Insurance Activities", "Real Estate & Business Services",
    "Professional, Scientific & Technical", "Public Administration",
    "Education, Health & Social Work",
]
SEGMENTS_FALLBACK = ["Mass Market", "Affluent", "Premier", "Diaspora",
                     "Youth", "Salaried", "Self-Employed"]

# product class -> the pipeline_category the app buckets it under
CLASS_TO_CATEGORY = {
    "Assets": "asset", "Liabilities": "liability", "Insurance": "insurance",
    "Transactional": "other", "Investments": "other",
}
# realistic KES value ranges (native) per category, (low, high)
VALUE_RANGES = {
    "asset": (500_000, 450_000_000), "liability": (100_000, 60_000_000),
    "insurance": (50_000, 6_000_000), "other": (50_000, 25_000_000),
}
CURRENCY_WEIGHTS = [("KES", 0.86), ("USD", 0.08), ("EUR", 0.03), ("GBP", 0.03)]


def _weighted(pairs):
    r, acc = random.random(), 0.0
    for v, w in pairs:
        acc += w
        if r <= acc:
            return v
    return pairs[-1][0]


def _fx_rates():
    fx = _load("fx_rates.json", {}) or {}
    out = {"KES": 1.0}
    for r in fx.get("rates", []):
        c = r.get("currency")
        if c and c not in out and r.get("rate_type") in (None, "mid"):
            out[c] = float(r.get("rate_to_kes") or 1.0)
    # sensible fallbacks if the table is thin
    for c, v in (("USD", 129.5), ("EUR", 140.0), ("GBP", 164.0)):
        out.setdefault(c, v)
    return out


def build_deals(count, n_branches, n_rms, seed):
    random.seed(seed)
    branches_all = _load("flexcube_mock_branches.json", []) or []
    branches_all = branches_all if isinstance(branches_all, list) else list(branches_all.values())
    active_branches = [b for b in branches_all if str(b.get("status", "ACTIVE")).upper() == "ACTIVE"]
    branches = active_branches[:n_branches] if n_branches else active_branches

    staff_all = _load("flexcube_mock_staff.json", []) or []
    staff_all = staff_all if isinstance(staff_all, list) else list(staff_all.values())
    # RM pool: ACTIVE staff, exclude obvious executives so RMs look like RMs.
    EXCLUDE = ("Managing Director", "Director", "Chief", "Head Office")
    rms = [s for s in staff_all
           if str(s.get("status", "ACTIVE")).upper() == "ACTIVE"
           and not any(x in str(s.get("role", "")) for x in EXCLUDE[:3])]
    random.shuffle(rms)
    rms = rms[:n_rms] if n_rms else rms
    if not branches or not rms:
        raise SystemExit("Reference data missing (branches/staff). Cannot seed.")

    # Assign each branch a stable slice of RMs (round-robin) so Branch -> RM
    # is a coherent hierarchy.
    branch_rms: dict = {b["branch_name"]: [] for b in branches}
    bn = [b["branch_name"] for b in branches]
    for i, rm in enumerate(rms):
        branch_rms[bn[i % len(bn)]].append(rm)
    for b in bn:  # guarantee at least one RM per branch
        if not branch_rms[b]:
            branch_rms[b].append(random.choice(rms))

    settings = _load("pipeline_settings.json", {}) or {}
    catalogue = settings.get("product_catalogue", {}) or {}
    stage_flows = settings.get("stage_flows", {}) or {}
    sectors = settings.get("business_sectors") or CBK_SECTORS_FALLBACK
    segments = settings.get("customer_segments") or SEGMENTS_FALLBACK
    fx = _fx_rates()

    # flatten products with their category
    products = []
    for cls, items in catalogue.items():
        cat = CLASS_TO_CATEGORY.get(cls, "other")
        for p in items:
            products.append((p, cat))
    if not products:
        raise SystemExit("product_catalogue missing in pipeline_settings.json")

    cat_weights = [("asset", 0.55), ("liability", 0.25),
                   ("insurance", 0.10), ("other", 0.10)]
    today = date.today()
    deals = []
    for i in range(count):
        cat = _weighted(cat_weights)
        cands = [p for p in products if p[1] == cat] or products
        product, _ = random.choice(cands)
        flow = stage_flows.get(cat) or stage_flows.get("asset") or ["Lead", "Closed Won", "Closed Lost"]
        # weight toward live stages; some closed
        roll = random.random()
        if roll < 0.15:
            stage = "Closed Won"
        elif roll < 0.25:
            stage = "Closed Lost"
        else:
            live = [s for s in flow if not s.startswith("Closed")]
            stage = random.choice(live) if live else flow[0]

        branch = random.choice(branches)
        bname = branch["branch_name"]
        rm = random.choice(branch_rms[bname])
        client_type = "Business" if random.random() < 0.6 else "Individual"

        lo, hi = VALUE_RANGES[cat]
        # log-uniform for a realistic long tail
        import math
        native = round(math.exp(random.uniform(math.log(lo), math.log(hi))), -3)
        currency = _weighted(CURRENCY_WEIGHTS)
        rate = fx.get(currency, 1.0)
        amount_kes = round(native * rate, 2)
        currency_book = "FCY" if currency != "KES" else "LCY"

        open_d = today - timedelta(days=random.randint(0, 180))
        close_d = open_d + timedelta(days=random.randint(20, 120))
        prob = {"Lead": 10, "Contacted": 20, "Qualified": 35, "Application": 50,
                "Credit Assessment": 60, "Offer / Proposal": 70, "Proposal": 55,
                "Negotiation": 75, "Documentation": 85, "Compliance": 90,
                "Closed Won": 100, "Closed Lost": 0}.get(stage, 40)

        deal = {
            "id": f"SEED{i + 1:05d}",
            "staff_code": str(rm.get("staff_code", "")),
            "staff_name": rm.get("full_name", ""),
            "unit": bname,
            "role": rm.get("role", ""),
            "client_name": f"{client_type} Client {i + 1:04d}",
            "client_type": client_type,
            "product_type": product,
            "pipeline_category": cat,
            "deal_category": "New Facility",
            "stage": stage,
            "deal_value": native,
            "amount": native,
            "currency": currency,
            "currency_book": currency_book,
            "fx_rate": rate,
            "fx_rate_source": "seed",
            "amount_kes": amount_kes,
            "probability": prob,
            "open_date": open_d.isoformat(),
            "expected_close": close_d.isoformat(),
            "source": "Seed",
            "is_ntb": random.random() < 0.4,
            "portfolio_owner_code": str(rm.get("staff_code", "")),
            "portfolio_owner_name": rm.get("full_name", ""),
            "region": branch.get("region", ""),
        }
        if client_type == "Business":
            deal["sector"] = random.choice(sectors)
        else:
            deal["segment"] = random.choice(segments)
        deals.append(deal)
    return deals


def summarise(deals):
    from collections import Counter
    def topn(field, n=8):
        c = Counter(str(d.get(field) or "—") for d in deals)
        return c
    total = sum(d["amount_kes"] for d in deals)
    print(f"\n  deals: {len(deals)} | total KES-equiv: {total/1e9:.2f}B")
    print(f"  distinct branches: {len(set(d['unit'] for d in deals))}")
    print(f"  distinct RMs:      {len(set(d['staff_name'] for d in deals))}")
    print(f"  distinct sectors:  {len(set(d.get('sector') for d in deals if d.get('sector')))}")
    cb = Counter(d['currency_book'] for d in deals)
    print(f"  currency book:     LCY={cb.get('LCY',0)} FCY={cb.get('FCY',0)}")
    print(f"  by category:       {dict(topn('pipeline_category'))}")
    print(f"  by stage (top):    {dict(topn('stage').most_common(6))}")
    print(f"  by region (top):   {dict(topn('region').most_common(6))}")


def write_db(deals, do_reset):
    """Persist via the app's canonical upsert. Imports the app (needs the
    project venv). Backs up before any destructive reset."""
    try:
        from utils.db import db as _db
        from utils.api import _db_sync_pipeline_deal, _db_available
    except Exception as e:
        raise SystemExit(f"Could not import app DB layer (run in the project venv): {e}")
    if not _db_available():
        raise SystemExit("Postgres unavailable — start the DB and retry.")

    if do_reset:
        os.makedirs(os.path.join(DATA, "_backups"), exist_ok=True)
        ts = date.today().isoformat()
        existing = _db.fetch_all("SELECT * FROM pipeline_deals", ())
        bpath = os.path.join(DATA, "_backups", f"pipeline_deals_{ts}.json")
        with open(bpath, "w", encoding="utf-8") as f:
            json.dump([dict(r) for r in (existing or [])], f, default=str, indent=2)
        print(f"  backup written: {bpath} ({len(existing or [])} rows)")
        _db.execute("DELETE FROM pipeline_deals", ())
        print("  existing pipeline_deals cleared")

    n = 0
    for d in deals:
        _db_sync_pipeline_deal(d)
        n += 1
    print(f"  upserted {n} seed deals into pipeline_deals")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=600)
    ap.add_argument("--branches", type=int, default=35)
    ap.add_argument("--rms", type=int, default=232)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    deals = build_deals(a.count, a.branches, a.rms, a.seed)
    summarise(deals)
    if a.dry_run:
        print("\n  DRY RUN — nothing written.\n")
        return
    write_db(deals, a.reset)
    print("\n  Done. Restart the API and reload Analytics to see populated drills.\n")


if __name__ == "__main__":
    main()
