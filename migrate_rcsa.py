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

rcsa_file = Path(__file__).parent / "data" / "rcsa_register.json"
if not rcsa_file.exists():
    print("ERROR: data/rcsa_register.json not found")
    sys.exit(1)

raw   = json.loads(rcsa_file.read_text(encoding="utf-8"))
risks = raw if isinstance(raw, list) else raw.get("risks", [])
print(f"Loaded {len(risks)} RCSA risks")

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

CORE_FIELDS = ["id","category","description","department","inherent_likelihood",
               "inherent_impact","inherent_score","control_description",
               "control_effectiveness","residual_score","residual_rating",
               "risk_owner","last_reviewed","next_review","action_required",
               "action_plan","kri","kri_value","kri_threshold","kri_breached","notes"]

inserted = 0
errors   = 0
cur      = conn.cursor()

for risk in risks:
    try:
        meta = {k: v for k, v in risk.items() if k not in CORE_FIELDS}

        cur.execute("""
            INSERT INTO rcsa_risks (
                id, category, description, department,
                inherent_likelihood, inherent_impact, inherent_score,
                control_description, control_effectiveness,
                residual_score, residual_rating, risk_owner,
                last_reviewed, next_review, action_required,
                action_plan, kri, kri_value, kri_threshold,
                kri_breached, notes, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                residual_score       = EXCLUDED.residual_score,
                residual_rating      = EXCLUDED.residual_rating,
                control_effectiveness= EXCLUDED.control_effectiveness,
                action_required      = EXCLUDED.action_required,
                kri_breached         = EXCLUDED.kri_breached,
                last_reviewed        = EXCLUDED.last_reviewed
        """, (
            safe_str(risk.get("id", "")),
            safe_str(risk.get("category", "")),
            safe_str(risk.get("description", "")),
            safe_str(risk.get("department", "")),
            safe_int(risk.get("inherent_likelihood", 0)),
            safe_int(risk.get("inherent_impact", 0)),
            safe_float(risk.get("inherent_score", 0)),
            safe_str(risk.get("control_description", "")),
            safe_str(risk.get("control_effectiveness", "")),
            safe_float(risk.get("residual_score", 0)),
            safe_str(risk.get("residual_rating", "")),
            safe_str(risk.get("risk_owner", "")),
            safe_date(risk.get("last_reviewed")),
            safe_date(risk.get("next_review")),
            bool(risk.get("action_required", False)),
            safe_str(risk.get("action_plan", "")),
            safe_str(risk.get("kri", "")),
            safe_float(risk.get("kri_value", 0)),
            safe_float(risk.get("kri_threshold", 0)),
            bool(risk.get("kri_breached", False)),
            safe_str(risk.get("notes", "")),
            Json(meta)
        ))
        inserted += 1
    except Exception as e:
        errors += 1
        print(f"  SKIP {risk.get('id','?')}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Stopping.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted} RCSA risks. Errors: {errors}")