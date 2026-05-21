"""utils/staff_field_resolver.py — v10.108 Integration Layer.

Operational tables identify the responsible staff member by different
column names. Loan applications use `assigned_officer`. Pipeline
opportunities use `rm_code`. Legal matters use `attorney`. AML
screenings use `reviewer_username`. The autofit aggregator needs a
single source of truth that resolves table_name → staff_field, so
that kpi_aggregation_rules.compute_rule can group rows by the right
column without each rule re-stating it.

If a rule explicitly sets `staff_field`, that overrides this map
(needed when a single table has multiple staff identifiers — e.g.
a credit_committee table tracks both proposer and approver).

Tables NOT in this map default to "staff_code", which is the most
common convention. Adding a table with a non-standard staff field
without registering it here will silently group every row under a
"None" staff bucket, which the autofit pipeline then drops. Audit
gate G143 surfaces this in a future drop.
"""
from __future__ import annotations


# table_name -> staff identifier column. Keep alphabetised by table.
#
# v10.109 update: the v10.108 entries for loan_applications,
# debt_recovery, referrals, and legal_matters used field names from
# the rule designer's mental model rather than the real schemas.
# Now corrected to match the actual CBS-mock data the platform tests
# against (loan_applications.rm_code, debt_recovery.recovery_officer_
# code, referrals.referrer_code, legal_matters.legal_officer is a
# nested dict — handled via per-rule staff_field_extractor).
STAFF_FIELD_BY_TABLE: dict[str, str] = {
    # Pipeline / sales
    "pipeline": "staff_code",          # real schema: staff_code, not rm_code
    "opportunities": "rm_code",
    "leads": "rm_code",
    "referrals": "referrer_code",      # the referrer fires the actual

    # Lending operations
    "loan_applications": "rm_code",    # corrected from assigned_officer
    "credit_decisions": "decided_by",
    "loan_disbursements": "disbursed_by",
    "credit_committee": "decided_by",

    # Recovery / collections
    "debt_recovery": "recovery_officer_code",   # corrected from recovery_officer
    "collections": "collector_username",
    "ifrs9_loans": "owner_code",

    # Legal / compliance — legal_matters uses nested legal_officer.code
    # Rules wiring legal_matters MUST set staff_field_extractor.
    "legal_matters": "_NESTED_legal_officer.code",
    "aml_screenings": "reviewer_username",
    "kyc_reviews": "reviewer_username",
    "consent_capture": "captured_by",

    # Operations / branch
    "agent_fraud_alerts": "agent_id",
    "branch_complaints": "owner_username",
    "complaints": "owner_username",
    "service_requests": "owner_username",
    "incidents": "raised_by",          # username field; assigned_to is full name
    "valuation_records": "valuer_username",

    # Campaigns / marketing
    "campaigns": "owner_code",         # v10.109 — wired

    # HR / training
    "training_completions": "staff_code",
    "performance_reviews": "reviewee_code",
    "leave_requests": "staff_code",

    # Default — most A2Z operational tables already use "staff_code"
    "operational_logs": "staff_code",
    "audit_reviews": "auditor_code",
    "nps": "rm_code",
    "hr": "staff_code",

    # v10.114 — newly wired in this drop:
    "board_papers":        "submitted_by",         # username field
    "cbk_returns":         "reviewer",             # username field; submitted_by is mostly empty
    "dpo_register":        "dpo_reviewer",         # username field
    "merchant_acquiring":  "rm_code",
    "projects":            "_NESTED_project_manager_via_name",  # sentinel; rules MUST set staff_field_extractor=name_lookup

    # v10.115 — newly wired:
    "customer_onboarding": "rm_assigned",          # username (rm{NNN})
    "sanctions_register":  "reviewer",             # username (comp{NNN})
    "ews_cases":           "_NESTED_rm_via_name",  # sentinel; rules MUST set extractor=name_lookup on `rm`
    "op_risk_losses":      "reported_by",          # username (staff{NNN})
    "retailer_finance":    "rm_code",

    # v10.116 — newly wired:
    "card_management":     "rm_code",              # username-style (rm{NNN})
    "purchase_requests":   "requested_by",         # username (geoffrey220, etc.)

    # v10.117 — newly wired:
    "trade_finance":         "rm_code",            # numeric code (300{NNN})
    "bid_bonds":             "rm_code",            # numeric code (300{NNN})
    "strategic_initiatives": "owner_username",     # username (head{NNN})

    # v10.122 — newly seeded + wired:
    "sla_tickets":           "assignee",           # numeric staff_code (300{NNN})
    "branch_log":            "submitted_by",       # numeric staff_code (300{NNN})

    # v10.123 — newly seeded + wired:
    "hr":                    "manager_code",       # most hr rules aggregate by manager
    "agency_banking":        "supervisor_code",    # supervisors own their agents
    "bsc_scores":            "staff_code",         # the person being scored

    # v10.124 — newly seeded + wired:
    "clearing":              "processed_by",       # numeric staff_code
    "nps":                   "handled_rm",         # numeric staff_code
    "compliance":            "filer",              # numeric staff_code
    "cims":                  "assigned_to",        # numeric staff_code

    # v10.125 — newly seeded + wired (STRICT-READY (high) crossing):
    "partnerships":          "rm_code",            # numeric staff_code
    "vendors":               "owner_code",         # numeric staff_code
    "agent_fraud":           "investigator",       # numeric staff_code
    "collateral":            "credit_officer",     # numeric staff_code
    "360_feedback":          "ratee_code",         # numeric staff_code (the person being rated)
}


DEFAULT_STAFF_FIELD = "staff_code"


# v10.110: per-bank field overrides loaded from
# data/integration_layer_config.json. Cached once per process; admins
# clear the cache after saving via the Module Config Centre.
_overrides_cache: dict[str, str] | None = None


def _get_field_overrides() -> dict[str, str]:
    """Lazy-load the per-bank field overrides. Empty dict if none."""
    global _overrides_cache
    if _overrides_cache is None:
        try:
            from utils.aggregation_rules_loader import (
                load_field_overrides)
            _overrides_cache = load_field_overrides()
        except Exception:
            _overrides_cache = {}
    return _overrides_cache


def refresh_overrides_cache() -> None:
    """Clear the cache so the next resolve_staff_field call reloads
    from disk. Called by the admin save handler."""
    global _overrides_cache
    _overrides_cache = None


def resolve_staff_field(table: str, override: str | None = None) -> str:
    """Return the staff field for `table`, consulting in priority order:
       1. `override` argument (rule-level — wins over everything)
       2. Per-bank override from integration_layer_config.json
       3. STAFF_FIELD_BY_TABLE built-in default
       4. DEFAULT_STAFF_FIELD ("staff_code") fallback

    The per-bank override layer (step 2) is the v10.110 deployability
    feature: a bank whose CBS table has `officer_id` instead of A2Z's
    expected `rm_code` adds an entry to integration_layer_config.json
    via the Module Config Centre admin page; no code edit required.
    """
    if override:
        return override
    bank_overrides = _get_field_overrides()
    if table in bank_overrides:
        return bank_overrides[table]
    return STAFF_FIELD_BY_TABLE.get(table, DEFAULT_STAFF_FIELD)


def registered_tables() -> set[str]:
    """The set of operational tables with explicit staff field entries
    (built-in map; does not include per-bank overrides)."""
    return set(STAFF_FIELD_BY_TABLE.keys())
