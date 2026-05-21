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
    # ── v10.129: integration-layer operational tables (Phase 1D shim) ──────
    # First entry from the integration layer's wired-39 set. Read path goes
    # through utils/actuals_engine._read_operational_table() — set
    # _data_source.per_table.sla_tickets = "pg_view" in
    # data/integration_layer_config.json to switch reads JSON → PG.
    ("sla_tickets.json",              "sla_tickets",              ("id","title","category","priority","sla_target_hours","sla_target_days","assignee","requester","department","branch","status","raised_date","resolved_date","actual_hours","actual_days","within_sla","escalation_count","description","last_updated")),
    # ── v10.130: integration-layer operational tables — debt_recovery ──────
    # Second entry. 4 wired rules (K027, K113, K044, Collection Throughput) —
    # higher rule density than sla_tickets, proves the shim handles multi-
    # rule tables identically.
    ("debt_recovery.json",            "debt_recovery",            ("id","account_number","client_cif","debtor_name","outstanding","loan_amount","dpd","npl_days","product","branch","rm_code","recovery_stage","collateral_type","collateral_value","ltvr","recovery_officer","recovery_officer_code","last_contact","next_action","settlement_offer","amount_recovered","legal_referral","legal_firm","demand_letters_sent","status","created_date","last_updated","notes")),
    ("customer_onboarding.json",      "customer_onboarding",      ("id","customer_name","phone","channel","product","started_date","completed_date","current_stage","stages_completed","abandoned","rm_assigned","branch_assigned")),
    ("card_management.json",          "card_management",          ("id","card_number_masked","customer_cif","customer_name","card_type","issue_date","expiry_date","status","ytd_spend_kes","has_dispute","fraud_flagged","branch","rm_code")),
    ("merchant_acquiring.json",       "merchant_acquiring",       ("id","merchant_name","merchant_type","kra_pin","onboarding_date","status","active","pos_terminals","active_terminals","ytd_revenue_kes","branch","rm_code","category")),
    ("op_risk_losses.json",           "op_risk_losses",           ("id","event_date","discovered_date","category","type","description","gross_loss_kes","recovered_kes","net_loss_kes","department","branch","status","regulatory_reportable")),
    ("strategic_initiatives.json",    "strategic_initiatives",    ("id","name","pillar","sponsor","owner","owner_username","start_date","target_end_date","actual_end_date","completion_pct","status","rag_status","budget_kes_m","spent_kes_m","department")),
    ("board_papers.json",             "board_papers",             ("id","title","type","committee","meeting_date","submission_deadline","submitted_date","submitted_on_time","submitted_by","status","action_items","actions_closed","department")),
    # ── v10.88: PG migration batch 1 (anti-drift Phase 1A) ─────────────────
    ("agent_fraud_alerts.json",       "agent_fraud_alerts",       ("id","alert_type","severity","agent_id","agent_name","branch","customer_ref","txn_date","txn_count","total_amount_kes","threshold_kes","commission_earned","excess_commission","status","assigned_to","detected_at","action_taken","notes")),
    ("agents_data.json",              "agents_data",              ("id","name","town","float_balance","float_limit","txn_count_today","txn_value_today_kes","status","uptime_30d_pct","float_utilisation_pct","last_txn","onboarding_date","compliance_docs_complete")),
    ("agent_transactions.json",       "agent_transactions",       ("id","agent_id","agent_name","branch","txn_date","txn_hour","txn_minute","txn_type","amount_kes","customer_ref","commission_kes","fraud_flag")),
    ("aml_alerts.json",               "aml_alerts",               ("id","account_number","customer_name","transaction_date","amount","transaction_type","rule_triggered","risk_score","risk_level","status","assigned_to","str_filed","str_reference","notes","created_at","updated_at")),
    ("asset_register.json",           "asset_register",           ("id","name","category","make_model","serial_number","location","assigned_to_dept","custodian","purchase_date","purchase_cost_kes","vendor","useful_life_years","depreciation_rate_pct","accumulated_dep_kes","net_book_value_kes","condition","warranty_expiry","last_inspection","next_inspection","insurance_policy","disposal_date","disposal_reason","barcode","notes")),
    ("bid_bonds.json",                "bid_bonds",                ("id","reference","bond_type","customer_name","customer_cif","beneficiary","project_name","amount_kes","currency","commission_pct","commission_kes","issue_date","expiry_date","status","collateral_type","collateral_value","rm_code","credit_approved_by","cbk_reported","called","called_amount","extended_count","notes","officer_username","cbk_reportable","principal")),
    # ── v10.89: PG migration batch 2 (anti-drift Phase 1A; +8 flat) ─────────
    ("ifrs9_loans.json",              "ifrs9_loans",              ("account_id","client_name","product","outstanding","stage","ecl_basis","npl_days","pd_12m","lgd","ead","ecl_amount","sicr_flag","reporting_date")),
    # ── v10.131: integration-layer designation for pre-existing PG table ───
    # loan_applications has been a PG-backed table since v10.89 (this entry
    # was added then). v10.131 designates it part of the integration layer's
    # PG-eligible set — 6 wired rules (K001/K010/K011/K115/K045/K046) become
    # PG-capable when banks set _data_source.per_table.loan_applications =
    # "pg_view" / "auto" in integration_layer_config.json. Higher rule
    # density than v10.130's debt_recovery (4) — most aggressive density
    # check yet for the v10.116 _data_source shim. Proves the shim works
    # with PRE-EXISTING PG tables, not just newly-migrated ones.
    ("loan_applications.json",        "loan_applications",        ("id","pipeline_deal_id","client_name","client_cif","product","amount","currency","swim_lane","status","application_date","rm_code","rm_name","rm_unit","is_repeat_borrower","clean_repayment_history","completeness_score","compliance_flag","compliance_type","appraisal_notes","tat_days","sla_target_days","last_updated","proposition_tag","deal_category")),
    ("legal_matters.json",            "legal_matters",            ("id","matter_type","status","priority","opened_date","sla_due_date","completed_date","days_elapsed","days_to_sla","sla_days","sla_breached","sla_kpi","client_name","client_cif","application_id","product","amount","attorney","attorney_ref","steps_total","steps_completed","current_step","next_step","next_action_date","notes","last_updated","proposition_tag")),
    ("rms_reconciliations.json",      "rms_reconciliations",      ("id","recon_type","account_code","account_name","account_type","period","cbs_balance","gl_balance","variance","abs_variance","currency","status","breaker_type","assigned_to","raised_date","due_date","resolved_date","ageing_days","notes","last_updated","amount")),
    ("debt_recovery.json",            "debt_recovery",            ("id","account_number","client_cif","debtor_name","outstanding","loan_amount","dpd","npl_days","product","branch","rm_code","recovery_stage","collateral_type","collateral_value","ltvr","recovery_officer","recovery_officer_code","last_contact","next_action","settlement_offer","amount_recovered","legal_referral","legal_firm","demand_letters_sent","status","created_date","last_updated","notes")),
    ("cims_tickets.json",             "cims_tickets",             ("id","instruction_type","client_name","client_cif","account_number","branch","rm_code","rm_name","priority","opened_date","sla_hours","due_date","status","resolved_date","escalated_to","notes","last_updated")),
    ("treasury_fd.json",              "treasury_fd",              ("id","pipeline_deal_id","client_name","client_cif","product","amount","currency","tenure_days","proposed_rate","ratified_rate","market_rate_ref","status","rm_code","rm_name","rm_unit","submitted_date","ratified_date","treasury_officer","counter_rate","notes","booked_date","maturity_date","proposition_tag")),
    ("bnc_policies.json",             "bnc_policies",             ("id","product","insurer","category","premium_annual","commission_pct","commission_kes","client_cif","branch","rm_code","inception_date","expiry_date","status","claim_raised","claim_status","claim_amount")),
    # ── v10.90: PG migration batch 3 (anti-drift Phase 1A; +7 flat) ─────────
    ("staff_history.json",            "staff_history",            ("staff_code","staff_name","movement_type","from_role","to_role","from_unit","to_unit","effective_date","approved_by","letter_ref")),
    ("pipeline.json",                 "pipeline",                 ("id","staff_code","staff_name","unit","role","client_name","product","stage","amount","currency","open_date","expected_close","probability","notes","last_updated","conflict_status","proposition_tag","win_probability_ai","is_repeat_borrower","deal_category","existing_facility_id","client_cif","top_up_amount","original_facility_amount","repayment_history")),
    ("lms_enrollments.json",          "lms_enrollments",          ("staff_code","staff_name","role","dept","course_id","course_title","cbk_mandatory","status","completion_date","score","due_date")),
    ("edms_documents.json",           "edms_documents",           ("id","category","document_type","title","client_name","client_cif","linked_type","linked_id","file_name","file_size_kb","pages","uploaded_date","uploaded_by","branch","access_level","status","expiry_date","is_expired","requires_review","reviewed_by","review_date","version","notes","last_updated")),
    ("revenue_assurance.json",        "revenue_assurance",        ("id","type","fee_type","branch","amount","currency","date_raised","period","reason","client_name","client_cif","raised_by","raised_code","status","recovered","recovered_amount","authorised_by","notes","last_updated")),
    ("treasury_fx.json",              "treasury_fx",              ("id","deal_type","direction","currency","fcy_amount","rate","kes_amount","counterparty","counterparty_type","dealer","trade_date","value_date","status","margin_kes","notes")),
    ("credit_admin.json",             "credit_admin",             ("id","application_id","client_name","product","amount","rm_code","rm_name","approval_date","all_conditions_met","ready_for_disbursement","disbursed","disbursement_date","last_updated")),
    # ── v10.91: PG migration batch 4 (anti-drift Phase 1A close-out; +9 flat) ─
    ("referrals.json",                "referrals",                ("id","referral_date","referral_source","referrer_name","referrer_code","referee_name","referee_phone","product_interested","mou_id","branch","rm_assigned","status","converted","conversion_date","account_opened","referral_fee_kes","fee_paid","notes")),
    ("consent_register.json",         "consent_register",         ("id","customer_cif","customer_name","consent_type","status","channel","granted","granted_date","withdrawn_date","expiry_date","purpose","legal_basis","data_processor","cbk_category","version","reviewed_by","notes")),
    ("collateral_register.json",      "collateral_register",      ("id","account_number","client_cif","collateral_type","description","market_value","forced_sale_value","loan_outstanding","ltv","last_valuation","next_valuation","insurance_expiry","valuer","status","rm","branch")),
    ("execute_initiatives.json",      "execute_initiatives",      ("id","name","objective","category","workstream","sub_workstream","io","io_backup","estimated_impact","created_by","gate","status")),
    ("projects.json",                 "projects",                 ("id","name","description","initiative_id","category","priority","status","project_manager","sponsor","department","start_date","planned_end_date","actual_end_date","budget_m","spent_m","pct_complete","pct_budget_used","rag_status","risks","open_issues","last_updated","notes","owner_username")),
    ("clearing_records.json",         "clearing_records",         ("id","value_date","settlement_date","system","transaction_ref","debit_account","credit_account","amount_kes","currency","status","failure_reason","settled_by","nostro_account","cbk_batch_ref","reconciled","reconciled_at","discrepancy_kes","notes","officer_username","settlement_tat_met","reconciled_by","exception_reason")),
    ("compliance_cases.json",         "compliance_cases",         ("id","source","source_ref","client_name","client_cif","flag_type","risk_level","status","raised_by","raised_date","assigned_officer","officer_code","review_notes","cleared_date","escalated_to","last_updated","proposition_tag","case_type","amount")),
    ("commission_records.json",       "commission_records",       ("staff_code","staff_name","role","unit","bsc_score","tier","base_salary","performance_commission","sales_commission","total_commission","disbursed_apps","period","status","approved_by","payment_date")),
    ("trade_finance.json",            "trade_finance",            ("id","lc_type","applicant","beneficiary","currency","amount","kes_equivalent","issuing_bank","confirming_bank","correspondent","issue_date","expiry_date","latest_shipment","status","documents_required","discrepancies","rm_code","branch","commission_earned","utilised_pct")),
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


# ════════════════════════════════════════════════════════════════════════
# v10.89 — special-case migrations (atypical JSON shapes that don't fit
# FLAT_MIGRATIONS or NESTED_MIGRATIONS patterns). Each handler reads its
# source file, transforms records in memory, then INSERTs.
# ════════════════════════════════════════════════════════════════════════

def migrate_bank_targets():
    """Special-case: bank_targets.json is keyed by composite "metric|year"
    pattern. Transform splits the key into separate metric + year columns
    so the table is queryable by either dimension."""
    src = DATA / "bank_targets.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping bank_targets")
        return 0
    with open(src) as f:
        raw = json.load(f)
    inserted = 0
    skipped  = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM bank_targets", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate bank_targets: {e}")
        for composite_key, value in raw.items():
            if "|" not in composite_key:
                skipped += 1
                continue
            try:
                metric, year_str = composite_key.rsplit("|", 1)
                year = int(year_str)
            except (ValueError, AttributeError):
                skipped += 1
                continue
            if not isinstance(value, dict):
                skipped += 1
                continue
            target = value.get("target")
            buffer_pct = value.get("buffer_pct")
            extras = {
                k: v for k, v in value.items()
                if k not in ("target", "buffer_pct")}
            try:
                db.execute(
                    'INSERT INTO bank_targets '
                    '(metric, year, target, buffer_pct, data) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (metric, year, target, buffer_pct,
                     json.dumps(extras, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                print(f"  ⚠️ Skipped row in bank_targets: "
                      f"{str(e)[:80]}")
                skipped += 1
    print(f"  ✅ bank_targets: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


def migrate_baselines():
    """Special-case: baseline_2025_Dec.json is an atypical DICT with
    period/date scalars + branch/rm sub-DICTs. Stored as a single row
    per (period, snapshot_date) with the sub-DICTs as JSONB so the
    snapshot is preserved without forcing per-branch flattening."""
    src = DATA / "baseline_2025_Dec.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping baselines")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        print(f"  ⚠️ {src.name} not a dict — skipping baselines")
        return 0
    period = raw.get("period")
    snapshot_date = raw.get("date")
    branch_data = raw.get("branch", {})
    rm_data = raw.get("rm", {})
    if not period or not snapshot_date:
        print(f"  ⚠️ {src.name} missing period/date — "
              f"skipping baselines")
        return 0
    inserted = 0
    with db.transaction() as conn:
        try:
            # Use upsert so re-running is idempotent
            db.execute(
                'INSERT INTO baselines '
                '(period, snapshot_date, branch_data, rm_data) '
                'VALUES (%s, %s, %s, %s) '
                'ON CONFLICT (period, snapshot_date) DO UPDATE SET '
                '  branch_data = EXCLUDED.branch_data, '
                '  rm_data = EXCLUDED.rm_data, '
                '  updated_at = now()',
                (period, snapshot_date,
                 json.dumps(branch_data, default=str),
                 json.dumps(rm_data, default=str)),
                conn=conn)
            inserted = 1
        except Exception as e:
            print(f"  ⚠️ baselines insert failed: "
                  f"{str(e)[:120]}")
    print(f"  ✅ baselines: {inserted} snapshot inserted "
          f"(period={period}, date={snapshot_date})")
    return inserted


# ─────────────────────────────────────────────────────────────────────
# v10.254 — PG migration sub-campaign batch 2: migrators for the 5
# tables added in v10.253's create_tables_v10.253.sql.
# Each handler reads the JSON, splits known fields into typed columns,
# preserves any extra keys in the JSONB `extra` column. All 5 use
# upsert-by-PK so re-running is idempotent.
# ─────────────────────────────────────────────────────────────────────

# Common helper — splits a row dict into (known_field_dict, extra_dict)
# given a tuple of known column names. Extra dict captures unmodelled
# fields for JSONB storage.
def _split_known_extra(row, known_cols):
    known = {c: row.get(c) for c in known_cols if c in row}
    extra = {k: v for k, v in row.items() if k not in known_cols}
    return known, extra


def migrate_credit_watchlist():
    """credit_monitoring.json → credit_watchlist table.

    Source structure: {"watchlist": [...], "last_updated": "...", "version": "..."}
    Iterates only the "watchlist" sub-list. Each item has id, account_number,
    cif, branch + RM info, plus risk indicators stored as JSONB.
    """
    src = DATA / "credit_monitoring.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping credit_watchlist")
        return 0
    with open(src) as f:
        raw = json.load(f)
    items = raw.get("watchlist", [])
    if not isinstance(items, list):
        print(f"  ⚠️ {src.name}.watchlist not a list — skipping")
        return 0
    KNOWN = ("id", "account_number", "cif", "branch_code", "branch_name",
              "region", "rm_code", "rm_name", "status", "severity",
              "added_date")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM credit_watchlist", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate credit_watchlist: {e}")
        for row in items:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO credit_watchlist '
                    '(id, account_number, cif, branch_code, branch_name, '
                    ' region, rm_code, rm_name, risk_data, status, '
                    ' severity, added_date) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("account_number"),
                     known.get("cif"), known.get("branch_code"),
                     known.get("branch_name"), known.get("region"),
                     known.get("rm_code"), known.get("rm_name"),
                     json.dumps(extra, default=str),
                     known.get("status"), known.get("severity"),
                     known.get("added_date")),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in credit_watchlist: "
                          f"{str(e)[:80]}")
    print(f"  ✅ credit_watchlist: {inserted} inserted, {skipped} skipped")
    return inserted


def migrate_target_cascade():
    """target_cascade.json → target_cascade table.

    Source structure: dict keyed by composite "from_code|kpi|period".
    Each value has from_code, from_name, kpi, period, total_target,
    allocated_sum, allocations (list). Composite key stored as
    cascade_key PK; allocations as JSONB.
    """
    src = DATA / "target_cascade.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping target_cascade")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        print(f"  ⚠️ {src.name} not a dict — skipping")
        return 0
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM target_cascade", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate target_cascade: {e}")
        for cascade_key, value in raw.items():
            if not isinstance(value, dict):
                skipped += 1
                continue
            try:
                db.execute(
                    'INSERT INTO target_cascade '
                    '(cascade_key, from_code, from_name, kpi, period, '
                    ' total_target, allocated_sum, allocations) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                    (cascade_key, value.get("from_code"),
                     value.get("from_name"), value.get("kpi"),
                     value.get("period"), value.get("total_target"),
                     value.get("allocated_sum"),
                     json.dumps(value.get("allocations", []),
                                  default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in target_cascade: "
                          f"{str(e)[:80]}")
    print(f"  ✅ target_cascade: {inserted} inserted, {skipped} skipped")
    return inserted


def migrate_training_completions():
    """training_completions.json → training_completions table.

    Source structure: top-level list of completion records. Each item
    has id, staff_code, staff_name, training_id, training_name,
    mandatory, hours, completed, status, completion_date.
    """
    src = DATA / "training_completions.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — "
              f"skipping training_completions")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("id", "staff_code", "staff_name", "training_id",
              "training_name", "mandatory", "hours", "completed",
              "status", "completion_date")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM training_completions", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate training_completions: {e}")
        for row in raw:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO training_completions '
                    '(id, staff_code, staff_name, training_id, '
                    ' training_name, mandatory, hours, completed, '
                    ' status, completion_date, extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("staff_code"),
                     known.get("staff_name"), known.get("training_id"),
                     known.get("training_name"),
                     bool(known.get("mandatory", False)),
                     known.get("hours"),
                     bool(known.get("completed", False)),
                     known.get("status"), known.get("completion_date"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in training_completions: "
                          f"{str(e)[:80]}")
    print(f"  ✅ training_completions: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


def migrate_ifrs9_loan_classifications():
    """ifrs9_loans.json → ifrs9_loan_classifications table.

    Source structure: top-level list of loan classification records.
    Each item has account_id, client_name, product, outstanding,
    stage, ecl_basis, npl_days, pd_12m, lgd, ead.
    """
    src = DATA / "ifrs9_loans.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — "
              f"skipping ifrs9_loan_classifications")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("account_id", "client_name", "product", "outstanding",
              "stage", "ecl_basis", "npl_days", "pd_12m", "lgd", "ead")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM ifrs9_loan_classifications", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate ifrs9_loan_classifications: {e}")
        for row in raw:
            if not isinstance(row, dict) or "account_id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO ifrs9_loan_classifications '
                    '(account_id, client_name, product, outstanding, '
                    ' stage, ecl_basis, npl_days, pd_12m, lgd, ead, '
                    ' extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("account_id"), known.get("client_name"),
                     known.get("product"), known.get("outstanding"),
                     known.get("stage"), known.get("ecl_basis"),
                     known.get("npl_days"), known.get("pd_12m"),
                     known.get("lgd"), known.get("ead"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in "
                          f"ifrs9_loan_classifications: "
                          f"{str(e)[:80]}")
    print(f"  ✅ ifrs9_loan_classifications: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


def migrate_customer_intelligence():
    """customer_intelligence.json → customer_intelligence table.

    Source structure: dict keyed by CIF. Each value has cif, segment,
    tags, propensity_scores, nba, churn_risk, clv_estimate,
    digital_engagement.
    """
    src = DATA / "customer_intelligence.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — "
              f"skipping customer_intelligence")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        print(f"  ⚠️ {src.name} not a dict — skipping")
        return 0
    KNOWN = ("cif", "segment", "tags", "propensity_scores", "nba",
              "churn_risk", "clv_estimate", "digital_engagement")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM customer_intelligence", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate customer_intelligence: {e}")
        for cif_key, value in raw.items():
            if not isinstance(value, dict):
                skipped += 1
                continue
            # Use cif from value if present, else the dict key
            cif = value.get("cif") or cif_key
            known, extra = _split_known_extra(value, KNOWN)
            try:
                db.execute(
                    'INSERT INTO customer_intelligence '
                    '(cif, segment, tags, propensity_scores, nba, '
                    ' churn_risk, clv_estimate, digital_engagement, '
                    ' extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (cif, known.get("segment"),
                     json.dumps(known.get("tags"), default=str),
                     json.dumps(known.get("propensity_scores"),
                                  default=str),
                     json.dumps(known.get("nba"), default=str),
                     known.get("churn_risk"),
                     known.get("clv_estimate"),
                     json.dumps(known.get("digital_engagement"),
                                  default=str),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in customer_intelligence: "
                          f"{str(e)[:80]}")
    print(f"  ✅ customer_intelligence: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


# ─────────────────────────────────────────────────────────────────────
# v10.256 — PG migration sub-campaign batch 4: migrators for the 5
# tables added in v10.255's create_tables_v10.255.sql.
# Same uniform pattern as v10.254's set.
# ─────────────────────────────────────────────────────────────────────

def migrate_performance_reviews():
    """performance_reviews.json → performance_reviews table.
    Top-level list of review records. 2,876 items.
    """
    src = DATA / "performance_reviews.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping performance_reviews")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("id", "reviewee_code", "reviewee_name", "reviewer_code",
              "reviewer_name", "period", "due_date", "submitted_date",
              "submitted_on_time", "status")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM performance_reviews", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate performance_reviews: {e}")
        for row in raw:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO performance_reviews '
                    '(id, reviewee_code, reviewee_name, reviewer_code, '
                    ' reviewer_name, period, due_date, submitted_date, '
                    ' submitted_on_time, status, extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("reviewee_code"),
                     known.get("reviewee_name"), known.get("reviewer_code"),
                     known.get("reviewer_name"), known.get("period"),
                     known.get("due_date"), known.get("submitted_date"),
                     known.get("submitted_on_time"), known.get("status"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in performance_reviews: "
                          f"{str(e)[:80]}")
    print(f"  ✅ performance_reviews: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


def migrate_staff_growth_plans():
    """growth_plans.json → staff_growth_plans table.
    Dict keyed by staff_code. Each value has meta, promotion_readiness,
    recommended_actions (list), skill_gaps (list).
    """
    src = DATA / "growth_plans.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping staff_growth_plans")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        print(f"  ⚠️ {src.name} not a dict — skipping")
        return 0
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM staff_growth_plans", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate staff_growth_plans: {e}")
        for staff_code, value in raw.items():
            if not isinstance(value, dict):
                skipped += 1
                continue
            try:
                db.execute(
                    'INSERT INTO staff_growth_plans '
                    '(staff_code, meta, promotion_readiness, '
                    ' recommended_actions, skill_gaps) '
                    'VALUES (%s,%s,%s,%s,%s)',
                    (staff_code,
                     json.dumps(value.get("meta", {}), default=str),
                     json.dumps(value.get("promotion_readiness", {}),
                                default=str),
                     json.dumps(value.get("recommended_actions", []),
                                default=str),
                     json.dumps(value.get("skill_gaps", []), default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in staff_growth_plans: "
                          f"{str(e)[:80]}")
    print(f"  ✅ staff_growth_plans: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


def migrate_edms_documents():
    """edms_documents.json → edms_documents table.
    Top-level list of document metadata records. 500 items.
    """
    src = DATA / "edms_documents.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping edms_documents")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("id", "category", "document_type", "title", "client_name",
              "client_cif", "linked_type", "linked_id", "file_name",
              "file_size_kb")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM edms_documents", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate edms_documents: {e}")
        for row in raw:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO edms_documents '
                    '(id, category, document_type, title, client_name, '
                    ' client_cif, linked_type, linked_id, file_name, '
                    ' file_size_kb, extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("category"),
                     known.get("document_type"), known.get("title"),
                     known.get("client_name"), known.get("client_cif"),
                     known.get("linked_type"), known.get("linked_id"),
                     known.get("file_name"), known.get("file_size_kb"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in edms_documents: "
                          f"{str(e)[:80]}")
    print(f"  ✅ edms_documents: {inserted} inserted, {skipped} skipped")
    return inserted


def migrate_customer_onboarding():
    """customer_onboarding.json → customer_onboarding table.
    Top-level list of onboarding journey records. 500 items.
    """
    src = DATA / "customer_onboarding.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping customer_onboarding")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("id", "customer_name", "phone", "channel", "product",
              "started_date", "completed_date", "current_stage",
              "stages_completed", "total_stages")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM customer_onboarding", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate customer_onboarding: {e}")
        for row in raw:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO customer_onboarding '
                    '(id, customer_name, phone, channel, product, '
                    ' started_date, completed_date, current_stage, '
                    ' stages_completed, total_stages, extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("customer_name"),
                     known.get("phone"), known.get("channel"),
                     known.get("product"), known.get("started_date"),
                     known.get("completed_date"),
                     known.get("current_stage"),
                     known.get("stages_completed"),
                     known.get("total_stages"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in customer_onboarding: "
                          f"{str(e)[:80]}")
    print(f"  ✅ customer_onboarding: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


def migrate_board_papers():
    """board_papers.json → board_papers table.
    Top-level list of board paper metadata records. ~60 items.
    """
    src = DATA / "board_papers.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping board_papers")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("id", "title", "type", "committee", "meeting_date",
              "submission_deadline", "submitted_date",
              "submitted_on_time", "submitted_by", "approved_by")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM board_papers", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate board_papers: {e}")
        for row in raw:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO board_papers '
                    '(id, title, type, committee, meeting_date, '
                    ' submission_deadline, submitted_date, '
                    ' submitted_on_time, submitted_by, approved_by, '
                    ' extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("title"),
                     known.get("type"), known.get("committee"),
                     known.get("meeting_date"),
                     known.get("submission_deadline"),
                     known.get("submitted_date"),
                     known.get("submitted_on_time"),
                     known.get("submitted_by"),
                     known.get("approved_by"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in board_papers: "
                          f"{str(e)[:80]}")
    print(f"  ✅ board_papers: {inserted} inserted, {skipped} skipped")
    return inserted


# ─────────────────────────────────────────────────────────────────────
# v10.258 — PG migration sub-campaign batch 6: migrators for the 5
# tables added in v10.257's create_tables_v10.257.sql.
# ─────────────────────────────────────────────────────────────────────

def migrate_legal_matters():
    """legal_matters.json → legal_matters table. List of 362 items."""
    src = DATA / "legal_matters.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping legal_matters")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("id", "matter_type", "status", "priority", "opened_date",
              "sla_due_date", "completed_date", "days_elapsed",
              "days_to_sla", "sla_days")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM legal_matters", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate legal_matters: {e}")
        for row in raw:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO legal_matters '
                    '(id, matter_type, status, priority, opened_date, '
                    ' sla_due_date, completed_date, days_elapsed, '
                    ' days_to_sla, sla_days, extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("matter_type"),
                     known.get("status"), known.get("priority"),
                     known.get("opened_date"), known.get("sla_due_date"),
                     known.get("completed_date"),
                     known.get("days_elapsed"),
                     known.get("days_to_sla"), known.get("sla_days"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in legal_matters: "
                          f"{str(e)[:80]}")
    print(f"  ✅ legal_matters: {inserted} inserted, {skipped} skipped")
    return inserted


def migrate_leave_requests():
    """leave_requests.json → leave_requests table. List of 1,416 items."""
    src = DATA / "leave_requests.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping leave_requests")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("id", "staff_code", "staff_name", "leave_type",
              "start_date", "end_date", "days", "status",
              "submitted_date", "approved_date")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM leave_requests", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate leave_requests: {e}")
        for row in raw:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO leave_requests '
                    '(id, staff_code, staff_name, leave_type, '
                    ' start_date, end_date, days, status, '
                    ' submitted_date, approved_date, extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("staff_code"),
                     known.get("staff_name"), known.get("leave_type"),
                     known.get("start_date"), known.get("end_date"),
                     known.get("days"), known.get("status"),
                     known.get("submitted_date"),
                     known.get("approved_date"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in leave_requests: "
                          f"{str(e)[:80]}")
    print(f"  ✅ leave_requests: {inserted} inserted, {skipped} skipped")
    return inserted


def migrate_lms_enrollments():
    """lms_enrollments.json → lms_enrollments table.
    No native `id` field — synthesize composite enrollment_key from
    staff_code + course_id."""
    src = DATA / "lms_enrollments.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping lms_enrollments")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("staff_code", "staff_name", "role", "dept", "course_id",
              "course_title", "cbk_mandatory", "status",
              "completion_date", "score")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM lms_enrollments", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate lms_enrollments: {e}")
        for row in raw:
            if (not isinstance(row, dict)
                    or "staff_code" not in row
                    or "course_id" not in row):
                skipped += 1
                continue
            enrollment_key = f"{row['staff_code']}|{row['course_id']}"
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO lms_enrollments '
                    '(enrollment_key, staff_code, staff_name, role, '
                    ' dept, course_id, course_title, cbk_mandatory, '
                    ' status, completion_date, score, extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (enrollment_key, known.get("staff_code"),
                     known.get("staff_name"), known.get("role"),
                     known.get("dept"), known.get("course_id"),
                     known.get("course_title"),
                     known.get("cbk_mandatory"), known.get("status"),
                     known.get("completion_date"), known.get("score"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in lms_enrollments: "
                          f"{str(e)[:80]}")
    print(f"  ✅ lms_enrollments: {inserted} inserted, {skipped} skipped")
    return inserted


def migrate_pipeline_deals_full():
    """pipeline.json → pipeline_deals_full table.
    Complements existing pipeline_deals (flat). Captures full deal
    structure with nested history."""
    src = DATA / "pipeline.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping pipeline_deals_full")
        return 0
    with open(src) as f:
        raw = json.load(f)
    # pipeline.json may be a list OR a dict — handle both
    if isinstance(raw, dict):
        # Try common keys
        items = raw.get("deals") or raw.get("pipeline") or list(raw.values())
        if not isinstance(items, list):
            items = []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    if not items:
        print(f"  ⚠️ {src.name} no deals found — skipping")
        return 0
    KNOWN = ("id", "client_name", "client_cif", "product", "amount",
              "currency", "stage", "swim_lane", "owner_code",
              "owner_name", "branch_code", "expected_close_date")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM pipeline_deals_full", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate pipeline_deals_full: {e}")
        for row in items:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO pipeline_deals_full '
                    '(id, client_name, client_cif, product, amount, '
                    ' currency, stage, swim_lane, owner_code, '
                    ' owner_name, branch_code, expected_close_date, '
                    ' extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("client_name"),
                     known.get("client_cif"), known.get("product"),
                     known.get("amount"), known.get("currency"),
                     known.get("stage"), known.get("swim_lane"),
                     known.get("owner_code"), known.get("owner_name"),
                     known.get("branch_code"),
                     known.get("expected_close_date"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in pipeline_deals_full: "
                          f"{str(e)[:80]}")
    print(f"  ✅ pipeline_deals_full: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


def migrate_rms_reconciliations():
    """rms_reconciliations.json → rms_reconciliations table."""
    src = DATA / "rms_reconciliations.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — "
              f"skipping rms_reconciliations")
        return 0
    with open(src) as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        items = raw.get("reconciliations") or list(raw.values())
        if not isinstance(items, list):
            items = []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    if not items:
        print(f"  ⚠️ {src.name} no items — skipping")
        return 0
    KNOWN = ("id", "recon_type", "period", "source_a", "source_b",
              "matched_count", "break_count", "total_count",
              "match_rate_pct", "status", "completed_date")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM rms_reconciliations", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate rms_reconciliations: {e}")
        for row in items:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, extra = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO rms_reconciliations '
                    '(id, recon_type, period, source_a, source_b, '
                    ' matched_count, break_count, total_count, '
                    ' match_rate_pct, status, completed_date, extra) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("recon_type"),
                     known.get("period"), known.get("source_a"),
                     known.get("source_b"), known.get("matched_count"),
                     known.get("break_count"), known.get("total_count"),
                     known.get("match_rate_pct"), known.get("status"),
                     known.get("completed_date"),
                     json.dumps(extra, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in rms_reconciliations: "
                          f"{str(e)[:80]}")
    print(f"  ✅ rms_reconciliations: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


# ─────────────────────────────────────────────────────────────────────
# v10.265 — CBK persistence layer
# ─────────────────────────────────────────────────────────────────────

def migrate_cbk_returns_generated():
    """cbk_returns_generated.json → cbk_returns_generated table.
    NEW data file — initially empty since v10.262-v10.264 didn't
    persist. v10.266 will start populating via save_cbk_package().
    Migrator handles missing file gracefully (treats as empty list).
    """
    src = DATA / "cbk_returns_generated.json"
    if not src.exists():
        # Acceptable — file may not exist yet; nothing to migrate
        print(f"  ℹ️  {src.name} not found (acceptable for new table)")
        return 0
    with open(src) as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError:
            print(f"  ⚠️ {src.name} is not valid JSON — skipping")
            return 0
    if not isinstance(raw, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    if not raw:
        print(f"  ℹ️  {src.name} is empty — nothing to migrate")
        return 0
    KNOWN = ("id", "return_code", "period", "generated_at",
              "generated_by", "breach_severity", "threshold",
              "threshold_direction", "breach_description",
              "computed_metrics", "inputs_used", "framework_refs")
    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM cbk_returns_generated", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate cbk_returns_generated: {e}")
        for row in raw:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            try:
                db.execute(
                    'INSERT INTO cbk_returns_generated '
                    '(id, return_code, period, generated_at, '
                    ' generated_by, breach_severity, threshold, '
                    ' threshold_direction, breach_description, '
                    ' computed_metrics, inputs_used, framework_refs) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (row.get("id"), row.get("return_code"),
                     row.get("period"), row.get("generated_at"),
                     row.get("generated_by"),
                     row.get("breach_severity"),
                     row.get("threshold"),
                     row.get("threshold_direction"),
                     row.get("breach_description"),
                     json.dumps(row.get("computed_metrics", {}),
                                default=str),
                     json.dumps(row.get("inputs_used", {}),
                                default=str),
                     json.dumps(row.get("framework_refs", []),
                                default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in "
                          f"cbk_returns_generated: {str(e)[:80]}")
    print(f"  ✅ cbk_returns_generated: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


# ─────────────────────────────────────────────────────────────────────
# v10.306 — PG migration push: 5 genuinely unmigrated registries
# ─────────────────────────────────────────────────────────────────────
# Scope honesty: inventory of FLAT_MIGRATIONS + explicit migrate_X()
# revealed many tables the conversation history suggested were
# unmigrated were actually already migrated. These 5 are the real
# unmigrated set.
#
# Pattern: each reads its JSON file, truncates the table, inserts.
# Known cockpit-relevant fields become columns; full row goes into
# JSONB `payload` for forward compatibility.

def migrate_audit_reviews():
    """audit_reviews.json → audit_reviews table (#201-#210)."""
    src = DATA / "audit_reviews.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping audit_reviews")
        return 0
    with open(src) as f:
        items = json.load(f)
    if not isinstance(items, list):
        print(f"  ⚠️ {src.name} not a list — skipping audit_reviews")
        return 0
    KNOWN = ("id", "audit_title", "audit_type", "category",
             "branch", "auditor_code", "auditor_name",
             "auditor_username")
    inserted, skipped = 0, 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM audit_reviews", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate audit_reviews: {e}")
        for row in items:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, _ = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO audit_reviews '
                    '(id, audit_title, audit_type, category, '
                    ' branch, auditor_code, auditor_name, '
                    ' auditor_username, payload) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("audit_title"),
                     known.get("audit_type"), known.get("category"),
                     known.get("branch"), known.get("auditor_code"),
                     known.get("auditor_name"),
                     known.get("auditor_username"),
                     json.dumps(row, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in audit_reviews: "
                          f"{str(e)[:80]}")
    print(f"  ✅ audit_reviews: {inserted} inserted, {skipped} skipped")
    return inserted


def migrate_compliance_regulatory_returns():
    """compliance.json → compliance_regulatory_returns table.

    Source file name is compliance.json for legacy reasons; the
    table name is explicit (compliance_regulatory_returns) to
    distinguish from the broader compliance_cases / compliance_*
    surface area.
    """
    src = DATA / "compliance.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — "
              f"skipping compliance_regulatory_returns")
        return 0
    with open(src) as f:
        items = json.load(f)
    if not isinstance(items, list):
        print(f"  ⚠️ {src.name} not a list — skipping")
        return 0
    KNOWN = ("id", "return_name", "frequency", "due_date",
             "filed_date", "filer", "status", "on_time")
    inserted, skipped = 0, 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM compliance_regulatory_returns",
                       conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate "
                  f"compliance_regulatory_returns: {e}")
        for row in items:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, _ = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO compliance_regulatory_returns '
                    '(id, return_name, frequency, due_date, '
                    ' filed_date, filer, status, on_time, '
                    ' payload) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("return_name"),
                     known.get("frequency"), known.get("due_date"),
                     known.get("filed_date"), known.get("filer"),
                     known.get("status"), known.get("on_time"),
                     json.dumps(row, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in "
                          f"compliance_regulatory_returns: "
                          f"{str(e)[:80]}")
    print(f"  ✅ compliance_regulatory_returns: {inserted} "
          f"inserted, {skipped} skipped")
    return inserted


def migrate_incidents():
    """incidents.json → incidents table (IT/Ops)."""
    src = DATA / "incidents.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping incidents")
        return 0
    with open(src) as f:
        items = json.load(f)
    if not isinstance(items, list):
        print(f"  ⚠️ {src.name} not a list — skipping incidents")
        return 0
    KNOWN = ("id", "title", "system", "priority", "status",
             "raised_by", "assigned_to", "raised_date")
    inserted, skipped = 0, 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM incidents", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate incidents: {e}")
        for row in items:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, _ = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO incidents '
                    '(id, title, system, priority, status, '
                    ' raised_by, assigned_to, raised_date, '
                    ' payload) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("title"),
                     known.get("system"), known.get("priority"),
                     known.get("status"), known.get("raised_by"),
                     known.get("assigned_to"),
                     known.get("raised_date"),
                     json.dumps(row, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in incidents: "
                          f"{str(e)[:80]}")
    print(f"  ✅ incidents: {inserted} inserted, {skipped} skipped")
    return inserted


def migrate_nps_responses():
    """nps.json → nps_responses table (customer NPS)."""
    src = DATA / "nps.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping nps_responses")
        return 0
    with open(src) as f:
        items = json.load(f)
    if not isinstance(items, list):
        print(f"  ⚠️ {src.name} not a list — skipping nps_responses")
        return 0
    KNOWN = ("id", "response_date", "customer_cif", "score",
             "band", "category", "channel", "branch")
    inserted, skipped = 0, 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM nps_responses", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate nps_responses: {e}")
        for row in items:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, _ = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO nps_responses '
                    '(id, response_date, customer_cif, score, '
                    ' band, category, channel, branch, payload) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("response_date"),
                     known.get("customer_cif"), known.get("score"),
                     known.get("band"), known.get("category"),
                     known.get("channel"), known.get("branch"),
                     json.dumps(row, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in nps_responses: "
                          f"{str(e)[:80]}")
    print(f"  ✅ nps_responses: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


def migrate_rcsa_register():
    """rcsa_register.json → rcsa_register table (Risk RCSA)."""
    src = DATA / "rcsa_register.json"
    if not src.exists():
        print(f"  ⚠️ {src.name} not found — skipping rcsa_register")
        return 0
    with open(src) as f:
        items = json.load(f)
    if not isinstance(items, list):
        print(f"  ⚠️ {src.name} not a list — skipping rcsa_register")
        return 0
    KNOWN = ("id", "category", "description", "department",
             "inherent_likelihood", "inherent_impact",
             "inherent_score", "control_description")
    inserted, skipped = 0, 0
    with db.transaction() as conn:
        try:
            db.execute("DELETE FROM rcsa_register", conn=conn)
        except Exception as e:
            print(f"  ⚠️ Could not truncate rcsa_register: {e}")
        for row in items:
            if not isinstance(row, dict) or "id" not in row:
                skipped += 1
                continue
            known, _ = _split_known_extra(row, KNOWN)
            try:
                db.execute(
                    'INSERT INTO rcsa_register '
                    '(id, category, description, department, '
                    ' inherent_likelihood, inherent_impact, '
                    ' inherent_score, control_description, '
                    ' payload) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (known.get("id"), known.get("category"),
                     known.get("description"),
                     known.get("department"),
                     known.get("inherent_likelihood"),
                     known.get("inherent_impact"),
                     known.get("inherent_score"),
                     known.get("control_description"),
                     json.dumps(row, default=str)),
                    conn=conn)
                inserted += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    print(f"  ⚠️ Skipped row in rcsa_register: "
                          f"{str(e)[:80]}")
    print(f"  ✅ rcsa_register: {inserted} inserted, "
          f"{skipped} skipped")
    return inserted


# Map filename → custom handler. Used in main() after FLAT/NESTED loops.
SPECIAL_MIGRATIONS = {
    "bank_targets.json":             migrate_bank_targets,
    "baseline_2025_Dec.json":        migrate_baselines,
    # v10.254 — sub-campaign batch 2 — migrators for 5 high-value tables
    "credit_monitoring.json":        migrate_credit_watchlist,
    "target_cascade.json":           migrate_target_cascade,
    "training_completions.json":     migrate_training_completions,
    "ifrs9_loans.json":              migrate_ifrs9_loan_classifications,
    "customer_intelligence.json":    migrate_customer_intelligence,
    # v10.256 — sub-campaign batch 4 — migrators for next 5 tables
    "performance_reviews.json":      migrate_performance_reviews,
    "growth_plans.json":             migrate_staff_growth_plans,
    "edms_documents.json":           migrate_edms_documents,
    "customer_onboarding.json":      migrate_customer_onboarding,
    "board_papers.json":             migrate_board_papers,
    # v10.258 — sub-campaign batch 6 — migrators for next 5 tables
    "legal_matters.json":            migrate_legal_matters,
    "leave_requests.json":           migrate_leave_requests,
    "lms_enrollments.json":          migrate_lms_enrollments,
    "pipeline.json":                 migrate_pipeline_deals_full,
    "rms_reconciliations.json":      migrate_rms_reconciliations,
    # v10.265 — CBK persistence layer
    "cbk_returns_generated.json":    migrate_cbk_returns_generated,
    # v10.306 — PG migration push: 5 genuinely unmigrated registries
    "audit_reviews.json":            migrate_audit_reviews,
    "compliance.json":               migrate_compliance_regulatory_returns,
    "incidents.json":                migrate_incidents,
    "nps.json":                      migrate_nps_responses,
    "rcsa_register.json":            migrate_rcsa_register,
}


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

    # 4b. Special-case migrations (atypical JSON shapes — bank_targets,
    # baselines). Each handler reads its source file and transforms.
    banner("STEP 3b — Migrating special-case JSON files")
    for fname, handler in SPECIAL_MIGRATIONS.items():
        try:
            n = handler()
            total_inserted += n
        except Exception as e:
            print(f"  ❌ {fname:<35} FAILED: {str(e)[:80]}")

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
