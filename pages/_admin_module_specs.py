# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_admin_module_specs.py — Centralised module config specs.

Each module that needs admin configuration registers its spec here.
The Module Config Centre uses these specs to render the admin UI.

To add a new module config: append a register_module_config({...}) call below.
Field types and categories are documented in utils/admin_registry.py.
"""
from utils.admin_registry import register_module_config

CONFIG_PATH = "proposition_config.json"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Reconciliation Management System (RMS) Config
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
register_module_config({
    "module_id":   "rms",
    "title":       "Reconciliation Management System",
    "icon":        "🔄",
    "category":    "operations",
    "config_path": CONFIG_PATH,
    "config_key":  "rms_config",
    "page_link":   "30_rms.py",
    "tabs": [
        {
            "name": "Recon Types",
            "fields": [
                {"type":"text_area_list", "key":"recon_types",
                 "label":"Reconciliation types (one per line)", "height":180},
                {"type":"text_area_list", "key":"breaker_types",
                 "label":"Breaker types (one per line)", "height":120},
            ],
            "save_label":   "💾 Save types",
            "audit_action": "RMS_TYPES_UPDATED",
        },
        {
            "name": "SLA & Thresholds",
            "fields": [
                {"type":"dict_editor", "key":"sla_days",
                 "label":"SLA days by status (days before escalation)",
                 "cast": int, "step":1, "cols":2},
                {"type":"number_input", "key":"auto_match_threshold_kes",
                 "label":"Auto-match threshold (KES)", "cast":int, "step":1000, "min":0},
                {"type":"number_input", "key":"escalation_days",
                 "label":"Escalation after (days)", "cast":int, "step":1, "min":1, "max":30},
            ],
            "save_label":   "💾 Save SLA",
            "audit_action": "RMS_SLA_UPDATED",
        },
        {
            "name": "Accounts",
            "fields": [
                {"type":"readonly_table", "key":"accounts",
                 "label":"GL accounts tracked",
                 "empty_msg":"No accounts configured. Edit proposition_config.json or contact admin."},
            ],
            "save_label": None,
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** matching algorithm, escalation routing, audit trail, "
        "GL feed format. To change methodology, contact engineering."
    ),
})

register_module_config({
    "module_id":   "edms",
    "title":       "Electronic Document Management System",
    "icon":        "📁",
    "category":    "data",
    "config_path": CONFIG_PATH,
    "config_key":  "edms_config",
    "page_link":   "31_edms.py",
    "tabs": [
        {
            "name": "Categories",
            "fields": [
                {"type":"text_area_list", "key":"categories",
                 "label":"Document categories (one per line)", "height":200},
                {"type":"multiselect", "key":"expiry_alert_days",
                 "label":"Expiry alert thresholds (days before expiry)",
                 "options":[7,14,30,60,90,180], "default":[30,60,90]},
            ],
            "save_label":   "💾 Save categories",
            "audit_action": "EDMS_CATEGORIES_UPDATED",
        },
        {
            "name": "Retention Periods",
            "fields": [
                {"type":"dict_editor", "key":"retention_periods_years",
                 "label":"Retention periods by category (years)",
                 "cast": int, "step":1, "cols":2},
            ],
            "save_label":   "💾 Save retention",
            "audit_action": "EDMS_RETENTION_UPDATED",
        },
        {
            "name": "Access Levels",
            "fields": [
                {"type":"readonly_table", "key":"access_levels",
                 "label":"Access level definitions",
                 "empty_msg":"No access levels configured."},
            ],
            "save_label": None,
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** audit trail, versioning, encryption, file storage structure."
    ),
})

register_module_config({
    "module_id":   "treasury",
    "title":       "Treasury Configuration",
    "icon":        "💹",
    "category":    "treasury",
    "config_path": CONFIG_PATH,
    "config_key":  "treasury_config",
    "page_link":   "25_treasury.py",
    "tabs": [
        {
            "name": "FX & Rates",
            "fields": [
                {"type":"dict_editor", "key":"fx_reference_rates",
                 "label":"Reference FX rates (against KES)",
                 "cast": float, "step":0.01, "format":"%.4f", "cols":3},
                {"type":"number_input", "key":"cbk_rate",
                 "label":"CBK Rate (%)", "cast":float, "step":0.25, "format":"%.2f"},
                {"type":"rich_caption",
                 "text":"In production these are updated from a market data feed (Bloomberg/Reuters)."},
            ],
            "save_label":   "💾 Save rates",
            "audit_action": "TREASURY_RATES_UPDATED",
        },
        {
            "name": "IFRS 9",
            "fields": [
                {"type":"dict_editor", "key":"ifrs9_ecl_rates",
                 "label":"IFRS 9 ECL rates by stage",
                 "cast":float, "step":0.001, "format":"%.4f", "cols":3},
                {"type":"multiselect", "key":"ifrs9_classifications",
                 "label":"IFRS 9 classifications allowed",
                 "options":["HTM","AFS","FVTPL","FVOCI"],
                 "default":["HTM","AFS","FVTPL"]},
            ],
            "save_label":   "💾 Save IFRS 9",
            "audit_action": "TREASURY_IFRS9_UPDATED",
        },
        {
            "name": "Liquidity",
            "fields": [
                {"type":"dict_editor", "key":"liquidity_ratios_minimum",
                 "label":"Minimum liquidity ratios (CBK Prudential Guidelines, %)",
                 "cast":float, "step":1.0, "format":"%.1f", "cols":2},
            ],
            "save_label":   "💾 Save ratios",
            "audit_action": "TREASURY_LIQUIDITY_UPDATED",
        },
        {
            "name": "Products",
            "fields": [
                {"type":"multiselect", "key":"fx_currencies",
                 "label":"FX currencies traded",
                 "options":["USD","EUR","GBP","CHF","JPY","ZAR","UGX","TZS","AED","CNY"],
                 "default":["USD","EUR","GBP"]},
            ],
            "save_label":   "💾 Save products",
            "audit_action": "TREASURY_PRODUCTS_UPDATED",
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** ECL calculation engine, SPPI test logic, OCI recycling, "
        "Basel III LCR/NSFR methodology, HQLA classification, CBK reporting forms."
    ),
})

register_module_config({
    "module_id":   "statement_analyzer",
    "title":       "Statement Analyzer",
    "icon":        "🧾",
    "category":    "credit",
    "config_path": CONFIG_PATH,
    "config_key":  "statement_analyzer_config",
    "page_link":   "33_statement_analyzer.py",
    "tabs": [
        {
            "name": "Thresholds",
            "fields": [
                {"type":"number_input", "key":"dsr_limit",
                 "label":"DSR Limit (%)", "cast":int, "step":1, "min":1, "max":100},
                {"type":"number_input", "key":"min_months",
                 "label":"Min statement months", "cast":int, "step":1, "min":1, "max":24},
                {"type":"number_input", "key":"living_expense_pct",
                 "label":"Living expense (% income)", "cast":int, "step":5, "min":0, "max":80},
                {"type":"number_input", "key":"interest_rate_monthly",
                 "label":"Interest rate (%/month)", "cast":float, "step":0.1, "format":"%.2f"},
                {"type":"rich_caption",
                 "text":"**Hardcoded:** CBK DSR methodology, affordability formula."},
            ],
            "save_label":   "💾 Save thresholds",
            "audit_action": "SA_THRESHOLDS_UPDATED",
        },
        {
            "name": "Risk Keywords",
            "fields": [
                {"type":"text_area_list", "key":"risk_keywords",
                 "label":"Risk keywords (one per line — gambling, digital lenders, etc.)",
                 "height":250},
                {"type":"rich_caption",
                 "text":"Case-insensitive matching against transaction descriptions."},
            ],
            "save_label":   "💾 Save keywords",
            "audit_action": "SA_KEYWORDS_UPDATED",
        },
        {
            "name": "Auto-decisions",
            "fields": [
                {"type":"bullet_list", "key":"auto_approve_triggers",
                 "label":"Auto-approve triggers (ALL must be met)"},
                {"type":"bullet_list", "key":"auto_decline_triggers",
                 "label":"Auto-decline triggers (ANY triggers decline)"},
            ],
            "save_label": None,
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** Claude API model (claude-sonnet-4), JSON output schema, "
        "CBK 40% DSR rule, affordability formula, audit trail of analyses."
    ),
})

register_module_config({
    "module_id":   "pipeline",
    "title":       "Pipeline & CRM Settings",
    "icon":        "💼",
    "category":    "credit",
    "config_path": CONFIG_PATH,
    "config_key":  "pipeline_config",
    "page_link":   "3_pipeline.py",
    "tabs": [
        {
            "name": "Stages",
            "fields": [
                {"type":"text_area_list", "key":"stages",
                 "label":"Pipeline stages (one per line, in order)", "height":200},
                {"type":"text_area_list", "key":"products",
                 "label":"Products available", "height":150},
            ],
            "save_label":   "💾 Save stages",
            "audit_action": "PIPELINE_STAGES_UPDATED",
        },
        {
            "name": "Probabilities",
            "fields": [
                {"type":"dict_editor", "key":"stage_probabilities",
                 "label":"Win probability by stage (%)",
                 "cast":int, "step":5, "cols":2},
            ],
            "save_label":   "💾 Save probabilities",
            "audit_action": "PIPELINE_PROBS_UPDATED",
        },
        {
            "name": "Thresholds",
            "fields": [
                {"type":"number_input", "key":"min_deal_kes",
                 "label":"Minimum deal size (KES)", "cast":int, "step":10000},
                {"type":"number_input", "key":"max_deal_kes",
                 "label":"Maximum deal size (KES)", "cast":int, "step":1000000},
                {"type":"number_input", "key":"stale_days",
                 "label":"Days before deal flagged as stale", "cast":int, "step":7, "min":7, "max":180},
            ],
            "save_label":   "💾 Save thresholds",
            "audit_action": "PIPELINE_THRESHOLDS_UPDATED",
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** stage progression rules, BSC integration, audit trail."
    ),
})

register_module_config({
    "module_id":   "lms",
    "title":       "Loan Management System",
    "icon":        "⚖️",
    "category":    "credit",
    "config_path": CONFIG_PATH,
    "config_key":  "lms_config",
    "page_link":   "21_loan_applications.py",
    "tabs": [
        {
            "name": "Loan Types",
            "fields": [
                {"type":"text_area_list", "key":"loan_types",
                 "label":"Loan types offered (one per line)", "height":150},
                {"type":"text_area_list", "key":"approval_levels",
                 "label":"Approval levels (one per line, in escalation order)", "height":120},
            ],
            "save_label":   "💾 Save types",
            "audit_action": "LMS_TYPES_UPDATED",
        },
        {
            "name": "Limits",
            "fields": [
                {"type":"dict_editor", "key":"approval_limits_kes",
                 "label":"Approval limits by level (KES)",
                 "cast":int, "step":100000, "cols":2},
            ],
            "save_label":   "💾 Save limits",
            "audit_action": "LMS_LIMITS_UPDATED",
        },
        {
            "name": "Rates",
            "fields": [
                {"type":"dict_editor", "key":"interest_rates_pct",
                 "label":"Interest rates by product (% p.a.)",
                 "cast":float, "step":0.5, "format":"%.2f", "cols":2},
            ],
            "save_label":   "💾 Save rates",
            "audit_action": "LMS_RATES_UPDATED",
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** CBK product classification, IFRS 9 staging, NPL recognition rules."
    ),
})

register_module_config({
    "module_id":   "propositions",
    "title":       "Propositions Configuration",
    "icon":        "🎯",
    "category":    "strategy",
    "config_path": CONFIG_PATH,
    "config_key":  "propositions_config",
    "page_link":   "27_propositions.py",
    "tabs": [
        {
            "name": "Segments",
            "fields": [
                {"type":"text_area_list", "key":"segments",
                 "label":"Customer segments (one per line)", "height":200},
                {"type":"text_area_list", "key":"micro_segments",
                 "label":"Micro-segments (one per line)", "height":200},
            ],
            "save_label":   "💾 Save segments",
            "audit_action": "PROPOSITIONS_SEGMENTS_UPDATED",
        },
        {
            "name": "Lifecycle",
            "fields": [
                {"type":"text_area_list", "key":"lifecycle_stages",
                 "label":"Customer lifecycle stages (one per line)", "height":150},
            ],
            "save_label":   "💾 Save lifecycle",
            "audit_action": "PROPOSITIONS_LIFECYCLE_UPDATED",
        },
        {
            "name": "Channels",
            "fields": [
                {"type":"multiselect", "key":"channels",
                 "label":"Channels available",
                 "options":["Branch","Mobile","Internet","USSD","ATM","Agent","Call Centre","WhatsApp"],
                 "default":["Branch","Mobile","Internet"]},
            ],
            "save_label":   "💾 Save channels",
            "audit_action": "PROPOSITIONS_CHANNELS_UPDATED",
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** segment-product matrix, eligibility rules, BSC linkage."
    ),
})

register_module_config({
    "module_id":   "ra",
    "title":       "Risk Analytics Configuration",
    "icon":        "📊",
    "category":    "risk",
    "config_path": CONFIG_PATH,
    "config_key":  "ra_config",
    "page_link":   "28_ra.py",
    "tabs": [
        {
            "name": "Risk Categories",
            "fields": [
                {"type":"text_area_list", "key":"risk_categories",
                 "label":"Risk categories tracked (one per line)", "height":150},
                {"type":"text_area_list", "key":"severity_levels",
                 "label":"Severity levels (one per line, in order)", "height":100},
            ],
            "save_label":   "💾 Save categories",
            "audit_action": "RA_CATEGORIES_UPDATED",
        },
        {
            "name": "Thresholds",
            "fields": [
                {"type":"dict_editor", "key":"alert_thresholds",
                 "label":"Alert thresholds by category",
                 "cast":int, "step":1, "cols":2},
            ],
            "save_label":   "💾 Save thresholds",
            "audit_action": "RA_THRESHOLDS_UPDATED",
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** risk scoring algorithm, escalation routing, regulator notifications."
    ),
})

register_module_config({
    "module_id":   "leave",
    "title":       "Leave Settings",
    "icon":        "🏖️",
    "category":    "people",
    "config_path": CONFIG_PATH,
    "config_key":  "leave_config",
    "page_link":   "2_people.py",
    "tabs": [
        {
            "name": "Leave Types",
            "fields": [
                {"type":"text_area_list", "key":"leave_types",
                 "label":"Leave types (one per line)", "height":150},
            ],
            "save_label":   "💾 Save types",
            "audit_action": "LEAVE_TYPES_UPDATED",
        },
        {
            "name": "Allocations",
            "fields": [
                {"type":"dict_editor", "key":"annual_days",
                 "label":"Annual days by leave type",
                 "cast":int, "step":1, "cols":2},
                {"type":"number_input", "key":"max_carryover",
                 "label":"Maximum carry-over days", "cast":int, "step":1, "min":0, "max":40},
            ],
            "save_label":   "💾 Save allocations",
            "audit_action": "LEAVE_ALLOC_UPDATED",
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** Kenyan Employment Act minimums (21 days annual), accrual rules."
    ),
})

register_module_config({
    "module_id":   "revenue_assurance",
    "title":       "Revenue Assurance",
    "icon":        "💰",
    "category":    "operations",
    "config_path": CONFIG_PATH,
    "config_key":  "revenue_assurance_config",
    "page_link":   "29_revenue_assurance.py",
    "tabs": [
        {
            "name": "Leakage Categories",
            "fields": [
                {"type":"text_area_list", "key":"leakage_categories",
                 "label":"Leakage categories tracked (one per line)", "height":180},
            ],
            "save_label":   "💾 Save categories",
            "audit_action": "RA_LEAKAGE_UPDATED",
        },
        {
            "name": "Thresholds",
            "fields": [
                {"type":"number_input", "key":"min_alert_kes",
                 "label":"Minimum alert threshold (KES)", "cast":int, "step":1000, "min":0},
                {"type":"number_input", "key":"recovery_target_pct",
                 "label":"Recovery target (% of detected leakage)", "cast":int, "step":5, "min":0, "max":100},
            ],
            "save_label":   "💾 Save thresholds",
            "audit_action": "REVENUE_ASSURANCE_THRESHOLDS_UPDATED",
        },
    ],
    "hardcoded_caption": (
        "**Hardcoded:** detection rules, GL feed format, recovery workflow."
    ),
})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Integration Layer (v10.110)
# Per-bank deployment configuration: field overrides, rule activation,
# status vocabulary, hard-coded vs configurable boundary documentation.
# Spec lives in pages/_admin_integration_layer.py — importing it
# triggers the register_module_config call.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    from pages import _admin_integration_layer  # noqa: F401
except Exception as _e:  # pragma: no cover — defensive
    import logging
    logging.getLogger("a2z.admin").warning(
        f"Integration Layer admin spec failed to load: "
        f"{type(_e).__name__}: {_e}")
