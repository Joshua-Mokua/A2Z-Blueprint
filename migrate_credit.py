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
print("Loading credit_monitoring.json...")
raw      = json.loads(cm_file.read_text(encoding="utf-8"))
accounts = raw if isinstance(raw, list) else raw.get("watchlist", raw.get("accounts", []))
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

cur       = conn.cursor()
inserted  = 0
errors    = 0
BATCH     = 500
batch_rows= []

for i, acc in enumerate(accounts):
    try:
        covenants = acc.get("covenants", [])
        if isinstance(covenants, str): covenants = []
        migration = acc.get("migration_history", [])
        if isinstance(migration, str): migration = []

        batch_rows.append((
            safe_str(acc.get("id", f"ACC{i+1:06d}")),
            safe_str(acc.get("account_number", "")),
            safe_str(acc.get("client_name", acc.get("rm_name", ""))),
            safe_str(acc.get("cif", acc.get("client_cif", ""))),
            safe_str(acc.get("product", "")),
            safe_float(acc.get("outstanding", 0)),
            safe_int(acc.get("npl_days", acc.get("dpd", 0))),
            safe_str(acc.get("classification", "")),
            safe_str(acc.get("stage", "")),
            safe_str(acc.get("rm_code", "")),
            safe_str(acc.get("rm_name", "")),
            safe_str(acc.get("branch_name", "")),
            bool(safe_int(acc.get("npl_days", 0)) >= 90),
            safe_date(acc.get("last_reviewed")),
            # New columns
            safe_str(acc.get("branch_name", "")),
            safe_str(acc.get("region", "")),
            safe_str(acc.get("branch_code", "")),
            safe_str(acc.get("cif", "")),
            safe_float(acc.get("loan_amount", 0)),
            safe_float(acc.get("collateral_value", 0)),
            safe_str(acc.get("collateral_type", "")),
            safe_date(acc.get("date_added")),
            safe_date(acc.get("last_reviewed")),
            safe_date(acc.get("next_review_due")),
            safe_str(acc.get("account_officer", "")),
            Json(covenants),
            Json(migration),
            safe_str(acc.get("notes", "")),
            safe_str(acc.get("status", "")),
        ))

        if len(batch_rows) >= BATCH:
            execute_batch(cur, """
                INSERT INTO watchlist (
                    id, account_number, client_name, client_cif,
                    product, outstanding, dpd, classification,
                    stage, rm_code, rm_name, branch, npl_flag,
                    last_updated,
                    branch_name, region, branch_code, cif,
                    loan_amount, collateral_value, collateral_type,
                    date_added, last_reviewed, next_review_due,
                    account_officer, covenants, migration_history,
                    notes, status
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (id) DO UPDATE SET
                    outstanding      = EXCLUDED.outstanding,
                    dpd              = EXCLUDED.dpd,
                    classification   = EXCLUDED.classification,
                    npl_flag         = EXCLUDED.npl_flag,
                    region           = EXCLUDED.region,
                    branch_name      = EXCLUDED.branch_name,
                    collateral_value = EXCLUDED.collateral_value,
                    next_review_due  = EXCLUDED.next_review_due,
                    status           = EXCLUDED.status,
                    last_reviewed    = EXCLUDED.last_reviewed
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

# Final batch
if batch_rows:
    execute_batch(cur, """
        INSERT INTO watchlist (
            id, account_number, client_name, client_cif,
            product, outstanding, dpd, classification,
            stage, rm_code, rm_name, branch, npl_flag,
            last_updated,
            branch_name, region, branch_code, cif,
            loan_amount, collateral_value, collateral_type,
            date_added, last_reviewed, next_review_due,
            account_officer, covenants, migration_history,
            notes, status
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        ON CONFLICT (id) DO UPDATE SET
            outstanding      = EXCLUDED.outstanding,
            dpd              = EXCLUDED.dpd,
            classification   = EXCLUDED.classification,
            npl_flag         = EXCLUDED.npl_flag,
            region           = EXCLUDED.region,
            branch_name      = EXCLUDED.branch_name,
            collateral_value = EXCLUDED.collateral_value,
            next_review_due  = EXCLUDED.next_review_due,
            status           = EXCLUDED.status,
            last_reviewed    = EXCLUDED.last_reviewed
    """, batch_rows)
    conn.commit()
    inserted += len(batch_rows)

cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted:,} accounts. Errors: {errors}")