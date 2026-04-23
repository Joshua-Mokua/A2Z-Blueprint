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

cab_file = Path(__file__).parent / "data" / "cab_register.json"
raw      = json.loads(cab_file.read_text(encoding="utf-8"))
changes  = raw if isinstance(raw, list) else raw.get("changes", [])
print(f"Loaded {len(changes)} CAB changes")

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

CORE_FIELDS = ["id","title","system","change_type","risk_level","status",
               "requestor","cab_date","planned_start","planned_end","actual_end",
               "rollback_plan","impact","cbk_notification_required",
               "post_impl_review","pir_outcome","notes"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for c in changes:
    try:
        meta = {k: v for k, v in c.items() if k not in CORE_FIELDS}
        cur.execute("""
            INSERT INTO cab_register (
                id, title, system, change_type, risk_level,
                status, requestor, cab_date, planned_start,
                planned_end, actual_end, rollback_plan, impact,
                cbk_notification_required, post_impl_review,
                pir_outcome, notes, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                status           = EXCLUDED.status,
                post_impl_review = EXCLUDED.post_impl_review,
                pir_outcome      = EXCLUDED.pir_outcome,
                actual_end       = EXCLUDED.actual_end
        """, (
            safe_str(c.get("id","")), safe_str(c.get("title","")),
            safe_str(c.get("system","")), safe_str(c.get("change_type","")),
            safe_str(c.get("risk_level","")), safe_str(c.get("status","")),
            safe_str(c.get("requestor","")), safe_date(c.get("cab_date")),
            safe_date(c.get("planned_start")), safe_date(c.get("planned_end")),
            safe_date(c.get("actual_end")), safe_str(c.get("rollback_plan","")),
            safe_str(c.get("impact","")),
            bool(c.get("cbk_notification_required", False)),
            bool(c.get("post_impl_review", False)),
            safe_str(c.get("pir_outcome","")), safe_str(c.get("notes","")),
            Json(meta)
        ))
        inserted += 1
    except Exception as e:
        errors += 1
        print(f"  SKIP {c.get('id','?')}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} CAB changes. Errors: {errors}")