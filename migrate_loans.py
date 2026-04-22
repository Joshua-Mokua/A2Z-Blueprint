import os, sys, json
from pathlib import Path

DB_HOST = os.getenv("A2Z_DB_HOST", "localhost")
DB_PORT = int(os.getenv("A2Z_DB_PORT", "5432"))
DB_NAME = os.getenv("A2Z_DB_NAME", "a2z_mis360")
DB_USER = os.getenv("A2Z_DB_USER", "a2z_app")
DB_PASS = os.getenv("A2Z_DB_PASSWORD", "")

if not DB_PASS:
    print("ERROR: set A2Z_DB_PASSWORD=@Mylove$u")
    sys.exit(1)

import psycopg2
from psycopg2.extras import Json

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

loans_file = Path(__file__).parent / "data" / "loan_applications.json"
raw   = json.loads(loans_file.read_text(encoding="utf-8"))
loans = raw if isinstance(raw, list) else raw.get("applications", [])
print(f"Loaded {len(loans)} loan applications")

def safe_date(val):
    if not val: return None
    try:
        parts = str(val)[:10].split("-")
        if len(parts) == 3: return f"{parts[0]}-{parts[1]}-{parts[2]}"
    except: pass
    return None

def safe_float(val):
    try: return float(str(val).replace(",", ""))
    except: return 0.0

def safe_int(val):
    try: return int(val)
    except: return 0

def safe_str(val):
    if isinstance(val, (dict, list)): return json.dumps(val)
    return str(val) if val else ""

CORE_FIELDS = ["id","pipeline_deal_id","client_name","client_cif","product",
               "amount","currency","swim_lane","status","deal_category",
               "application_date","rm_code","rm_name","rm_unit","analyst",
               "is_repeat_borrower","completeness_score","compliance_flag",
               "tat_days","sla_target_days","last_updated"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for loan in loans:
    try:
        # Build metadata from remaining fields
        meta = {k: v for k, v in loan.items() if k not in CORE_FIELDS}

        cur.execute("""
            INSERT INTO loan_applications (
                id, pipeline_deal_id, client_name, client_cif,
                product, amount, currency, swim_lane, status,
                deal_category, application_date, rm_code, rm_name,
                rm_unit, analyst, is_repeat_borrower,
                completeness_score, compliance_flag,
                tat_days, sla_target_days, last_updated, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                status             = EXCLUDED.status,
                swim_lane          = EXCLUDED.swim_lane,
                completeness_score = EXCLUDED.completeness_score,
                tat_days           = EXCLUDED.tat_days,
                last_updated       = EXCLUDED.last_updated
        """, (
            safe_str(loan.get("id", "")),
            safe_str(loan.get("pipeline_deal_id", "")),
            safe_str(loan.get("client_name", "")),
            safe_str(loan.get("client_cif", "")),
            safe_str(loan.get("product", "")),
            safe_float(loan.get("amount", 0)),
            safe_str(loan.get("currency", "KES")),
            safe_str(loan.get("swim_lane", "")),
            safe_str(loan.get("status", "")),
            safe_str(loan.get("deal_category", "New Facility")),
            safe_date(loan.get("application_date")),
            safe_str(loan.get("rm_code", "")),
            safe_str(loan.get("rm_name", "")),
            safe_str(loan.get("rm_unit", "")),
            safe_str(loan.get("analyst", "")),
            bool(loan.get("is_repeat_borrower", False)),
            safe_float(loan.get("completeness_score", 0)),
            bool(loan.get("compliance_flag", False)),
            safe_int(loan.get("tat_days", 0)),
            safe_int(loan.get("sla_target_days", 0)),
            safe_date(loan.get("last_updated")),
            Json(meta)
        ))
        inserted += 1
        if inserted % 100 == 0:
            print(f"  {inserted} / {len(loans)} done...")
    except Exception as e:
        errors += 1
        print(f"  SKIP {loan.get('id','?')}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} loans. Errors: {errors}")