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

proj_file = Path(__file__).parent / "data" / "projects.json"
if not proj_file.exists():
    print("ERROR: data/projects.json not found")
    sys.exit(1)

raw      = json.loads(proj_file.read_text(encoding="utf-8"))
projects = raw if isinstance(raw, list) else raw.get("projects", [])
print(f"Loaded {len(projects)} projects")

def safe_date(val):
    if not val: return None
    try:
        parts = str(val)[:10].split("-")
        if len(parts) == 3: return f"{parts[0]}-{parts[1]}-{parts[2]}"
    except: pass
    return None

def safe_float(val):
    try: return float(val)
    except: return 0.0

def safe_int(val):
    try: return int(val)
    except: return 0

def safe_str(val):
    if isinstance(val, (dict, list)): return json.dumps(val)
    return str(val) if val else ""

CORE_FIELDS = ["id","name","description","initiative_id","category","priority",
               "status","project_manager","sponsor","department","start_date",
               "planned_end_date","actual_end_date","budget_m","spent_m",
               "pct_complete","pct_budget_used","rag_status","risks",
               "open_issues","milestones","stakeholders","last_updated","notes"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for proj in projects:
    try:
        meta = {k: v for k, v in proj.items() if k not in CORE_FIELDS}

        milestones   = proj.get("milestones", [])
        stakeholders = proj.get("stakeholders", [])
        if isinstance(milestones, str):   milestones   = []
        if isinstance(stakeholders, str): stakeholders = []

        cur.execute("""
            INSERT INTO projects (
                id, name, description, initiative_id,
                category, priority, status, project_manager,
                sponsor, department, start_date, planned_end_date,
                actual_end_date, budget_m, spent_m, pct_complete,
                pct_budget_used, rag_status, risks, open_issues,
                milestones, stakeholders, last_updated, notes, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                status          = EXCLUDED.status,
                pct_complete    = EXCLUDED.pct_complete,
                rag_status      = EXCLUDED.rag_status,
                spent_m         = EXCLUDED.spent_m,
                pct_budget_used = EXCLUDED.pct_budget_used,
                open_issues     = EXCLUDED.open_issues,
                milestones      = EXCLUDED.milestones,
                last_updated    = EXCLUDED.last_updated
        """, (
            safe_str(proj.get("id", "")),
            safe_str(proj.get("name", "")),
            safe_str(proj.get("description", "")),
            safe_str(proj.get("initiative_id", "")),
            safe_str(proj.get("category", "")),
            safe_str(proj.get("priority", "")),
            safe_str(proj.get("status", "")),
            safe_str(proj.get("project_manager", "")),
            safe_str(proj.get("sponsor", "")),
            safe_str(proj.get("department", "")),
            safe_date(proj.get("start_date")),
            safe_date(proj.get("planned_end_date")),
            safe_date(proj.get("actual_end_date")),
            safe_float(proj.get("budget_m", 0)),
            safe_float(proj.get("spent_m", 0)),
            safe_int(proj.get("pct_complete", 0)),
            safe_float(proj.get("pct_budget_used", 0)),
            safe_str(proj.get("rag_status", "Green")),
            safe_int(proj.get("risks", 0)),
            safe_int(proj.get("open_issues", 0)),
            Json(milestones),
            Json(stakeholders),
            safe_date(proj.get("last_updated")),
            safe_str(proj.get("notes", "")),
            Json(meta)
        ))
        inserted += 1
    except Exception as e:
        errors += 1
        print(f"  SKIP {proj.get('id','?')}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} projects. Errors: {errors}")