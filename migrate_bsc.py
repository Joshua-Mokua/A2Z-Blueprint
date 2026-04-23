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

scores_file = Path(__file__).parent / "data" / "feb_2026_staff_scores.json"
if not scores_file.exists():
    print("ERROR: data/feb_2026_staff_scores.json not found")
    sys.exit(1)

raw = json.loads(scores_file.read_text(encoding="utf-8"))
print(f"Loaded {len(raw)} staff scores")

def safe_float(val):
    try: return float(val)
    except: return 0.0

def safe_int(val):
    try: return int(val)
    except: return 0

def safe_str(val):
    if isinstance(val, (dict, list)): return json.dumps(val)
    return str(val) if val else ""

inserted = 0
errors   = 0
cur      = conn.cursor()

for username, score in raw.items():
    try:
        cur.execute("""
            INSERT INTO bsc_scores (
                username, staff_code, period, final_score,
                pillar_scores, kpi_scores, n_kpis, avg_ach,
                role, unit, dept
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (username, period) DO UPDATE SET
                final_score   = EXCLUDED.final_score,
                pillar_scores = EXCLUDED.pillar_scores,
                kpi_scores    = EXCLUDED.kpi_scores,
                avg_ach       = EXCLUDED.avg_ach
        """, (
            username,
            safe_str(score.get("staff_code", "")),
            safe_str(score.get("period", "Feb 2026")),
            safe_float(score.get("final_score", 0)),
            Json(score.get("pillar_scores", {})),
            Json(score.get("kpi_scores", {})),
            safe_int(score.get("n_kpis", 0)),
            safe_float(score.get("avg_ach", 0)),
            safe_str(score.get("role", "")),
            safe_str(score.get("unit", "")),
            safe_str(score.get("dept", "")),
        ))
        inserted += 1
        if inserted % 200 == 0:
            print(f"  {inserted} / {len(raw)} done...")
    except Exception as e:
        errors += 1
        print(f"  SKIP {username}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} BSC scores. Errors: {errors}")