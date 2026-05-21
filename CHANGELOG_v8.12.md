# A2Z MIS 360 — CHANGELOG v8.12

**v8.12 Living Doc Phase 1 — registry loader + claim validator + 6 sales-content JSONs**
**Released:** May 2026
**Audit gates:** **109/109** = 100% PASS — **38th consecutive clean**
**Strategic milestone:** **🎯 LIVING DOC SUB-CAMPAIGN — PHASE 1 DONE.** The discipline foundation is in place: every claim future generators want to make in rendered collateral must trace through `_claim_validator.py` against the registry. Sales claims become as audit-locked as engineering invariants.

---

## What this batch is

**Pure scaffolding batch.** Phase 1 of the Living Documentation sub-campaign per Part 7 of `docs/A2Z_LIVING_DOCS_PLAN.md` (v8.11).

**Three things shipped:**
1. `scripts/docgen/_registry_loader.py` (~310 lines) — assembles unified content dict from tiers 1-5
2. `scripts/docgen/_claim_validator.py` (~180 lines) — audit-locked claim verification with `Claim` dataclass + `ClaimValidationError`
3. 6 sales-content JSON files in `docs/sales_content/` — the only NEW content the Living Doc system needs

The campaign-defining idea now has a working foundation: every numeric or factual claim in rendered collateral must trace to a registry path. If a claim diverges, generation aborts. The collateral is never written.

---

## What changed

### `scripts/docgen/__init__.py`

Package entry exporting `load_registry`, `Claim`, `validate_claim`, `validate_claims`, `ClaimValidationError`. Documents the v8.12 → v8.15 sub-campaign sequence in module docstring.

### `scripts/docgen/_registry_loader.py` (~310 lines)

The only module that knows about tier 1-5 file structures. `load_registry()` returns a unified dict:

```python
{
    "platform": {
        "version": "v8.12",
        "audit_gates": 109,
        "audit_pass_rate": "100.0%",
        "engines_count": 120,
        "changelog_count": 81,
        "build_timestamp_iso": "...",
        "audit_command": "python scripts/audit.py",
    },
    "stocks": [...6 entries...],
    "stocks_count": 6,
    "stocks_wired": 6,
    "stocks_wired_pct": 100.0,
    "loops": [...15 entries...],
    "loops_count": 15,
    "loops_wired": 15,
    "loops_wired_pct": 100.0,
    "learning_loops_count": 3,
    "invariants": [...],
    "kpi_library": {...},
    "cbs": {customers, accounts, transactions, branches, staff},
    "docs": {charter, v7_retrospective, v8_retrospective, living_docs_plan},
    "sales_content": {...6 JSONs...},
    "sales_content_files_present": 6,
    "regulatory_alignment": [5 entries],
    "canonical_references": [Meadows, Evans, Nygard, Newman, CBK],
}
```

**Discipline:** if a registry is missing a field, `RegistryLoadError` is raised. We will not render stale or guessed numbers.

### `scripts/docgen/_claim_validator.py` (~180 lines)

```python
@dataclass
class Claim:
    text: str            # "15 of 15 feedback loops wired"
    registry_path: str   # "loops_wired"
    expected_value: Any  # 15
    source_file: str     # "utils/system_flows.py"
    tolerance: Optional[float] = None

def validate_claim(claim, registry) -> bool:
    """Raises ClaimValidationError on divergence."""

def validate_claims(claims, registry, fail_fast=False) -> dict:
    """Batch validation. Returns total/passed/failed/failures summary."""
```

`_resolve_path()` walks dot-separated paths through nested dicts/lists with clear error messages.

### 6 sales-content JSON files in `docs/sales_content/`

| File | Purpose | Honest scope examples |
|---|---|---|
| `gap_analysis.json` | 6 market gaps with shipped/designed/roadmap status + `verification_audit_gates` | "Real-time mobile alerts on KPI drift are roadmap (v9.x), not shipped" |
| `security_architecture.json` | CISO summary distinguishing implemented vs designed vs roadmap | "A2Z does not currently hold SOC 2 or ISO 27001 certifications" |
| `integrations_roadmap.json` | FLEXCUBE 12 marked shipped; T24/Salesforce/Workday/SAP marked roadmap | "Most external system integrations are roadmap" |
| `case_studies.json` | Ecobank Kenya design-partner with `may_appear_in_collateral: false`; Zanifu/C2FO labeled `_label: 'EXTERNAL CITATION — NOT AN A2Z CUSTOMER'` | "A2Z does not currently have any signed production-reference deployments with measurable outcomes" |
| `pricing_models.json` | Explicit ROI methodology disclaimer | "A2Z has no measured ROI outcomes from production deployments. Any number framed as 'achievable ROI' is a projection, not a measurement" |
| `competitive_positioning.json` | What A2Z is genuinely distinctive about + what it does NOT replace + what it is NOT better at | "Where the original draft said 'no other banking MIS offers...' — those claims are removed because verifying them would require a market survey A2Z has not conducted" |

Every file has `_doc`, `_schema_version`, `_last_reviewed_iso` headers + structured `honest_scope` blocks at the top level or per-entry.

### FOUNDATIONAL allowlist extended

Added to `scripts/audit.py`:
```python
"scripts/docgen/__init__.py",
"scripts/docgen/_registry_loader.py",
"scripts/docgen/_claim_validator.py",
```

Architecturally identical to `scripts/generate_cbs_aggregates.py` (v8.10) — pipeline-driver scripts that read JSON files. G2 doesn't currently scan subdirectories under `scripts/`, but explicit allowlist matches the v8.10 precedent.

---

## End-to-end smoke test (4 scenarios all green)

```
=== Scenario 1: registry loader self-test ===
  Platform version: v8.11 → v8.12 after master prompt bump
  Audit gates: 109
  Stocks: 6 (6/6 WIRED)
  Loops: 15 (15/15 WIRED, 3 learning)
  Sales content present: 6/6
  ✓ Loader assembles unified dict from tiers 1-5

=== Scenario 2: validator self-test ===
  6 canonical Part 6 claims all validate ✓
  Deliberately-wrong claim raises ClaimValidationError ✓
  Missing-path claim raises ClaimValidationError ✓

=== Scenario 3: end-to-end batch validation ===
  4 truthful claims → all pass
  1 deliberately-divergent claim → fails with clear error
  ✓ Validator catches divergence; passes truthful claims

=== Scenario 4: full audit ===
  Score: 109/109 gates = 100.0% — PASS
  G2 direct_io: 0 violations
```

---

## ✅ Thirty-eighth consecutive clean-first-try

38 batches in a row landing clean — v5.96 → v8.12.

---

## Comparison vs v8.11

| | v8.11 | v8.12 |
|---|---|---|
| Audit gates | 109/109 | **109/109** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Feedback loops WIRED | 15 (100%) | 15 (100%, unchanged) |
| Standards in UI | 62 | 62 (unchanged) |
| **Living Doc engine** | **planning only** | **registry loader + validator** ⭐ |
| **Sales-content JSONs** | **0** | **6** ⭐ |
| FOUNDATIONAL allowlist | 21 entries | 24 entries ⭐ (+3 docgen) |
| Clean-first-try streak | 37 | **38** |

---

## Strategic narrative — Phase 1 done; Phase 2 opens

Per Part 7 of `docs/A2Z_LIVING_DOCS_PLAN.md`:

| Batch | Phase | Status |
|---|---|---|
| v8.11 | Plan | ✓ shipped |
| **v8.12** | **Phase 1: registry loader + validator + 6 JSONs** | ✓ **shipped** |
| v8.13 | Phase 2: three generators (PPT + Magazine + Whitepaper) | next |
| v8.14 | Phase 3: admin/systems-view UI surface | after |
| v8.15 (optional) | Phase 4: G110 audit gate | optional |

**The discipline foundation is now in place.** Every claim a future generator wants to make must trace through `_claim_validator.py` against the registry. If a claim diverges, generation aborts. Sales claims become as audit-locked as engineering invariants.

The 6 sales-content JSONs follow the campaign's honest acknowledgement convention end-to-end:
- Every gap has a `solution_status` (shipped/designed/roadmap)
- Every security feature has explicit status markers
- The ROI section explicitly states "no measured outcomes exist yet"
- Case studies clearly distinguish A2Z deployments (none yet) from cited industry research (Zanifu/C2FO)
- Competitive positioning lists what A2Z is NOT better at

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — pure script + JSON batch; tested via Python CLI invocation.
2. **The 6 sales-content JSONs require periodic review** — `_last_reviewed_iso` is dated v8.12; future batches must update when underlying facts change.
3. **The validator is strict equality by default** — numeric claims with floating-point tolerance must explicitly set the `tolerance` parameter.
4. **Engine count reported as 120 not 116** — the loader counts `utils/*.py` files; the 116 figure is registered standards (different metric); future v8.x could expose `engine_registry_count` separately.
5. **CHANGELOG count reported as 81 not 32** — `glob('CHANGELOG_v*.md')` picks up legacy v5.x and v6.x files; both metrics valid.
6. **KPI count reported as 111 not 35** — local A2Z Blueprint kpi_library.json has KPIs beyond the canonical 35; honest about file content.
7. **Sales content JSONs deliberately conservative** — every claim hedged toward roadmap/designed; future batches that ship features can promote status without rewriting prose.
8. **The validator only catches numeric/string equality divergence** — does NOT catch logical inconsistencies; future enhancement: structural claim validation.
9. **G110 audit gate not built** — proposed for v8.15; v8.12 is foundation only.
10. **`_load_audit_summary()` re-executes audit module via importlib** — for performance, v8.13 generators could cache; current behavior fine for occasional generation.
11. **No integration test of validator against full magazine claim list** — arrives in v8.13 when generators' Claim lists are built.
12. **The discipline pattern is now portable** — future sub-campaigns wanting audit-locked claims for new domains can adopt the same Claim/validate pattern.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v8.13 Build three generators (PPT + Magazine + Whitepaper)** | Phase 2 per Part 7; produces rendered artifacts |
| (2) | v8.14 Surface docgen on admin/systems-view | Phase 3; UI surface |
| (3) | v8.15 (optional) Add G110 audit gate | Final hardening; 109 → 110 gates |

**Strong recommendation: v8.13 = Build three generators** — the canonical Phase 2 per Part 7 of the plan; ~1250 lines including ppt_generator (400) + magazine_generator (600) + whitepaper_generator (250) + shared rendering core (`_theme.py` + `_honest_section.py`); produces actual rendered artifacts via WeasyPrint + python-pptx; 39th-clean candidate.

---

🎯 **Living Doc Phase 1 done — registry loader + claim validator + 6 sales-content JSONs in place.**

⭐ **38th consecutive clean-first-try. Sales claims now as audit-lockable as engineering invariants.**
