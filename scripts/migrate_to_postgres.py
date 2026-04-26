"""scripts/migrate_to_postgres.py — One-shot JSON → PostgreSQL migration.

Run this script ONCE after creating the database schema. It:
  1. Connects to PostgreSQL using A2Z_DB_* environment variables
  2. Creates all tables (idempotent — safe to re-run)
  3. Reads each JSON file and bulk-inserts into the corresponding PG table
  4. Reports success/failure per table

Usage:
    export A2Z_USE_DB=true
    export A2Z_DB_HOST=localhost
    export A2Z_DB_NAME=a2z_mis360
    export A2Z_DB_USER=a2z_app
    export A2Z_DB_PASSWORD="<your password>"
    python scripts/migrate_to_postgres.py

Pre-requisites:
    pip install psycopg2-binary
    psql -U postgres -c "CREATE DATABASE a2z_mis360;"
    psql -U postgres -c "CREATE USER a2z_app WITH PASSWORD 'YourPassword';"
    psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE a2z_mis360 TO a2z_app;"
"""
import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import db, get_schema_sql

DATA = Path(__file__).parent.parent / "data"

# Mapping: JSON file → (PG table, flat columns) for flat-list modules
FLAT_MIGRATIONS = [
    ("cbk_returns.json",              "cbk_returns",              ("id","return_code","return_name","frequency","period","due_date","submitted","on_time","status","department")),
    ("dpo_register.json",             "dpo_register",             ("id","type","subject","risk_level","status","started_date","due_date","completed_date","department")),
    ("sanctions_register.json",       "sanctions_register",       ("id","screening_date","customer_cif","customer_name","list_matched","match_score","status","transaction_blocked","filed_with_cbk")),
    ("capital_liquidity_metrics.json","capital_liquidity_metrics",("id","metric_date","tier1_ratio_pct","total_capital_ratio_pct","leverage_ratio_pct","lcr_pct","nsfr_pct","all_compliant")),
    ("customer_onboarding.json",      "customer_onboarding",      ("id","customer_name","phone","channel","product","started_date","completed_date","current_stage","stages_completed","abandoned","rm_assigned","branch_assigned")),
    ("card_management.json",          "card_management",          ("id","card_number_masked","customer_cif","customer_name","card_type","issue_date","expiry_date","status","ytd_spend_kes","has_dispute","fraud_flagged","branch","rm_code")),
    ("merchant_acquiring.json",       "merchant_acquiring",       ("id","merchant_name","merchant_type","kra_pin","onboarding_date","status","active","pos_terminals","active_terminals","ytd_revenue_kes","branch","rm_code","category")),
    ("op_risk_losses.json",           "op_risk_losses",           ("id","event_date","discovered_date","category","type","description","gross_loss_kes","recovered_kes","net_loss_kes","department","branch","status","regulatory_reportable")),
    ("strategic_initiatives.json",    "strategic_initiatives",    ("id","name","pillar","sponsor","owner","owner_username","start_date","target_end_date","actual_end_date","completion_pct","status","rag_status","budget_kes_m","spent_kes_m","department")),
    ("board_papers.json",             "board_papers",             ("id","title","type","committee","meeting_date","submission_deadline","submitted_date","submitted_on_time","submitted_by","status","action_items","actions_closed","department")),
]

# Nested-dict migrations: {file: {json_key: (pg_table, flat_cols)}}
NESTED_MIGRATIONS = {
    "alm_liquidity.json": {
        "gap_analysis":      ("alm_gap_analysis",     ("id","metric_date","tenor_bucket","assets_kes","liabilities_kes","gap_kes","cumulative_gap_kes")),
        "funding_sources":   ("alm_funding_sources",  ("source","amount_kes_b","concentration_pct","tenor_avg_days","rate_pct","as_of")),
        "alco_meetings":     ("alm_alco_meetings",    ("id","meeting_date","agenda_items","decisions_taken","action_items","actions_closed","attendance_pct")),
        "contingency_plans": ("alm_contingency_plans",("id","trigger","action","tested_date","test_result")),
    },
    "esg_climate.json": {
        "green_loans":              ("esg_green_loans",         ("id","customer","sector","amount_kes_m","tenor_years","interest_rate","carbon_offset_tons_yr","status","verified","esg_score")),
        "esg_initiatives":          ("esg_initiatives",         ("id","name","category","budget_kes_m","spent_kes_m","beneficiaries","completion_pct","department")),
        "climate_risk_assessments": ("esg_climate_assessments", ("id","risk_type","portfolio_segment","exposure_kes_b","risk_score","completed","cbk_reportable")),
        "esg_score":                ("esg_score_snapshot",      ("as_of","overall","environmental","social","governance","rated_by","previous","trend")),
    },
}


def banner(msg):
    print("\n" + "="*72)
    print("  " + msg)
    print("="*72)


def insert_records(table, records, flat_cols):
    """Bulk insert records into a PG table. Splits flat columns from JSONB data."""
    if not records: return 0

    inserted = 0
    skipped  = 0
    with db.transaction() as conn:
        # Truncate table first to avoid duplicates on re-run
        try:
            db.execute(f"DELETE FROM {table}", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate {table}: {e}")

        for rec in records:
            if not isinstance(rec, dict):
                skipped += 1; continue

            flat_data = {c: rec.get(c) for c in flat_cols if c in rec}
            nested    = {k: v for k, v in rec.items() if k not in flat_cols}
            flat_data["data"] = json.dumps(nested, default=str)

            cols    = list(flat_data.keys())
            vals    = list(flat_data.values())
            ph      = ", ".join(["%s"] * len(cols))
            col_str = ", ".join(f'"{c}"' for c in cols)
            sql     = f"INSERT INTO {table} ({col_str}) VALUES ({ph})"
            try:
                db.execute(sql, tuple(vals), conn=conn)
                inserted += 1
            except Exception as e:
                print(f"  ⚠️ Skipped row in {table}: {str(e)[:80]}")
                skipped += 1
    return inserted


def main():
    banner("A2Z Blueprint — JSON → PostgreSQL Migration")

    # 1. Pre-flight checks
    if not db.is_postgres_ready():
        print("❌ PostgreSQL is not configured.")
        print("   Set environment variables: A2Z_USE_DB=true, A2Z_DB_HOST, A2Z_DB_NAME, A2Z_DB_USER, A2Z_DB_PASSWORD")
        return 1

    health = db.health_check()
    print(f"✅ Connected to {health.get('host')} / {health.get('database')}")
    print(f"   Version: {health.get('version','')}")
    print(f"   Size:    {health.get('db_size','')}")

    # 2. Apply schema
    banner("STEP 1 — Applying schema (CREATE TABLE IF NOT EXISTS)")
    schema = get_schema_sql()
    try:
        with db.transaction() as conn:
            with conn.cursor() as cur:
                # PostgreSQL can handle the whole schema in one go
                cur.execute(schema)
        print("✅ Schema applied")
    except Exception as e:
        print(f"❌ Schema apply failed: {e}")
        return 1

    # 3. Migrate flat-list modules
    banner("STEP 2 — Migrating flat-list modules (10 tables)")
    total_inserted = 0
    for fname, table, flat_cols in FLAT_MIGRATIONS:
        path = DATA / fname
        if not path.exists():
            print(f"  ⚠️ {fname:<35} SKIPPED (file not found)")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                print(f"  ⚠️ {fname:<35} SKIPPED (not a list)")
                continue
            n = insert_records(table, data, flat_cols)
            total_inserted += n
            print(f"  ✅ {fname:<35} → {table:<28} {n:>6} rows")
        except Exception as e:
            print(f"  ❌ {fname:<35} FAILED: {str(e)[:60]}")

    # 4. Migrate nested-dict modules (ALM, ESG)
    banner("STEP 3 — Migrating nested-dict modules (8 tables)")
    for fname, sub_map in NESTED_MIGRATIONS.items():
        path = DATA / fname
        if not path.exists():
            print(f"  ⚠️ {fname:<35} SKIPPED")
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            for json_key, (table, flat_cols) in sub_map.items():
                value = doc.get(json_key)
                if value is None:
                    print(f"  ⚠️ {fname}/{json_key} → {table}  EMPTY")
                    continue
                # esg_score is a single dict, not a list — wrap it
                records = [value] if isinstance(value, dict) else value
                n = insert_records(table, records, flat_cols)
                total_inserted += n
                print(f"  ✅ {fname:<22} {json_key:<28} → {table:<28} {n:>6} rows")
        except Exception as e:
            print(f"  ❌ {fname:<35} FAILED: {str(e)[:60]}")

    # 5. Migrate FLEXCUBE config and events
    banner("STEP 4 — Migrating FLEXCUBE config & events")
    flx_cfg_path = DATA / "flexcube_config.json"
    if flx_cfg_path.exists():
        try:
            cfg = json.loads(flx_cfg_path.read_text(encoding="utf-8"))
            db.execute("DELETE FROM flexcube_config WHERE id = %s", ("singleton",))
            db.execute(
                "INSERT INTO flexcube_config (id, mode, config_json) VALUES (%s, %s, %s)",
                ("singleton", cfg.get("mode","synthetic"), json.dumps(cfg))
            )
            print(f"  ✅ flexcube_config.json migrated (mode={cfg.get('mode')})")
        except Exception as e:
            print(f"  ❌ flexcube_config.json failed: {e}")

    flx_evt_path = DATA / "flexcube_events.json"
    if flx_evt_path.exists():
        try:
            events = json.loads(flx_evt_path.read_text(encoding="utf-8"))
            with db.transaction() as conn:
                db.execute("DELETE FROM flexcube_events", conn=conn)
                for e in events:
                    db.execute(
                        "INSERT INTO flexcube_events (timestamp, topic, payload, mode) VALUES (%s,%s,%s,%s)",
                        (e.get("timestamp"), e.get("topic"), json.dumps(e.get("payload",{})), e.get("mode","synthetic")),
                        conn=conn
                    )
            print(f"  ✅ flexcube_events.json migrated ({len(events)} events)")
        except Exception as e:
            print(f"  ❌ flexcube_events.json failed: {e}")

    # 6. Migrate module_config
    banner("STEP 5 — Migrating module_config.json")
    mc_path = DATA / "module_config.json"
    if mc_path.exists():
        try:
            mc = json.loads(mc_path.read_text(encoding="utf-8"))
            with db.transaction() as conn:
                db.execute("DELETE FROM module_config", conn=conn)
                for module_key, config in mc.items():
                    db.execute(
                        """INSERT INTO module_config
                           (module_key, hardcoded, configurable, bsc_kpis, dept, nav_groups, last_updated_by)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (module_key,
                         json.dumps(config.get("hardcoded",{})),
                         json.dumps(config.get("configurable",{})),
                         json.dumps(config.get("bsc_kpis",[])),
                         config.get("dept",""),
                         json.dumps(config.get("nav_groups",[])),
                         config.get("last_updated_by","migration")),
                        conn=conn
                    )
            print(f"  ✅ module_config.json migrated ({len(mc)} modules)")
        except Exception as e:
            print(f"  ❌ module_config.json failed: {e}")

    # 7. Summary
    banner("MIGRATION COMPLETE")
    print(f"  Total records migrated: {total_inserted:,}")
    print()
    print("  NEXT STEPS:")
    print("    1. Verify data: SELECT count(*) FROM cbk_returns; (etc.)")
    print("    2. Edit utils/db.py — set TABLE_USE_DB[<table>] = True for each migrated table")
    print("    3. Restart Streamlit — pages will now read from PostgreSQL")
    print("    4. JSON files remain as backup. Delete only after 30 days of stable PG operation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
