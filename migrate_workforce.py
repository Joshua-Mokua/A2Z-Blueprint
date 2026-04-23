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

wf_file = Path(__file__).parent / "data" / "workforce_planning.json"
raw     = json.loads(wf_file.read_text(encoding="utf-8"))
depts   = raw.get("by_department", []) if isinstance(raw, dict) else raw
print(f"Loaded {len(depts)} departments")

def safe_float(val):
    try: return float(val)
    except: return 0.0

def safe_int(val):
    try: return int(val)
    except: return 0

def safe_str(val):
    if isinstance(val, (dict, list)): return json.dumps(val)
    return str(val) if val else ""

CORE_FIELDS = ["department","actual_headcount","budgeted_headcount",
               "open_positions","attrition_ytd","attrition_rate_pct",
               "avg_tenure_years","gender_ratio_f_pct","succession_depth",
               "critical_roles","critical_roles_covered"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for d in depts:
    try:
        meta = {k: v for k, v in d.items() if k not in CORE_FIELDS}
        cur.execute("""
            INSERT INTO workforce (
                department, actual_headcount, budgeted_headcount,
                open_positions, attrition_ytd, attrition_rate_pct,
                avg_tenure_years, gender_ratio_f_pct, succession_depth,
                critical_roles, critical_roles_covered, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (department) DO UPDATE SET
                actual_headcount   = EXCLUDED.actual_headcount,
                budgeted_headcount = EXCLUDED.budgeted_headcount,
                open_positions     = EXCLUDED.open_positions,
                attrition_rate_pct = EXCLUDED.attrition_rate_pct,
                succession_depth   = EXCLUDED.succession_depth
        """, (
            safe_str(d.get("department","")),
            safe_int(d.get("actual_headcount",0)),
            safe_int(d.get("budgeted_headcount",0)),
            safe_int(d.get("open_positions",0)),
            safe_int(d.get("attrition_ytd",0)),
            safe_float(d.get("attrition_rate_pct",0)),
            safe_float(d.get("avg_tenure_years",0)),
            safe_float(d.get("gender_ratio_f_pct",0)),
            safe_str(d.get("succession_depth","")),
            safe_int(d.get("critical_roles",0)),
            safe_int(d.get("critical_roles_covered",0)),
            Json(meta)
        ))
        inserted += 1
    except Exception as e:
        errors += 1
        print(f"  SKIP {d.get('department','?')}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} departments. Errors: {errors}")