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

ews_file = Path(__file__).parent / "data" / "ews_cases.json"
if not ews_file.exists():
    print("ERROR: data/ews_cases.json not found")
    sys.exit(1)

raw  = json.loads(ews_file.read_text(encoding="utf-8"))
cases = raw if isinstance(raw, list) else raw.get("cases", [])
print(f"Loaded {len(cases)} EWS cases")

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

CORE_FIELDS = ["id","account_number","client_name","client_cif","product",
               "outstanding","dpd","rag_status","stage","rm_code","rm_name",
               "branch","triggers","actions","last_updated","created_date"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for case in cases:
    try:
        meta = {k: v for k, v in case.items() if k not in CORE_FIELDS}

        triggers = case.get("triggers", [])
        if isinstance(triggers, str):
            triggers = [triggers]

        actions = case.get("actions", [])
        if isinstance(actions, str):
            actions = [actions]

        cur.execute("""
            INSERT INTO ews_cases (
                id, account_number, client_name, client_cif,
                product, outstanding, dpd, rag_status, stage,
                rm_code, rm_name, branch, triggers, actions,
                last_updated, created_date, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                dpd         = EXCLUDED.dpd,
                rag_status  = EXCLUDED.rag_status,
                stage       = EXCLUDED.stage,
                last_updated= EXCLUDED.last_updated,
                actions     = EXCLUDED.actions
        """, (
            safe_str(case.get("id", "")),
            safe_str(case.get("account_number", "")),
            safe_str(case.get("client_name", "")),
            safe_str(case.get("client_cif", "")),
            safe_str(case.get("product", "")),
            safe_float(case.get("outstanding", 0)),
            safe_int(case.get("dpd", 0)),
            safe_str(case.get("rag_status", "")),
            safe_str(case.get("stage", "")),
            safe_str(case.get("rm_code", "")),
            safe_str(case.get("rm_name", "")),
            safe_str(case.get("branch", "")),
            Json(triggers),
            Json(actions),
            safe_date(case.get("last_updated")),
            safe_date(case.get("created_date")),
            Json(meta)
        ))
        inserted += 1
    except Exception as e:
        errors += 1
        print(f"  SKIP {case.get('id','?')}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} EWS cases. Errors: {errors}")