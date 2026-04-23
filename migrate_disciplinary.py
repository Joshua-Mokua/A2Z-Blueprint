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

disc_file = Path(__file__).parent / "data" / "disciplinary_register.json"
if not disc_file.exists():
    print("ERROR: data/disciplinary_register.json not found")
    sys.exit(1)

raw   = json.loads(disc_file.read_text(encoding="utf-8"))
cases = raw if isinstance(raw, list) else raw.get("cases", [])
print(f"Loaded {len(cases)} disciplinary cases")

def safe_date(val):
    if not val: return None
    try:
        parts = str(val)[:10].split("-")
        if len(parts) == 3: return f"{parts[0]}-{parts[1]}-{parts[2]}"
    except: pass
    return None

def safe_str(val):
    if isinstance(val, (dict, list)): return json.dumps(val)
    return str(val) if val else ""

CORE_FIELDS = ["id","staff_code","staff_name","department","offence_category",
               "offence_date","hearing_date","outcome","sanction","appeal_filed",
               "appeal_outcome","hr_manager","status","confidential","notes",
               "created_date","created_by"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for case in cases:
    try:
        meta = {k: v for k, v in case.items() if k not in CORE_FIELDS}

        cur.execute("""
            INSERT INTO disciplinary (
                id, staff_code, staff_name, department,
                offence_category, offence_date, hearing_date,
                outcome, sanction, appeal_filed, appeal_outcome,
                hr_manager, status, confidential, notes,
                created_date, created_by, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                outcome        = EXCLUDED.outcome,
                sanction       = EXCLUDED.sanction,
                appeal_outcome = EXCLUDED.appeal_outcome,
                status         = EXCLUDED.status,
                notes          = EXCLUDED.notes
        """, (
            safe_str(case.get("id", "")),
            safe_str(case.get("staff_code", "")),
            safe_str(case.get("staff_name", "")),
            safe_str(case.get("department", "")),
            safe_str(case.get("offence_category", "")),
            safe_date(case.get("offence_date")),
            safe_date(case.get("hearing_date")),
            safe_str(case.get("outcome", "")),
            safe_str(case.get("sanction", "")),
            bool(case.get("appeal_filed", False)),
            safe_str(case.get("appeal_outcome", "")),
            safe_str(case.get("hr_manager", "")),
            safe_str(case.get("status", "")),
            bool(case.get("confidential", True)),
            safe_str(case.get("notes", "")),
            safe_date(case.get("created_date")),
            safe_str(case.get("created_by", "")),
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
print(f"Done! Migrated {inserted} disciplinary cases. Errors: {errors}")
print(f"Note: This is confidential data — HR access only")