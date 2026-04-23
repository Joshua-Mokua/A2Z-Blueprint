import os, sys, json
from pathlib import Path
from psycopg2.extras import Json, execute_batch
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

cm_file = Path(__file__).parent / "data" / "credit_monitoring.json"
if not cm_file.exists():
    print("ERROR: data/credit_monitoring.json not found")
    sys.exit(1)

print("Loading credit_monitoring.json (large file — please wait)...")
raw      = json.loads(cm_file.read_text(encoding="utf-8"))
accounts = raw if isinstance(raw, list) else raw.get("accounts", raw.get("watchlist", []))
print(f"Loaded {len(accounts):,} accounts")

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

CORE_FIELDS = ["id","account_number","client_name","client_cif","product",
               "outstanding","dpd","classification","stage","rm_code",
               "rm_name","branch","npl_flag","last_updated"]

inserted = 0
errors   = 0
cur      = conn.cursor()
BATCH    = 500

batch_rows = []

for i, acc in enumerate(accounts):
    try:
        meta = {k: v for k, v in acc.items() if k not in CORE_FIELDS}

        # Handle different field names
        acc_id = acc.get("id") or acc.get("account_id") or f"ACC{i+1:06d}"
        dpd    = safe_int(acc.get("dpd") or acc.get("days_past_due", 0))
        stage  = safe_str(acc.get("stage") or acc.get("ifrs_stage", ""))
        npl    = bool(acc.get("npl_flag") or dpd >= 90)

        batch_rows.append((
            safe_str(acc_id),
            safe_str(acc.get("account_number", "")),
            safe_str(acc.get("client_name", "")),
            safe_str(acc.get("client_cif", "")),
            safe_str(acc.get("product", "")),
            safe_float(acc.get("outstanding", 0)),
            dpd,
            safe_str(acc.get("classification", "")),
            stage,
            safe_str(acc.get("rm_code", "")),
            safe_str(acc.get("rm_name", "")),
            safe_str(acc.get("branch", "")),
            npl,
            safe_date(acc.get("last_updated")),
            Json(meta)
        ))

        if len(batch_rows) >= BATCH:
            execute_batch(cur, """
                INSERT INTO watchlist (
                    id, account_number, client_name, client_cif,
                    product, outstanding, dpd, classification,
                    stage, rm_code, rm_name, branch, npl_flag,
                    last_updated, metadata
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (id) DO UPDATE SET
                    dpd            = EXCLUDED.dpd,
                    outstanding    = EXCLUDED.outstanding,
                    classification = EXCLUDED.classification,
                    npl_flag       = EXCLUDED.npl_flag,
                    last_updated   = EXCLUDED.last_updated
            """, batch_rows)
            conn.commit()
            inserted += len(batch_rows)
            print(f"  {inserted:,} / {len(accounts):,} done...")
            batch_rows = []

    except Exception as e:
        errors += 1
        print(f"  SKIP {acc.get('id','?')}: {e}")
        if errors > 20:
            print("Too many errors. Stopping.")
            conn.rollback()
            sys.exit(1)

# Insert remaining rows
if batch_rows:
    execute_batch(cur, """
        INSERT INTO watchlist (
            id, account_number, client_name, client_cif,
            product, outstanding, dpd, classification,
            stage, rm_code, rm_name, branch, npl_flag,
            last_updated, metadata
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        ON CONFLICT (id) DO UPDATE SET
            dpd            = EXCLUDED.dpd,
            outstanding    = EXCLUDED.outstanding,
            classification = EXCLUDED.classification,
            npl_flag       = EXCLUDED.npl_flag,
            last_updated   = EXCLUDED.last_updated
    """, batch_rows)
    conn.commit()
    inserted += len(batch_rows)

cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted:,} accounts. Errors: {errors}")
print(f"NPL accounts: {sum(1 for a in accounts if safe_int(a.get('dpd',0)) >= 90):,}")