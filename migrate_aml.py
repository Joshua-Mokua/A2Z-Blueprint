import os, sys, json
from pathlib import Path
from psycopg2.extras import Json
import psycopg2

DB_HOST = os.getenv("A2Z_DB_HOST", "localhost")
DB_PORT = int(os.getenv("A2Z_DB_PORT", "5432"))
DB_NAME = os.getenv("A2Z_DB_NAME", "a2z_mis360")
DB_USER = os.getenv("A2Z_DB_USER", "a2z_app")
DB_PASS = os.getenv("A2Z_DB_PASSWORD", "")

if not DB_PASS:
    print("ERROR: set A2Z_DB_PASSWORD=@Mylove$u")
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

aml_file = Path(__file__).parent / "data" / "aml_alerts.json"
if not aml_file.exists():
    print("ERROR: data/aml_alerts.json not found")
    sys.exit(1)

raw    = json.loads(aml_file.read_text(encoding="utf-8"))
alerts = raw if isinstance(raw, list) else raw.get("alerts", [])
print(f"Loaded {len(alerts)} AML alerts")

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

CORE_FIELDS = ["id","account_number","customer_name","transaction_date",
               "amount","transaction_type","rule_triggered","risk_score",
               "risk_level","status","assigned_to","str_filed",
               "str_reference","notes","created_at","updated_at"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for alert in alerts:
    try:
        meta = {k: v for k, v in alert.items() if k not in CORE_FIELDS}

        cur.execute("""
            INSERT INTO aml_alerts (
                id, account_number, customer_name, transaction_date,
                amount, transaction_type, rule_triggered, risk_score,
                risk_level, status, assigned_to, str_filed,
                str_reference, notes, created_at, updated_at, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                status      = EXCLUDED.status,
                assigned_to = EXCLUDED.assigned_to,
                str_filed   = EXCLUDED.str_filed,
                notes       = EXCLUDED.notes,
                updated_at  = EXCLUDED.updated_at
        """, (
            safe_str(alert.get("id", "")),
            safe_str(alert.get("account_number", "")),
            safe_str(alert.get("customer_name", "")),
            safe_date(alert.get("transaction_date")),
            safe_float(alert.get("amount", 0)),
            safe_str(alert.get("transaction_type", "")),
            safe_str(alert.get("rule_triggered", "")),
            safe_int(alert.get("risk_score", 0)),
            safe_str(alert.get("risk_level", "")),
            safe_str(alert.get("status", "")),
            safe_str(alert.get("assigned_to", "")),
            bool(alert.get("str_filed", False)),
            safe_str(alert.get("str_reference", "")),
            safe_str(alert.get("notes", "")),
            safe_date(alert.get("created_at")),
            safe_date(alert.get("updated_at")),
            Json(meta)
        ))
        inserted += 1
    except Exception as e:
        errors += 1
        print(f"  SKIP {alert.get('id','?')}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} AML alerts. Errors: {errors}")