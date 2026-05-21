# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_admin_integration_layer.py — v10.110.

Integration Layer admin Module Config registration. Renders inside
the Module Config Centre (pages/_admin_module_config.py) under the
"Integration" category, so admins deploying A2Z MIS at a new bank
can adjust per-bank schema mappings, rule activation, and status
vocabularies without editing Python code.

Per the convention documented in `docs/ADMIN_CONVENTIONS.md` and
the v10.108 prompt directive ("Never add module-specific config tabs
to `7_admin.py`; use the registry pattern"), this module uses
`utils.admin_registry.register_module_config(...)` to declare its
spec; the Module Config Centre handles rendering, persistence, and
audit.

CONFIG STORAGE
──────────────
Per-bank overrides live in `data/integration_layer_config.json`.
This file is part of the deployment artefact — when A2Z is installed
at a new bank, the admin user customises it through the Centre and
the saved config persists across runs.

The hard-coded vs configurable boundary is documented on the
"Configurable Boundary" tab so deploying admins know what they can
and can't touch.
"""
from utils.admin_registry import register_module_config


CONFIG_PATH = "integration_layer_config.json"


# Bullet content for the configurable boundary documentation tab.
# Kept as a Python list so the renderer's `bullet_list` field type
# can render it directly.
_CONFIGURABLE_LIST = [
    "**Active rules.** Per-rule on/off toggle in `data/aggregation_rules.json` (each rule's `active` field). The list of active KPI IDs is also forcibly suppressible via the `active_rule_overrides` list in this file.",
    "**Source-table → staff-field mapping.** Per-bank `field_overrides` map (set on the Field Mapping tab). Wins over the built-in `STAFF_FIELD_BY_TABLE` defaults but loses to a rule-level `staff_field` override.",
    "**Predicate value lists.** Status enums (e.g., which values count as 'approved' or 'decided') configurable via the Status Vocabulary tab. Predicates in `aggregation_rules.json` can reference these lists by name in v10.111+ (currently the JSON has the lists inline — admin edits propagate via the JSON file directly).",
    "**Period field selection.** `period_field` per rule in `aggregation_rules.json`. Tells the engine which date column to filter rows by.",
    "**Decimals for rounding.** `decimals` per rule.",
    "**Invert flag for BOOL_FRACTION/PERCENTAGE.** Per rule. Use when the rule's bool/numerator captures the opposite of what the KPI semantically rewards (e.g., a 'Compliance Score' KPI direction:higher wired to a `flagged` boolean where True=problem).",
]

_HARD_CODED_LIST = [
    "**The 6 archetypal patterns.** COUNT, SUM, PERCENTAGE, TAT_DAYS, RATIO, BOOL_FRACTION. Universal across banks; fixed in `utils/kpi_aggregation_rules.py`.",
    "**`compute_rule` engine.** The pattern-dispatch logic that applies a rule to a row list and returns `{staff: value}`. Universal.",
    "**Ownership union rule.** A staff owns a KPI iff `role_kpis[role] ∪ (cascade-locked AND in cascade allocations)`. Universal across banks.",
    "**Audit gate G143.** Reports operational-source KPI aggregator coverage. Universal.",
    "**KPI library schema.** The `kpi_library.json` shape (id, name, pillar, weight, direction, source) is fixed. Adding KPIs is allowed; changing the schema is not.",
    "**BSC submission contract.** `{staff_code, kpi_id, value, period}` records submitted via `bsc_engine.submit_batch`. Universal.",
]

_DSL_REFERENCE = [
    "Predicates in `aggregation_rules.json` use a small JSON DSL. Available types:",
    "**field_eq** — `{type, field, value}` — field equals value",
    "**field_in** — `{type, field, values: [...]}` — field is in list",
    "**field_in_named** — `{type, field, list_name}` — field is in the named status_vocabulary list (v10.111)",
    "**field_not_in** — `{type, field, values: [...]}` — field is NOT in list",
    "**field_truthy** — `{type, field}` — `bool(field)` is true",
    "**field_is_true** — `{type, field}` — field is exactly `True`",
    "**field_is_numeric** — `{type, field}` — field is int or float",
    "**field_le_field** — `{type, field, compare_field}` — field ≤ other field, both numeric",
    "**all** — `{type, of: [pred1, pred2, ...]}` — every sub-predicate true (AND)",
    "**any** — `{type, of: [pred1, pred2, ...]}` — any sub-predicate true (OR)",
    "Staff field extractors:",
    "**nested** — `{type: nested, path: 'parent.child'}` — dotted-path traversal, handles None at any level",
    "**name_lookup** — `{type: name_lookup, name_field: 'assigned_to'}` — resolves full name to staff_code via the name resolver (v10.111)",
    "**role_lookup** — `{type: role_lookup, role_field: 'assigned_to'}` — resolves role title to staff_code via the role resolver's 3-layer chain (v10.113)",
]


register_module_config({
    "module_id":   "integration_layer",
    "title":       "Integration Layer (Phase 1D)",
    "icon":        "🧩",
    "category":    "integration",
    "config_path": CONFIG_PATH,
    "config_key":  "integration_layer_config",
    "page_link":   None,  # No standalone page; lives in admin only

    "tabs": [
        # ─── Tab 1: Field Mapping (per-bank schema adaptation) ───
        {
            "name": "Field Mapping",
            "fields": [
                {"type": "rich_caption",
                 "value": "Map operational tables to your bank's actual staff-identifier column. A2Z defaults assume the Eco Bank FLEXCUBE-mock schemas; another bank's CBS may use different field names. Leave empty entries blank — A2Z will fall back to the built-in `STAFF_FIELD_BY_TABLE` defaults (rm_code for loan_applications, recovery_officer_code for debt_recovery, etc.). Only override what's different at YOUR bank."},
                {"type": "dict_editor",
                 "key": "field_overrides",
                 "label": "Per-table staff-field overrides (table → column)",
                 "cols": 2,
                 "cast": str,
                 "step": None},
            ],
            "save_label":   "💾 Save field mapping",
            "audit_action": "INTEGRATION_LAYER_FIELD_OVERRIDES_UPDATED",
            "post_save_hook": "utils.staff_field_resolver:refresh_overrides_cache",
        },

        # ─── Tab 2: Rule Activation ───
        {
            "name": "Rule Activation",
            "fields": [
                {"type": "rich_caption",
                 "value": "Force-disable specific rules at THIS bank's deployment. Each entry is a kpi_id (e.g., 'K014'). Disabled rules are skipped at registry-load time — no actuals submitted for the listed KPIs. Use when a rule's source table doesn't exist in your bank's deployment, or when the rule's logic doesn't apply (e.g., a bank that doesn't run referral programs would disable K044, K116, K117)."},
                {"type": "text_area_list",
                 "key": "active_rule_overrides",
                 "label": "Disabled rule kpi_ids (one per line)",
                 "height": 180},
            ],
            "save_label":   "💾 Save rule activation",
            "audit_action": "INTEGRATION_LAYER_RULE_ACTIVATION_UPDATED",
        },

        # ─── Tab 3: Status Vocabulary ───
        {
            "name": "Status Vocabulary",
            "fields": [
                {"type": "rich_caption",
                 "value": "Status value enums used by predicates in `data/aggregation_rules.json`. Editing here is the most common per-bank customisation: your bank's loan workflow may use `pending_approval` instead of `analysis`, or `awaiting_disbursement` instead of `approved`. Edits saved here become the source of truth for which rows count as 'decided', 'closed', etc. v10.111 will wire these named lists directly into the predicate DSL; for now, edits propagate by an admin re-saving `aggregation_rules.json`."},
                {"type": "text_area_list",
                 "key": "loan_decided",
                 "label": "Loan statuses that count as 'decided' (one per line)",
                 "height": 100},
                {"type": "text_area_list",
                 "key": "loan_approved_disbursed",
                 "label": "Loan statuses that count as 'approved or disbursed' (one per line)",
                 "height": 80},
                {"type": "text_area_list",
                 "key": "pipeline_closed",
                 "label": "Pipeline stages that count as 'closed' (one per line)",
                 "height": 80},
                {"type": "text_area_list",
                 "key": "campaign_active",
                 "label": "Campaign statuses that count as 'active or completed' (one per line)",
                 "height": 80},
            ],
            "save_label":   "💾 Save vocabulary",
            "audit_action": "INTEGRATION_LAYER_VOCABULARY_UPDATED",
        },

        # ─── Tab 4: Configurable Boundary (read-only documentation) ───
        {
            "name": "Configurable Boundary",
            "fields": [
                {"type": "rich_caption",
                 "value": "**What admins CAN configure (per-bank deployment knobs):**"},
                {"type": "bullet_list",
                 "value": _CONFIGURABLE_LIST},
                {"type": "rich_caption",
                 "value": "**What is hard-coded (universal across banks; not configurable):**"},
                {"type": "bullet_list",
                 "value": _HARD_CODED_LIST},
                {"type": "rich_caption",
                 "value": "**Predicate DSL reference (for editing aggregation_rules.json directly):**"},
                {"type": "bullet_list",
                 "value": _DSL_REFERENCE},
            ],
            # No save_label — this tab is documentation only
        },

        # ─── Tab 5: Agent Alerts Config (v10.113) ───
        # Per-bank role aliases + admin-pinned staff for tables that
        # record assignees by role title (agent_fraud_alerts).
        {
            "name": "Agent Alerts Config",
            "fields": [
                {"type": "rich_caption",
                 "value": "**Role-based assignment resolution.** Some operational tables (notably `agent_fraud_alerts`) record the assignee as a role title rather than a person's name. The resolver looks up role titles in the staff register via three layers (admin-pinned → alias-normalized → direct match). Use this tab to configure the bank-specific resolution behaviour."},
                {"type": "rich_caption",
                 "value": "**Role aliases.** Map the role-title labels in operational tables to the staff register's labels. Eco Bank example: agent_fraud_alerts has assigned_to='Agency Banking Manager' but users.json has role='Manager Agency Banking' — the alias `Agency Banking Manager → Manager Agency Banking` bridges the gap. Format: one mapping per row, source label → target label."},
                {"type": "dict_editor",
                 "key": "agent_alerts_config.role_aliases",
                 "label": "Role aliases (table label → register label)",
                 "cols": 2,
                 "cast": str,
                 "step": None},
                {"type": "rich_caption",
                 "value": "**Pinned staff codes.** Optionally pin a role title to a specific staff_code regardless of role population. Useful when the bank wants a specific person to permanently own these alerts. Wins over the alias layer."},
                {"type": "dict_editor",
                 "key": "agent_alerts_config.role_to_staff_code",
                 "label": "Pinned role → staff_code",
                 "cols": 2,
                 "cast": str,
                 "step": None},
            ],
            "save_label":   "💾 Save agent alerts config",
            "audit_action": "INTEGRATION_LAYER_AGENT_ALERTS_UPDATED",
            "post_save_hook": "utils.staff_role_resolver:refresh_cache",
        },

        # ─── Tab 6: Resolution Metrics (v10.113, read-only) ───
        # Surfaces name + role resolver hit/miss rates so deploying
        # admins can debug staff-register coverage gaps.
        {
            "name": "Resolution Metrics",
            "fields": [
                {"type": "rich_caption",
                 "value": "**Name + role resolution health.** When operational tables record assignees by name (aml_alerts, incidents) or role (agent_fraud_alerts), the resolvers convert those values to staff codes for BSC submission. This tab shows hit/miss rates so you can see which assignees aren't resolving — typically because the staff register doesn't have an active user with that name/role, or there's a typo, or the role uses a different label."},
                {"type": "computed_callout",
                 "key": "name_resolver_metrics",
                 "compute": "utils.staff_name_resolver:get_resolution_metrics",
                 "label": "Name resolver (aml_alerts.assigned_to, incidents.assigned_to)"},
                {"type": "computed_callout",
                 "key": "role_resolver_metrics",
                 "compute": "utils.staff_role_resolver:get_resolution_metrics",
                 "label": "Role resolver (agent_fraud_alerts.assigned_to)"},
                {"type": "rich_caption",
                 "value": "**To improve resolution:** Add missing staff to users.json with the correct full_name and active=true, or update the operational table's assignee value to match the register's full_name exactly. For role gaps, add an alias under Agent Alerts Config or pin a specific staff_code."},
            ],
            # No save_label — read-only
        },
    ],

    "hardcoded_caption": (
        "Hard-coded engine: 6 patterns + ownership rule + G143 audit gate. "
        "See Configurable Boundary tab for the full split."
    ),
})
