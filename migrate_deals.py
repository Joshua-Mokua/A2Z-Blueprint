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

deals_file = Path(__file__).parent / "data" / "deal_rooms.json"
raw        = json.loads(deals_file.read_text(encoding="utf-8"))
deals      = raw if isinstance(raw, list) else raw.get("deals", [])
print(f"Loaded {len(deals)} deal rooms")

def safe_date(val):
    if not val: return None
    try:
        parts = str(val)[:10].split("-")
        if len(parts) == 3: return f"{parts[0]}-{parts[1]}-{parts[2]}"
    except: pass
    return None

def safe_float(val):
    try: return float(str(val).replace(",",""))
    except: return 0.0

def safe_int(val):
    try: return int(val)
    except: return 0

def safe_str(val):
    if isinstance(val, (dict, list)): return json.dumps(val)
    return str(val) if val else ""

CORE_FIELDS = ["id","deal_name","pipeline_id","deal_type","amount_m","currency",
               "tenor_months","rate_pct","purpose","security","term_sheet_status",
               "rm","created_date","last_updated","conditions_precedent",
               "covenants","fees","checklist_complete","notes"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for d in deals:
    try:
        meta  = {k: v for k, v in d.items() if k not in CORE_FIELDS}
        cps   = d.get("conditions_precedent", [])
        covs  = d.get("covenants", [])
        fees  = d.get("fees", {})
        if isinstance(cps, str):  cps  = []
        if isinstance(covs, str): covs = []
        if isinstance(fees, str): fees = {}

        cur.execute("""
            INSERT INTO deal_rooms (
                id, deal_name, pipeline_id, deal_type,
                amount_m, currency, tenor_months, rate_pct,
                purpose, security, term_sheet_status, rm,
                created_date, last_updated, conditions_precedent,
                covenants, fees, checklist_complete, notes, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                term_sheet_status    = EXCLUDED.term_sheet_status,
                amount_m             = EXCLUDED.amount_m,
                rate_pct             = EXCLUDED.rate_pct,
                conditions_precedent = EXCLUDED.conditions_precedent,
                covenants            = EXCLUDED.covenants,
                checklist_complete   = EXCLUDED.checklist_complete,
                last_updated         = EXCLUDED.last_updated
        """, (
            safe_str(d.get("id","")),
            safe_str(d.get("deal_name","")),
            safe_str(d.get("pipeline_id","")),
            safe_str(d.get("deal_type","")),
            safe_float(d.get("amount_m",0)),
            safe_str(d.get("currency","KES")),
            safe_int(d.get("tenor_months",0)),
            safe_float(d.get("rate_pct",0)),
            safe_str(d.get("purpose","")),
            safe_str(d.get("security","")),
            safe_str(d.get("term_sheet_status","")),
            safe_str(d.get("rm","")),
            safe_date(d.get("created_date")),
            safe_date(d.get("last_updated")),
            Json(cps),
            Json(covs),
            Json(fees),
            bool(d.get("checklist_complete", False)),
            safe_str(d.get("notes","")),
            Json(meta)
        ))
        inserted += 1
    except Exception as e:
        errors += 1
        print(f"  SKIP {d.get('id','?')}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} deal rooms. Errors: {errors}")