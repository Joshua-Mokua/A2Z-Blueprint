import os, sys, json
from pathlib import Path

DB_HOST = os.getenv("A2Z_DB_HOST", "localhost")
DB_PORT = int(os.getenv("A2Z_DB_PORT", "5432"))
DB_NAME = os.getenv("A2Z_DB_NAME", "a2z_mis360")
DB_USER = os.getenv("A2Z_DB_USER", "a2z_app")
DB_PASS = os.getenv("A2Z_DB_PASSWORD", "")

if not DB_PASS:
    print("ERROR: A2Z_DB_PASSWORD not set.")
    print("Run: set A2Z_DB_PASSWORD=@Mylove$u")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: Run: pip install psycopg2-binary")
    sys.exit(1)

print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}...")
try:
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    conn.autocommit = False
    print("Connected successfully")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

pipeline_file = Path(__file__).parent / "data" / "pipeline.json"
if not pipeline_file.exists():
    print("ERROR: data/pipeline.json not found")
    sys.exit(1)

raw = json.loads(pipeline_file.read_text(encoding="utf-8"))
deals = raw if isinstance(raw, list) else raw.get("deals", [])
print(f"Loaded {len(deals)} deals from pipeline.json")

inserted = 0
errors   = 0
cur      = conn.cursor()

for deal in deals:
    try:
        # Parse amount safely
        amount = deal.get("amount", 0)
        try:
            amount = float(str(amount).replace(",", ""))
        except:
            amount = 0.0

        # Parse dates safely
        def safe_date(val):
            if not val:
                return None
            try:
                from datetime import date
                parts = str(val)[:10].split("-")
                if len(parts) == 3:
                    return f"{parts[0]}-{parts[1]}-{parts[2]}"
            except:
                pass
            return None

        cur.execute("""
            INSERT INTO pipeline_deals (
                id, staff_code, staff_name, unit, role,
                client_name, client_cif, product, stage,
                deal_category, amount, currency,
                open_date, expected_close, probability,
                is_repeat_borrower, existing_facility_id,
                repayment_history, notes, last_updated, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                stage           = EXCLUDED.stage,
                amount          = EXCLUDED.amount,
                probability     = EXCLUDED.probability,
                last_updated    = EXCLUDED.last_updated,
                notes           = EXCLUDED.notes
        """, (
            deal.get("id", ""),
            str(deal.get("staff_code", "")),
            deal.get("staff_name", ""),
            deal.get("unit", ""),
            deal.get("role", ""),
            deal.get("client_name", ""),
            deal.get("client_cif", ""),
            deal.get("product", ""),
            deal.get("stage", ""),
            deal.get("deal_category", "New Facility"),
            amount,
            deal.get("currency", "KES"),
            safe_date(deal.get("open_date")),
            safe_date(deal.get("expected_close")),
            float(deal.get("probability", 0)),
            bool(deal.get("is_repeat_borrower", False)),
            deal.get("existing_facility_id", ""),
            deal.get("repayment_history", ""),
            deal.get("notes", ""),
            safe_date(deal.get("last_updated")),
            json.dumps({k: v for k, v in deal.items()
                       if k not in ["id","staff_code","staff_name","unit","role",
                                    "client_name","client_cif","product","stage",
                                    "deal_category","amount","currency","open_date",
                                    "expected_close","probability","is_repeat_borrower",
                                    "existing_facility_id","repayment_history",
                                    "notes","last_updated"]})
        ))
        inserted += 1
        if inserted % 50 == 0:
            print(f"  {inserted} / {len(deals)} done...")
    except Exception as e:
        errors += 1
        print(f"  SKIP {deal.get('id','?')}: {e}")
        if errors > 20:
            print("Too many errors. Rolling back.")
            conn.rollback()
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} deals. Errors: {errors}")
print(f"\nNext step:")
print(f"  Open utils/db.py")
print(f"  Change 'pipeline_deals': False")
print(f"  To:    'pipeline_deals': True")