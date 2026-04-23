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

DATA = Path(__file__).parent / "data"

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

def load(fname):
    p = DATA / fname
    if not p.exists():
        print(f"  WARNING: {fname} not found — skipping")
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []

cur = conn.cursor()
total = 0

# ── Purchase Requests ─────────────────────────────────────────────
prs = load("purchase_requests.json")
print(f"Migrating {len(prs)} purchase requests...")
for r in prs:
    try:
        cur.execute("""
            INSERT INTO purchase_requests (
                id, title, category, requested_by, department,
                amount_kes, currency, vendor_preferred, justification,
                status, request_date, approved_by, approval_date,
                po_id, budget_line, urgent, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                status       = EXCLUDED.status,
                approved_by  = EXCLUDED.approved_by,
                approval_date= EXCLUDED.approval_date
        """, (
            safe_str(r.get("id","")), safe_str(r.get("title","")),
            safe_str(r.get("category","")), safe_str(r.get("requested_by","")),
            safe_str(r.get("department","")), safe_float(r.get("amount_kes",0)),
            safe_str(r.get("currency","KES")), safe_str(r.get("vendor_preferred","")),
            safe_str(r.get("justification","")), safe_str(r.get("status","")),
            safe_date(r.get("request_date")), safe_str(r.get("approved_by","")),
            safe_date(r.get("approval_date")), safe_str(r.get("po_id","")),
            safe_str(r.get("budget_line","")), bool(r.get("urgent",False)),
            safe_str(r.get("notes",""))
        ))
        total += 1
    except Exception as e:
        print(f"  SKIP {r.get('id','?')}: {e}")
        conn.rollback()
conn.commit()
print(f"  Done: {len(prs)} purchase requests")

# ── Purchase Orders ───────────────────────────────────────────────
pos = load("purchase_orders.json")
print(f"Migrating {len(pos)} purchase orders...")
for r in pos:
    try:
        items = r.get("items", [])
        if isinstance(items, str): items = []
        cur.execute("""
            INSERT INTO purchase_orders (
                id, pr_id, vendor, department, category,
                amount_kes, currency, issue_date, delivery_date,
                status, items, goods_received_note, delivery_note_ref,
                invoice_id, three_way_match, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                status          = EXCLUDED.status,
                three_way_match = EXCLUDED.three_way_match
        """, (
            safe_str(r.get("id","")), safe_str(r.get("pr_id","")),
            safe_str(r.get("vendor","")), safe_str(r.get("department","")),
            safe_str(r.get("category","")), safe_float(r.get("amount_kes",0)),
            safe_str(r.get("currency","KES")), safe_date(r.get("issue_date")),
            safe_date(r.get("delivery_date")), safe_str(r.get("status","")),
            Json(items), safe_str(r.get("goods_received_note","")),
            safe_str(r.get("delivery_note_ref","")), safe_str(r.get("invoice_id","")),
            bool(r.get("3way_match", r.get("three_way_match",False))),
            safe_str(r.get("notes",""))
        ))
        total += 1
    except Exception as e:
        print(f"  SKIP {r.get('id','?')}: {e}")
        conn.rollback()
conn.commit()
print(f"  Done: {len(pos)} purchase orders")

# ── Invoices ──────────────────────────────────────────────────────
invs = load("invoices.json")
print(f"Migrating {len(invs)} invoices...")
for r in invs:
    try:
        cur.execute("""
            INSERT INTO invoices (
                id, po_id, pr_id, vendor, department, category,
                amount_kes, invoice_date, due_date, status,
                payment_date, payment_ref, three_way_match,
                match_status, finance_approved, dispute_reason, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                status           = EXCLUDED.status,
                payment_date     = EXCLUDED.payment_date,
                payment_ref      = EXCLUDED.payment_ref,
                finance_approved = EXCLUDED.finance_approved
        """, (
            safe_str(r.get("id","")), safe_str(r.get("po_id","")),
            safe_str(r.get("pr_id","")), safe_str(r.get("vendor","")),
            safe_str(r.get("department","")), safe_str(r.get("category","")),
            safe_float(r.get("amount_kes",0)), safe_date(r.get("invoice_date")),
            safe_date(r.get("due_date")), safe_str(r.get("status","")),
            safe_date(r.get("payment_date")), safe_str(r.get("payment_ref","")),
            bool(r.get("3way_match", r.get("three_way_match",False))),
            safe_str(r.get("match_status","")),
            bool(r.get("finance_approved",False)),
            safe_str(r.get("dispute_reason","")), safe_str(r.get("notes",""))
        ))
        total += 1
    except Exception as e:
        print(f"  SKIP {r.get('id','?')}: {e}")
        conn.rollback()
conn.commit()
print(f"  Done: {len(invs)} invoices")

# ── Vendors ───────────────────────────────────────────────────────
vends = load("vendor_register.json")
print(f"Migrating {len(vends)} vendors...")
for r in vends:
    try:
        bank = r.get("bank_details", {})
        if isinstance(bank, str): bank = {}
        cur.execute("""
            INSERT INTO vendors (
                id, name, category, kra_pin, registration_no,
                contact_person, phone, email, address, status,
                onboarding_date, last_reviewed, next_review,
                tax_compliance, insurance_valid, bank_details,
                rating, total_spend_ytd_m, open_pos, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                status         = EXCLUDED.status,
                tax_compliance = EXCLUDED.tax_compliance,
                insurance_valid= EXCLUDED.insurance_valid,
                rating         = EXCLUDED.rating,
                last_reviewed  = EXCLUDED.last_reviewed
        """, (
            safe_str(r.get("id","")), safe_str(r.get("name","")),
            safe_str(r.get("category","")), safe_str(r.get("kra_pin","")),
            safe_str(r.get("registration_no","")), safe_str(r.get("contact_person","")),
            safe_str(r.get("phone","")), safe_str(r.get("email","")),
            safe_str(r.get("address","")), safe_str(r.get("status","")),
            safe_date(r.get("onboarding_date")), safe_date(r.get("last_reviewed")),
            safe_date(r.get("next_review")),
            bool(r.get("tax_compliance",False)), bool(r.get("insurance_valid",False)),
            Json(bank), safe_float(r.get("rating",0)),
            safe_float(r.get("total_spend_ytd_m",0)),
            safe_int(r.get("open_pos",0)), safe_str(r.get("notes",""))
        ))
        total += 1
    except Exception as e:
        print(f"  SKIP {r.get('id','?')}: {e}")
        conn.rollback()
conn.commit()
print(f"  Done: {len(vends)} vendors")

# ── Assets ────────────────────────────────────────────────────────
assets = load("asset_register.json")
print(f"Migrating {len(assets)} assets...")
for r in assets:
    try:
        cur.execute("""
            INSERT INTO assets (
                id, name, category, make_model, serial_number,
                location, assigned_to_dept, custodian, purchase_date,
                purchase_cost_kes, vendor, useful_life_years,
                depreciation_rate_pct, accumulated_dep_kes,
                net_book_value_kes, condition, warranty_expiry,
                last_inspection, next_inspection, insurance_policy,
                disposal_date, disposal_reason, barcode, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                condition          = EXCLUDED.condition,
                net_book_value_kes = EXCLUDED.net_book_value_kes,
                accumulated_dep_kes= EXCLUDED.accumulated_dep_kes,
                last_inspection    = EXCLUDED.last_inspection,
                disposal_date      = EXCLUDED.disposal_date
        """, (
            safe_str(r.get("id","")), safe_str(r.get("name","")),
            safe_str(r.get("category","")), safe_str(r.get("make_model","")),
            safe_str(r.get("serial_number","")), safe_str(r.get("location","")),
            safe_str(r.get("assigned_to_dept","")), safe_str(r.get("custodian","")),
            safe_date(r.get("purchase_date")), safe_float(r.get("purchase_cost_kes",0)),
            safe_str(r.get("vendor","")), safe_int(r.get("useful_life_years",0)),
            safe_float(r.get("depreciation_rate_pct",0)),
            safe_float(r.get("accumulated_dep_kes",0)),
            safe_float(r.get("net_book_value_kes",0)),
            safe_str(r.get("condition","")),
            safe_date(r.get("warranty_expiry")), safe_date(r.get("last_inspection")),
            safe_date(r.get("next_inspection")), safe_str(r.get("insurance_policy","")),
            safe_date(r.get("disposal_date")), safe_str(r.get("disposal_reason","")),
            safe_str(r.get("barcode","")), safe_str(r.get("notes",""))
        ))
        total += 1
    except Exception as e:
        print(f"  SKIP {r.get('id','?')}: {e}")
        conn.rollback()
conn.commit()
print(f"  Done: {len(assets)} assets")

# ── Contracts ─────────────────────────────────────────────────────
cons = load("contracts.json")
print(f"Migrating {len(cons)} contracts...")
for r in cons:
    try:
        cur.execute("""
            INSERT INTO contracts (
                id, title, vendor, category, contract_type,
                department, value_kes, start_date, end_date,
                status, auto_renew, renewal_notice_days,
                signed_by, contract_manager, document_ref,
                sla_terms, penalties, notes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                status     = EXCLUDED.status,
                auto_renew = EXCLUDED.auto_renew
        """, (
            safe_str(r.get("id","")), safe_str(r.get("title","")),
            safe_str(r.get("vendor","")), safe_str(r.get("category","")),
            safe_str(r.get("contract_type","")), safe_str(r.get("department","")),
            safe_float(r.get("value_kes",0)), safe_date(r.get("start_date")),
            safe_date(r.get("end_date")), safe_str(r.get("status","")),
            bool(r.get("auto_renew",False)), safe_int(r.get("renewal_notice_days",30)),
            safe_str(r.get("signed_by","")), safe_str(r.get("contract_manager","")),
            safe_str(r.get("document_ref","")), safe_str(r.get("sla_terms","")),
            bool(r.get("penalties",False)), safe_str(r.get("notes",""))
        ))
        total += 1
    except Exception as e:
        print(f"  SKIP {r.get('id','?')}: {e}")
        conn.rollback()
conn.commit()

cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Total records migrated: {total}")
print(f"  Purchase requests: {len(prs)}")
print(f"  Purchase orders:   {len(pos)}")
print(f"  Invoices:          {len(invs)}")
print(f"  Vendors:           {len(vends)}")
print(f"  Assets:            {len(assets)}")
print(f"  Contracts:         {len(cons)}")