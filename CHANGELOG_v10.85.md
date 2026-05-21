# CHANGELOG v10.85 — ml_governance arc 5/N (ENH-285 MLOps Model Card Composer)

**Status:** Single batch. ml_governance arc 5 of 5 — **all engines active**. Final engine before arc closure batch (v10.86 will ship G139+G140+G141 + closure cockpit + Master Prompt update).

**Audit:** 138/138 PASS (closure ratchets next drop)
**Active standards:** 153/260 (+1 ENH-285)
**Scenario library:** 186 (+4 MCD scenarios)
**Engine self-tests:** 151/151 (+1 mlops_model_card_composer)
**ml_governance arc scenarios:** 20 (4 each across MRG/ADJ/RTR/ABT/MCD — closure floor met)

---

## Why this engine closes the arc

The first four ml_governance arc engines each track one signal:
- ENH-281 mlops_model_registry → registry metadata (id, version, hashes, framework, owner, status, training metrics)
- ENH-282 mlops_adjudication_log → operator override rate over rolling window
- ENH-283 mlops_retraining_scheduler → retraining recommendation against caller policies
- ENH-284 mlops_ab_harness → shadow-vs-active comparison delta + composite severity

The model_governance arc at G124 produces one more: distribution drift via PSI/KS/Wasserstein.

ENH-285 sits at the consumer end where every signal flows into a single documentation surface — the model card. The card is the artifact a regulator examines: all the provenance for one model in one place. When the regulator asks "what's deployed, who owns it, when was it trained, how is it performing in production, what's the retraining cadence, when was the last shadow comparison, is there a known bias signal" — the model card answers all of it from one structured dataclass plus a markdown rendering.

The composer is structured per Mitchell et al. 2019 *Model Cards for Model Reporting* (FAccT) — the canonical reference for ML governance documentation — with production performance extensions (override_rate_30d, drift_metric_value, last_retraining_outcome, last_ab_severity) for ongoing monitoring.

## What landed

`utils/mlops_model_card_composer.py` (~1300 lines, **20/20 tests pass**). Five capabilities:

### 1. compose_model_card

Orchestrator. Takes registry fields + narrative + optional production snapshot. Validates required fields, narrative completeness (Mitchell et al. §3 required sections), metric Decimal/non-NaN sanity. CardComposeOutcome `COMPOSED` (with frozen ModelCard) or `REJECTED_INVALID` (with all findings surfaced per Rule 1).

The narrative requires four base sections (intended_use, out_of_scope_use, training_data_description, evaluation_data_description) at composition time — the engine refuses to compose a card with missing required narrative because *those require human authorship*. Engine cannot compose intended_use or ethical_considerations from data. Two more narrative sections (ethical_considerations, caveats_and_recommendations) are validated at completeness time but not required at composition time — letting callers compose a draft card and progressively complete it.

Per Rule 7, engine never persists. Caller appends to their archive.

### 2. validate_card_completeness

Given a ModelCard + caller-supplied `CardCompletenessRequirements(require_narrative, require_production_snapshot, required_metric_names, require_training_completion_timestamp)`, surface all missing sections. Outcome COMPLETE / INCOMPLETE.

Per Rule 1, all missing sections surface (not just first). Operator sees whether one edit fixes it or whether the card has multiple gaps. This is the "regulatory-grade gate" applied at examination time: caller defines what regulatory-grade means for their bank, engine surfaces compliance.

### 3. compute_card_diff

Field-by-field diff between two cards. Useful for promotion review: active card vs candidate card, what changed?

Per Rule 1, every field diff surfaces — changed and unchanged. Operator sees the full picture. Per Rule 7, engine surfaces diff but cites ENH-281 `validate_promotion_readiness` as the actual promotion gate. The card diff is summary view; ENH-281 with PromotionGate evaluation is the gate.

### 4. build_revision_history

Given chronological card sequence, build summary statistics + per-revision entries. Sorted by `composed_at_iso` ascending. Useful for regulatory examination: regulator sees the full revision narrative chronologically.

### 5. serialize_card_to_markdown

Render structured ModelCard to markdown. Markdown is **generic, not regulator-specific** — that's the deliberate Rule 7 line. XBRL / iTax / CBK formats are `regulatory_reporting` territory. Source of truth remains the structured ModelCard; markdown is a rendering for human consumption.

## Rule 7 boundaries

Engine NEVER:
- Persists cards (caller stores in JSON / PG / archive)
- Serializes to regulator-specific schemas (regulatory_reporting arc territory)
- Decides whether a card is "good enough" beyond caller-supplied requirements
- Publishes cards externally
- Reads other engines directly (caller integrates upstream outputs into ProductionPerformanceSnapshot)
- Auto-fills missing narrative sections (those require human authorship — engine cannot compose intended_use from data)

## 4 new scenarios MCD-01..04

**MCD-01** clean composition — doc_classifier@2.0.0 with full narrative + training metrics → COMPOSED. Mitchell et al. 2019 cited.

**MCD-02** completeness gate surfaces all missing — card with 4 gaps (ethical_considerations + caveats_and_recommendations + production_snapshot + training_completed_at_iso) → INCOMPLETE with all 4 sections in missing_sections. Engine surfaces full picture, never just first missing.

**MCD-03** diff between active and candidate cards — v1.0.0 (acc 0.85, ACTIVE) vs v2.0.0 (acc 0.91, PROPOSED). Every changed field surfaces. ENH-281 promotion gate boundary cited in framework_refs.

**MCD-04** **full arc integration** — compose_model_card with `ProductionPerformanceSnapshot` composed from ENH-282 (override 0.08) + G124 (PSI 0.06) + ENH-283 (NOT_YET retraining) + ENH-284 (READY_TO_PROMOTE A/B). Markdown serialization includes all upstream signals. The arc closure story: every engine produces a signal that flows into the card.

## Files changed

- **NEW** `utils/mlops_model_card_composer.py` (~1300 lines, 20 tests)
- **MOD** `utils/standards_registry.py` (ENH-285 added)
- **MOD** `utils/scenario_simulator.py` (4 MCD scenarios)
- **MOD** `pages/7_admin.py` (Tier 29 fifth entry)
- **NEW** `CHANGELOG_v10.85.md`

## ml_governance arc state — all engines active

| Standard | Engine | Drop | Status |
|---|---|---|---|
| ENH-281 | mlops_model_registry | v10.81 | active |
| ENH-282 | mlops_adjudication_log | v10.82 | active |
| ENH-283 | mlops_retraining_scheduler | v10.83 | active |
| ENH-284 | mlops_ab_harness | v10.84 | active |
| ENH-285 | mlops_model_card_composer | **v10.85** | **active** |

**5/5 active. 20/20 arc scenarios (closure floor met).**

## What v10.86 brings (arc closure batch)

The closure batch follows the established 5-thing pattern (per the Lean+Compact protocol):

1. **G139 + G140 closure ratchet pair** — G139 verifies all 5 mlops_* standards active with required symbols on each engine module (using `dir()` + `inspect.signature()` introspection per the trade_finance closure lesson — never assume names from memory). G140 verifies arc-level scenario count ≥ 20 and per-engine scenario count ≥ 4.

2. **G141 cross-platform wiring gate** — the audit-side answer to "apply this everywhere." A new `MLOPS_INTEGRATION_REGISTRY` constant in standards_registry.py enumerates each ML-using engine + which mlops_* engines it integrates with. G141 verifies every engine in that registry exists in utils/* and has the v10.76 hook contract markers. Discipline becomes a property of the codebase, not a checklist line item. Same enforcement pattern as G108/G109/G110 from older closed work.

3. **Closure cockpit `pages/98_ml_governance_arc_cockpit.py`** — single pane of glass for ML governance. Tabs: Registry (every model_id + active version + governance breach detection), Adjudication (override rate per model with class-level pattern surfacing), Retraining (calendar sorted by urgency), A/B (in-flight comparisons by candidate), Model Cards (compose + validate + diff). All consuming caller-supplied data; no automatic capture.

4. **Tier 29 promotion** — label flips from "in flight, closes vTBD" to "closed at v10.86" and adds the closure cockpit page entry.

5. **Master Prompt v10.86 update + CHANGELOG_v10.86.md.**

After v10.86, ml_governance becomes the **15th closed arc** alongside Climate (G120), Credit (G121), KESONIA, RMS (G122), Audit-GRC (G123), Model Governance (G124), Virtual Bank (G125), Bandit (G126), Treasury (G127), Risk (G129+G130), credit_model_risk (G131+G132), revenue_assurance (G133+G134), finance (G135+G136), trade_finance (G137+G138), and ml_governance (G139+G140+G141).

## Honest acknowledgements

**Markdown is the only serialization format.** The engine ships markdown rendering specifically because (1) it's generic and human-consumable; (2) most stakeholders can read it without tooling; (3) writing each caller's renderer separately would lead to subtle differences. Other formats (JSON, YAML, XBRL, iTax) are deliberately not implemented — those are caller's serialization concerns. JSON in particular would be trivial (just `dataclasses.asdict(card)`), but the line is "engine doesn't decide serialization format beyond markdown for human consumption."

**Production snapshot is opt-in.** A card without a `ProductionPerformanceSnapshot` is fine for an initial registration (model just trained, not yet deployed, no production data). Caller decides when to attach a snapshot. The completeness gate's `require_production_snapshot=True` is what enforces "every regulatory-grade card must have a production snapshot" — defaults to False for new-model convenience.

**Snapshot field naming is opinionated to match arc engines.** `override_rate_30d` is a 30-day window, baked into the field name. If callers want a different window (90-day, 7-day), they integrate ENH-282 with that window externally and put the result in the field anyway. The 30-day window is the most common observation period in ML governance literature; if callers need flexibility, they can extend the snapshot dataclass via subclassing in their caller code (frozen dataclass means inheritance pattern, not mutation).

**Card diff is field-by-field, not semantic.** A whitespace change in `intended_use` shows as `changed`. A reordering of metric keys would not show as changed (Mapping comparison is unordered). For semantic diff (only flag *meaningful* changes), caller would post-process the field_diffs tuple. Engine surfaces every diff per Rule 1; caller decides what's meaningful.

**Revision history sorted by composed_at_iso.** This is the timestamp the card was composed, not the timestamp the model was trained. Two cards composed for the same model_version on different dates (e.g. one at training time, another after a year of production data is available) would both appear in revision history. This is the right behavior — each card composition is a documentation event; multiple cards can exist for the same model.

**No automatic narrative generation.** Some MLOps platforms generate first-draft narrative from training metadata. This engine deliberately does not — narrative requires human authorship. The trade-off: more friction at composition time, but no risk of generated narrative quietly filling sections that should reflect human judgment about ethical considerations or out-of-scope use.

**No native validation against training data lineage.** The card preserves `training_data_hash` as a string. It doesn't verify that the hash corresponds to a real dataset the platform can locate. That's lineage system territory — beyond engine scope.

**Cleared to proceed to v10.86 closure batch** when ready. Closure brings the 15th closed arc.
