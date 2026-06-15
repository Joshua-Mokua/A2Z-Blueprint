# CHANGELOG v10.562 — Batch B1: data-driven all-view from the staff register

## Principle applied
Admin/source data is the source of truth for scope. The staff register
(data/staff_register.xlsx, the authoritative reporting source) has exactly one
ROOT role — "Chief Executive & Managing Director" (blank Reports To) — which
must see everyone. Previously the CEO's all-view came from a hardcoded H4
addition to _ALL_VIEW_ROLES; now it's derived from data.

## Change (utils/core_audit.py)
- _register_root_roles() (cached): reads the register and returns roles with a
  blank "Reports To" (org roots), lowercased. Empty on any error.
- get_visible_staff: the all-view check now also passes for register-root
  roles (union with is_admin / "admin" in role / _ALL_VIEW_ROLES). Additive —
  the hardcoded set remains a fallback; nothing is removed.

Because get_visible_staff_codes (pipeline scope) extracts Staff Codes from
get_visible_staff's result, this fixes BOTH the BSC scope and the pipeline
deal-visibility scope from one place.

## Safety
Only genuine roots become all-view. The register has exactly ONE root (the
CEO), so no mid-level role can be over-scoped; Regional Head / Branch Manager /
Teller all fall through to the existing REPORTING_TREE logic unchanged.

## Verified
- py_compile; register yields {chief executive & managing director}; CEO ->
  all-view via data; mid-level roles -> not all-view (REPORTING_TREE fallback).

## Scope / next
This is the all-view increment of the config-driven scope. The full mid-level
rebuild (replace REPORTING_TREE's role+unit filtering with the register's
Reports-To chain + Region/Unit) is the larger next step, to be done carefully
with regression tests. The hardcoded REPORTING_TREE / _ALL_VIEW_ROLES remain
as fallbacks until then (safe to delete only AFTER the full rebuild is proven).
