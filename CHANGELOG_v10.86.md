# CHANGELOG v10.86 — ml_governance arc CLOSED (15th closed arc)

**Status:** Closure batch. ml_governance arc 5/5 engines active + 3 closure ratchet gates + closure cockpit + Tier 29 promotion + cross-platform wiring catalog. Fifteenth closed arc on the platform.

**Audit:** **141/141 PASS** (was 138/138 — ratcheted +3 with G139/G140/G141)
**G117:** STABLE
**G128:** STABLE
**Active standards:** 153/260 (unchanged)
**Scenario library:** 186 (unchanged — closure batch ships gates, not engines)
**Engine self-tests:** 151/151 (unchanged)
**ml_governance arc scenarios:** 20/20 PASS, 80/80 assertions

---

## What this closure batch ships

Per the established 5-thing closure pattern (locked at v10.46):

1. **G-gate ratchet pair G139 + G140** — closure audit gates
2. **G141** — cross-platform wiring catalog gate (the audit-side "apply everywhere")
3. **MLOPS_INTEGRATION_REGISTRY** — new constant in standards_registry.py
4. **Closure cockpit** `pages/98_ml_governance_arc_cockpit.py`
5. **Tier 29 promotion** + Master Prompt update + CHANGELOG

## G139 ml_governance_arc_closed

Audit gate that locks the v10.81-v10.85 work. Verifies:

- All 5 mlops_* engine modules exist on disk
- Required public symbols on each module — **introspected via `dir()` before writing the gate** per the trade_finance closure lesson (never assume names from memory). Symbols verified per module:
  - `mlops_model_registry`: 14 required (engine + dataclasses + enums)
  - `mlops_adjudication_log`: 13 required
  - `mlops_retraining_scheduler`: 14 required
  - `mlops_ab_harness`: 14 required
  - `mlops_model_card_composer`: 13 required
- ENH-281..ENH-285 all `status='active'`, `subcategory='ml_governance'`
- ≥20 ml_governance arc scenarios in library across 5 prefixes (MRG/ADJ/RTR/ABT/MCD — 4 each per closure floor)
- **Per Rule 7** — engines remain diagnostic-only. Gate scans each engine class for forbidden auto-execute method markers (`auto_promote`, `auto_deprecate`, `auto_retrain`, `auto_trigger`, `execute_retraining`, `deploy_to_production`) and fails if any appear.

## G140 ml_governance_arc_ui_integrated

Codifies the v10.46 protocol amendment for the closure cockpit. Verifies:

- `pages/98_ml_governance_arc_cockpit.py` exists
- Cockpit imports all 5 mlops_* engine modules
- Cockpit constructs each engine class
- Cockpit declares `require_access(...)` for access control
- Cockpit emits `audit_log(...)` events on every interaction

## G141 ml_governance_cross_platform_wiring

The audit-side answer to **"how do I apply this everywhere?"** — same enforcement pattern as G108/G109/G110 from older closed work. Verifies:

- `MLOPS_INTEGRATION_REGISTRY` exists in `standards_registry.py` and is non-empty
- Each entry's `engine_module` exists in `utils/`
- Each entry's `standard_id` exists in `STANDARDS_REGISTRY`
- At least one entry uses the v10.76 ML hook contract (otherwise the catalog has no point)
- Notes field non-empty for every entry per Rule 1

**Per Rule 7, this is a CATALOG, not coupling.** The mlops_* engines never read this registry. The catalog exists so operations can audit "every ML-using engine has registry + adjudication wiring planned in its caller path." Wiring lives in CALLER code paths (cockpit pages, training pipelines, operations workflows), never in the engines.

Current catalog: 4 ML-using engines documented:
| engine_module | standard | v10.76 hook | registry | adjudication | scheduler |
|---|---|---|---|---|---|
| trade_finance_reporting | ENH-280 | ✓ | ✓ | ✓ | ✓ |
| trade_finance_document_checking | ENH-270 | ✓ | ✓ | ✓ | — |
| cross_sell_bandit | ENH-126 | — (pre-v10.76) | ✓ | ✓ | ✓ |
| model_governance | ENH-259 | — (validation arc itself) | — | — | — |

Two engines use the v10.76 contract (ENH-280 + ENH-270 — both shipped during the trade_finance arc). cross_sell_bandit predates v10.76 and is queued for retrofit. utils.model_governance is the validation arc itself — no retrofit needed; ml_governance arc engines consume its outputs via caller integration.

## Closure cockpit pages/98_ml_governance_arc_cockpit.py

Single pane of glass for ML governance. Six tabs:

1. **Registry (ENH-281)** — promotion readiness check demo with three gate types (MINIMUM_METRIC + NON_REGRESSION + METADATA_REQUIRED)
2. **Adjudication (ENH-282)** — override rate computation over 24-hour window with sample records
3. **Retraining (ENH-283)** — combined recommendation across freshness + override + drift signals
4. **A/B Harness (ENH-284)** — 100-paired-prediction comparison with composite severity
5. **Model Cards (ENH-285)** — sample card composition + markdown preview + completeness validation
6. **Cross-Platform Wiring (G141)** — interactive view of MLOPS_INTEGRATION_REGISTRY

Every interaction emits `audit_log(...)` with the operation + outcome. Full provenance preserved. Operator drives every decision; cockpit surfaces, never decides.

## Tier 29 promotion

Label flipped from `"Tier 29 — ml_governance Arc (v10.81+, in flight, closes vTBD)"` to `"Tier 29 — ml_governance Arc (v10.81-v10.85, closed at v10.86)"`. All 5 engine entries remain in place with their full descriptions.

## What closure means

The ml_governance arc is now the **15th closed arc** on the platform. Closed arcs (in order):

| # | Arc | Closure gates | Closed at |
|---|---|---|---|
| 1 | Climate / ESG | G120 | v10.6+ |
| 2 | Credit | G121 | v10.x |
| 3 | KESONIA | various | v10.x |
| 4 | RMS | G122 | v10.x |
| 5 | Audit-GRC | G123 | v10.x |
| 6 | Model Governance | G124 | v10.28 |
| 7 | Virtual Bank | G125 | v10.x |
| 8 | Bandit (Cat A first ML) | G126 | v10.x |
| 9 | Treasury | G127 | v10.x |
| 10 | Risk | G129+G130 | v10.46 |
| 11 | credit_model_risk | G131+G132 | v10.49 |
| 12 | revenue_assurance | G133+G134 | v10.58 |
| 13 | finance | G135+G136 | v10.69 |
| 14 | trade_finance | G137+G138 | v10.80 |
| 15 | **ml_governance** | **G139+G140+G141** | **v10.86** |

Each closed arc is locked: subsequent platform changes that break arc invariants fail the closure gate.

## Files changed in this batch

- **MOD** `utils/standards_registry.py` (added MLOpsIntegrationRecord + MLOPS_INTEGRATION_REGISTRY constant with 4 entries)
- **MOD** `scripts/audit.py` (added `gate_ml_governance_arc_closed`, `gate_ml_governance_arc_ui_integrated`, `gate_ml_governance_cross_platform_wiring` + registered in GATES list)
- **NEW** `pages/98_ml_governance_arc_cockpit.py` (closure cockpit, ~440 lines)
- **MOD** `pages/7_admin.py` (Tier 29 label promoted to "closed at v10.86")
- **NEW** `CHANGELOG_v10.86.md` (this file)

## Master Prompt v10.86 update

The closing line of the arc roadmap moves to "ml_governance closed at v10.86 (G139+G140+G141)". Tier 29 is locked. The next arc that opens — when business prioritizes — will be assigned a new tier number and ENH-### range starting at ENH-286+ (numbers 286-290 reserved for any ml_governance follow-on if scope extends).

## Where the closed arc takes the platform

After v10.86, the platform's ML governance story is structurally complete:

1. **Engine authors adopt the v10.76 ML hook contract** when their engine wants ML refinement — that's the discipline pattern
2. **Operations registers every model artifact via ENH-281** before deployment — that's the lifecycle entry point
3. **Cockpit pages capture every operator decision via ENH-282** during inference — that's the production feedback loop
4. **Retraining cycle consults ENH-283** quarterly (or per caller policy) — that's the freshness gate
5. **Promotion review uses ENH-284 + ENH-281** — A/B harness surfaces deltas; ENH-281 promotion gates are the actual decision point
6. **Each model has a ModelCard composed via ENH-285** — that's the documentation surface for regulatory examination
7. **Drift detection at G124 (model_governance arc, closed earlier) feeds ENH-283** — that's the cross-arc integration

What's NOT closed and remains operations work:
- **Retrofit cross_sell_bandit** to use ENH-281+282 wiring (tracked in MLOPS_INTEGRATION_REGISTRY)
- **Build the actual JSON/PG persistence layer** for the registry, adjudication log, and card archive (engines are stateless; caller stores)
- **Wire the existing ENH-280 forecast hook + ENH-270 discrepancy classification hook** through ENH-281+282 in their cockpit pages (the wiring framework is in place; the actual integration code lands as a v10.87+ enhancement when operations prioritizes)

These are runbook items, not engine work. The ml_governance arc gives operations the tools; operations applies them.

## Honest acknowledgements

**G141 verifies catalog consistency, not actual wiring.** The gate confirms the MLOPS_INTEGRATION_REGISTRY catalog is internally consistent (engine modules exist, standards exist, notes are populated). It does NOT verify that the wiring claimed in each entry's `*_wiring_planned` flags actually exists in the caller code paths. That would require static analysis of cockpit pages + training pipelines + operations workflows — significantly more invasive. The current gate is "documentation-grade auditable" — operations can show a regulator the catalog and reconcile against runbooks. Future enhancement (G142?) could add static checks that verify, e.g., "trade_finance_reporting cockpit page imports mlops_model_registry."

**MLOPS_INTEGRATION_REGISTRY is hand-maintained.** Adding a new ML-using engine requires manually adding a row. Operationally, this is fine — the cadence of new ML adopters is slow. Auditably, the catalog could go stale if maintainers forget to add a row when shipping a new ML-using engine. A future enhancement could automate detection (e.g., scan utils/* for v10.76 hook markers and warn when an engine uses the contract but isn't catalogued).

**Closure cockpit is demo-grade, not production-grade.** Each tab demonstrates a capability with sample data; the actual operational use case (e.g., "show me the override rate for cross_sell_bandit over the last 30 days") requires integration with the actual adjudication storage. The cockpit is the structural deliverable per closure protocol; the operational extension is post-closure work that callers can do in their own time.

**G139 introspection-based verification doesn't catch semantic drift.** The gate verifies symbol names exist, but doesn't verify their semantics. If someone refactors `register_new_model_version` to silently persist (Rule 7 violation), G139 wouldn't catch it. The diagnostic-only discipline depends on engine-author care + the auto-method-marker scan + closure-cockpit review during PR review.

**Cross-arc integration with model_governance is informal.** ml_governance arc engines (specifically ENH-283 and ENH-285) consume model_governance G124 outputs (drift metrics) via caller integration into ProductionPerformanceSnapshot. There's no audit gate enforcing this integration is correct — the caller writes whatever drift value they got from `detect_drift_psi`/`ks`/`wasserstein` and trusts the metric_name. A future enhancement could add a typed bridge between the two arcs.

**Bandit retrofit is queued indefinitely.** ENH-126 cross_sell_bandit is in MLOPS_INTEGRATION_REGISTRY with `uses_v10_76_hook_contract=False` and all wiring flags `True`. Actually retrofitting the bandit to capture adjudication via ENH-282 would require non-trivial work (the bandit decision logic is internal, not pluggable; would need to wrap the recommendation surface in a caller-side adjudication capture). Documented as post-closure operations work; not a regression because the bandit was working pre-arc.

**Markdown serialization in cockpit is browser-rendered, not file-saved.** The cockpit's Tab 5 ("Model Cards") shows the markdown preview in an expander but doesn't save it to disk. Saving to disk would be a download-button pattern; left to a future enhancement when operations needs it.

---

**ml_governance arc CLOSED at v10.86.**

15th closed arc on the platform. Cleared to begin the next arc when business prioritizes. Future-arc engineers inherit the patterns: caller-supplied data discipline, Rule 7 diagnostic-only, Rule 1 full provenance, G-gate closure ratchet pair (or triplet when there's a cross-platform wiring catalog), closure cockpit, Tier expansion in admin page.
