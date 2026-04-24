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

try:
    import psycopg2
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS)
    conn.autocommit = False
    print("Connected successfully")
except Exception as e:
    print(f"ERROR: {e}"); sys.exit(1)

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

cur = conn.cursor()
total = 0

# ── Partnerships / MOUs ───────────────────────────────────────────
mous = json.loads((DATA/"partnerships_mous.json").read_text(encoding="utf-8"))
print(f"Migrating {len(mous)} MOUs...")
for m in mous:
    try:
        cur.execute("""
            INSERT INTO partnerships (
                id, title, partner_name, partner_type, mou_type,
                department, relationship_manager, signed_date,
                effective_date, expiry_date, status, auto_renew,
                renewal_notice_days, deal_value_kes_m, revenue_share_pct,
                referral_revenue_ytd_m, leads_generated_ytd,
                accounts_opened_ytd, cbk_approval_required,
                cbk_approval_ref, board_approved, legal_reviewed,
                kpis, milestones, notes, created_at, created_by, metadata
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                status                 = EXCLUDED.status,
                referral_revenue_ytd_m = EXCLUDED.referral_revenue_ytd_m,
                leads_generated_ytd    = EXCLUDED.leads_generated_ytd,
                accounts_opened_ytd    = EXCLUDED.accounts_opened_ytd
        """, (
            safe_str(m.get("id","")), safe_str(m.get("title","")),
            safe_str(m.get("partner_name","")), safe_str(m.get("partner_type","")),
            safe_str(m.get("mou_type","")), safe_str(m.get("department","")),
            safe_str(m.get("relationship_manager","")),
            safe_date(m.get("signed_date")), safe_date(m.get("effective_date")),
            safe_date(m.get("expiry_date")), safe_str(m.get("status","")),
            bool(m.get("auto_renew",False)), safe_int(m.get("renewal_notice_days",90)),
            safe_float(m.get("deal_value_kes_m",0)), safe_float(m.get("revenue_share_pct",0)),
            safe_float(m.get("referral_revenue_ytd_m",0)),
            safe_int(m.get("leads_generated_ytd",0)),
            safe_int(m.get("accounts_opened_ytd",0)),
            bool(m.get("cbk_approval_required",False)),
            safe_str(m.get("cbk_approval_ref","")),
            bool(m.get("board_approved",False)), bool(m.get("legal_reviewed",False)),
            Json(m.get("kpis",[])), Json(m.get("milestones",[])),
            safe_str(m.get("notes","")), safe_date(m.get("created_at")),
            safe_str(m.get("created_by","")), Json({})
        ))
        total += 1
    except Exception as e:
        print(f"  SKIP {m.get('id','?')}: {e}")
        conn.rollback()
conn.commit()
print(f"  Done: {total} MOUs")

# ── Referrals ─────────────────────────────────────────────────────
refs = json.loads((DATA/"referrals.json").read_text(encoding="utf-8"))
print(f"Migrating {len(refs)} referrals...")
ref_ct = 0
for r in refs:
    try:
        cur.execute("""
            INSERT INTO referrals (
                id, referral_date, referral_source, referrer_name,
                referrer_code, referee_name, referee_phone,
                product_interested, mou_id, branch, rm_assigned,
                status, converted, conversion_date, account_opened,
                referral_fee_kes, fee_paid, notes
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                status          = EXCLUDED.status,
                converted       = EXCLUDED.converted,
                conversion_date = EXCLUDED.conversion_date,
                fee_paid        = EXCLUDED.fee_paid
        """, (
            safe_str(r.get("id","")), safe_date(r.get("referral_date")),
            safe_str(r.get("referral_source","")), safe_str(r.get("referrer_name","")),
            safe_str(r.get("referrer_code","")), safe_str(r.get("referee_name","")),
            safe_str(r.get("referee_phone","")), safe_str(r.get("product_interested","")),
            safe_str(r.get("mou_id","")), safe_str(r.get("branch","")),
            safe_str(r.get("rm_assigned","")), safe_str(r.get("status","")),
            bool(r.get("converted",False)), safe_date(r.get("conversion_date")),
            safe_str(r.get("account_opened","")),
            safe_float(r.get("referral_fee_kes",0)),
            bool(r.get("fee_paid",False)), safe_str(r.get("notes",""))
        ))
        ref_ct += 1
    except Exception as e:
        print(f"  SKIP {r.get('id','?')}: {e}")
        conn.rollback()
conn.commit()
print(f"  Done: {ref_ct} referrals")

# ── Sponsored Events ──────────────────────────────────────────────
events = json.loads((DATA/"sponsored_events.json").read_text(encoding="utf-8"))
print(f"Migrating {len(events)} events...")
ev_ct = 0
for e in events:
    try:
        cur.execute("""
            INSERT INTO sponsored_events (
                id, name, event_category, category_name, partner,
                mou_id, branch, department, rm_owner,
                start_date, end_date, status, budget_kes, spent_kes,
                target_leads, actual_leads, target_accounts, actual_accounts,
                target_deposits_m, actual_deposits_m,
                catchment_population, reached_count, penetration_pct,
                roi_pct, cost_per_lead_kes, cost_per_account_kes, notes, created_by
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                status          = EXCLUDED.status,
                spent_kes       = EXCLUDED.spent_kes,
                actual_leads    = EXCLUDED.actual_leads,
                actual_accounts = EXCLUDED.actual_accounts,
                penetration_pct = EXCLUDED.penetration_pct,
                roi_pct         = EXCLUDED.roi_pct
        """, (
            safe_str(e.get("id","")), safe_str(e.get("name","")),
            safe_str(e.get("event_category","")), safe_str(e.get("category_name","")),
            safe_str(e.get("partner","")), safe_str(e.get("mou_id","")),
            safe_str(e.get("branch","")), safe_str(e.get("department","")),
            safe_str(e.get("rm_owner","")),
            safe_date(e.get("start_date")), safe_date(e.get("end_date")),
            safe_str(e.get("status","")),
            safe_float(e.get("budget_kes",0)), safe_float(e.get("spent_kes",0)),
            safe_int(e.get("target_leads",0)), safe_int(e.get("actual_leads",0)),
            safe_int(e.get("target_accounts",0)), safe_int(e.get("actual_accounts",0)),
            safe_float(e.get("target_deposits_m",0)), safe_float(e.get("actual_deposits_m",0)),
            safe_int(e.get("catchment_population",0)), safe_int(e.get("reached_count",0)),
            safe_float(e.get("penetration_pct",0)), safe_float(e.get("roi_pct",0)),
            safe_float(e.get("cost_per_lead_kes",0)),
            safe_float(e.get("cost_per_account_kes",0)),
            safe_str(e.get("notes","")), safe_str(e.get("created_by",""))
        ))
        ev_ct += 1
    except Exception as e2:
        print(f"  SKIP {e.get('id','?')}: {e2}")
        conn.rollback()
conn.commit()
print(f"  Done: {ev_ct} events")

# ── Agent Fraud Alerts ────────────────────────────────────────────
alerts = json.loads((DATA/"agent_fraud_alerts.json").read_text(encoding="utf-8"))
print(f"Migrating {len(alerts)} fraud alerts...")
al_ct = 0
for a in alerts:
    try:
        cur.execute("""
            INSERT INTO agent_fraud_alerts (
                id, alert_type, severity, agent_id, agent_name,
                branch, customer_ref, txn_date, txn_count,
                total_amount_kes, threshold_kes, commission_earned,
                excess_commission, txn_ids, amounts, status,
                assigned_to, detected_at, action_taken, notes
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (id) DO UPDATE SET
                status       = EXCLUDED.status,
                action_taken = EXCLUDED.action_taken
        """, (
            safe_str(a.get("id","")), safe_str(a.get("alert_type","")),
            safe_str(a.get("severity","")), safe_str(a.get("agent_id","")),
            safe_str(a.get("agent_name","")), safe_str(a.get("branch","")),
            safe_str(a.get("customer_ref","")), safe_date(a.get("txn_date")),
            safe_int(a.get("txn_count",0)), safe_float(a.get("total_amount_kes",0)),
            safe_float(a.get("threshold_kes",0)), safe_float(a.get("commission_earned",0)),
            safe_float(a.get("excess_commission",0)),
            Json(a.get("txn_ids",[])), Json(a.get("amounts",[])),
            safe_str(a.get("status","")), safe_str(a.get("assigned_to","")),
            safe_date(a.get("detected_at")), safe_str(a.get("action_taken","")),
            safe_str(a.get("notes",""))
        ))
        al_ct += 1
    except Exception as e:
        print(f"  SKIP {a.get('id','?')}: {e}")
        conn.rollback()
conn.commit()

cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Total migrated:")
print(f"  MOUs:         {total}")
print(f"  Referrals:    {ref_ct}")
print(f"  Events:       {ev_ct}")
print(f"  Fraud alerts: {al_ct}")