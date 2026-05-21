# CHANGELOG v10.19 — RMS Arc Batch 2: Workflow + Memory + Timing + Guards

**Audit:** 121/121 PASS — **102nd consecutive clean.**

## What ships in v10.19

`utils/reconciliation_workflow.py` — 1289 lines, **Cat A**. 4 of 17 RMS standards active:

| Standard | Implemented as |
|---|---|
| **ENH-183** Exception Management & Workflow | `ExceptionType` enum (10 types) + `ExceptionState` enum (9 states) with explicit `ALLOWED_EXC_TRANSITIONS` graph + 4 terminal states; `AssignmentQueue` enum (9 queues) with `assign_queue()` routing by exception type + amount tier + source hint; `AgingBucket` enum (4 buckets: FRESH_0_3, AGING_4_7, OVERDUE_8_30, BREACH_30_PLUS); `DEFAULT_SLA_DAYS` per exception type; `ExceptionRecord` dataclass with `days_open()` / `aging()` / `is_sla_breached()` methods |
| **ENH-RMS-R2** Memory-Layer Architecture | `compute_signature()` deterministic key builder (exception_type \| amount_bucket \| first-3-tokens-of-counterparty); `ResolutionPattern` dataclass; `MemoryLayer` class with `record_resolution()` + `recall()`; confidence growth via `confidence_from_occurrences()` (LOW=0.5 at 1 occ, MEDIUM=0.75 at 3+, HIGH=0.90 at 10+) |
| **ENH-RMS-R4** Timing-Difference Auto-Handling | `TimingDifferenceConfig` (max_lag_days=3, auto_resolve_max_lag_days=1, require_same_amount=True); `TimingDifferenceCandidate` with `can_auto_resolve` flag; `detect_timing_difference()` returns None for unmatched amount/counterparty/lag-too-large, returns auto-resolvable candidate for T+1 same-amount, returns review-required for T+2/T+3 |
| **ENH-RMS-R5** Governed Execution Layer (TruePath-style) | `GuardRailType` enum (7 types: AMOUNT_LIMIT, ALLOWED_ACCOUNT_TYPES, BUSINESS_HOURS_ONLY, REQUIRES_DUAL_APPROVAL, RATE_LIMIT_PER_HOUR, BLOCKED_COUNTERPARTIES, PATTERN_CONFIDENCE_FLOOR); `GuardRail` dataclass + `evaluate_guards()` returning `GovernedExecutionDecision` with per-guard outcomes + blocked_by list + dual-approval flag; defaults: KES 50K auto-resolution amount limit, 0.75 pattern-confidence floor |

## Regulatory provenance

- **CBK Prudential Guideline CBK/PG/02** — operational risk framework
- **CBK CRMF April 2021 §6** — internal controls + reconciliation requirements
- **CBK Banking Act §39** — books and records integrity
- **PCAOB AS 2401** — fraud risk + management override of controls
- **SOX §404** — internal control over financial reporting
- **COSO ERM** — three lines of defense + control activities
- **Basel BCBS 239 §5** — accuracy and integrity principles
- **Kenya Data Protection Act 2019 §28** — retention principles

## Key design decisions

### Explicit transition graph for exception states
`ALLOWED_EXC_TRANSITIONS` is a deterministic directed graph. Invalid skips raise `ValueError`. NEW must go through ASSIGNED → INVESTIGATING → MANUALLY_RESOLVED (or any of several escalation paths) — caller cannot jump from NEW directly to MANUALLY_RESOLVED. Same explicit-transition pattern as v10.13 credit_workflow + v10.15 document_management. The 4 terminal states (AUTO_RESOLVED, MANUALLY_RESOLVED, WRITTEN_OFF, REJECTED_NEEDS_REVERSAL) have empty out-edges.

### Queue routing is rule-based + auditable
`assign_queue()` checks high-amount tier first (>10M → MGMT_REVIEW always), then source hint (NOSTRO → NOSTRO_DESK, MPESA → MOBILE_MONEY_OPS, CARD → CARDS_OPS, etc.), then amount tier (>100K → TIER2 else TIER1). Pure deterministic logic — auditors can trace any exception's queue assignment to a specific rule.

### Memory layer: signature-based, not embedding-based
Per Rule 1 honesty, the memory layer uses an explicit `compute_signature()` key (exception_type | amount_bucket | first-3-tokens-of-counterparty). When the engine recalls a pattern, the caller sees:
- whether a pattern was found
- the occurrence count (evidence weight)
- the historical resolution + GL account
- confidence (0.5/0.75/0.90 from 1/3/10+ occurrences)

This is intentionally simpler than ML embeddings. Production deployments can swap in vector-similarity (FAISS, pgvector) by replacing `compute_signature` + `recall` while keeping the rest of the engine. The deterministic baseline is auditor-defensible.

### Confidence grows in 3 discrete steps
Rather than a continuous function, confidence is `0` (no pattern) → `0.5` (1 occurrence) → `0.75` (3+) → `0.90` (10+). This makes reasoning easy: if the pattern-confidence-floor guard requires `≥0.75`, you need at least 3 occurrences before auto-action is permitted. New patterns explicitly need to "earn" their automation rights.

### Timing difference: T+1 auto, T+2/T+3 review
Per industry convention (matches CBK settlement cycles), `auto_resolve_max_lag_days=1` permits same-day → next-day timing matches to auto-resolve. T+2 and T+3 (within `max_lag_days=3`) surface as candidates with `can_auto_resolve=False` — manual review. Beyond T+3, no candidate at all (returns None).

### Governed execution: per-guard outcomes always visible
`GovernedExecutionDecision` returns `guards_evaluated: Tuple[GuardCheckResult, ...]` showing every guard's pass/fail + reason. Caller sees exactly why an action was blocked, not just "denied". This is the TruePath-style transparent guardrail principle: actions taken (or refused) must be explainable.

### Dual approval is a side flag, not a blocker
When `REQUIRES_DUAL_APPROVAL` triggers (amount above threshold), `is_permitted=False` AND `requires_dual_approval=True`. Caller's UI can route to the dual-approval queue rather than treating it as a hard block. This separates "blocked" from "needs second signature" semantically.

### Compose, don't modify
v10.18's `reconciliation_matching.py` is unchanged. v10.19 adds the workflow layer above it. Caller flow:
```python
# v10.18: matching produces unmatched + medium/low confidence results
results, report = matching_engine.match_run(sources, targets)

# v10.19: convert unmatched to exceptions, route to queues
for r in results:
    if r.algorithm == MatchAlgorithm.UNMATCHED:
        exc = ExceptionRecord(...)
        workflow_engine.register_exception(exc)
        # Try auto-resolve via memory + guards
        decision = workflow_engine.attempt_auto_resolve(...)
```

## Engine Hub integration

Tier 10 expanded from 1 to 2 engines. The new `reconciliation_workflow` entry covers the full lifecycle, memory, timing, and guard surfaces. **G117 coverage holds at ≥ 95%.**

## Tests

- 36 self-tests in `reconciliation_workflow.py`
- 26 integration tests in `tests/integration/test_v10_19_reconciliation_workflow.py`

## Verified output

```
✓ reconciliation_workflow self-test passed (36 tests)
Ran 363 tests in 48.713s OK
Audit: 121/121 gates PASS
```

## Standards registry — 8 RMS active

```
RMS (subcategory) — 8 of 17 active after v10.19:
  ENH-181:    Multi-Source Data Ingestion                   (v10.18)
  ENH-182:    Intelligent Matching Engine                   (v10.18)
  ENH-183:    Exception Management & Workflow              (v10.19) ← NEW
  ENH-RMS-R1: 90%+ AI-Matching Threshold Target             (v10.18)
  ENH-RMS-R2: Memory-Layer Architecture                     (v10.19) ← NEW
  ENH-RMS-R3: Vendor Name Normalization Library             (v10.18)
  ENH-RMS-R4: Timing-Difference Auto-Handling               (v10.19) ← NEW
  ENH-RMS-R5: Governed Execution Layer (TruePath-style)    (v10.19) ← NEW

RMS still planned: 9 (for v10.20-v10.21; v10.22 closes)
```

## Honest acknowledgements

1. **Memory signature is simple by design.** The 3-token canonicalization handles "ACME LIMITED Q3 PAYMENT" and "ACME LIMITED Q4 PAYMENT" as the same signature (only first 3 tokens matter). This is intentionally lossy — production deployments will likely tighten or loosen depending on transaction patterns. Override `compute_signature()` for custom behavior.

2. **No embeddings or ML clustering.** This batch ships rule-based pattern recall. ML clustering (e.g., DBSCAN on transaction embeddings) is a future enhancement; the architecture supports it via signature replacement.

3. **Confidence step function is heuristic.** 1/3/10 occurrence boundaries are conventional but not derived from data. Production deployments can recalibrate against historical false-positive rates.

4. **Timing-difference T+1/T+3 limits are configurable but not auto-tuned.** Banks with longer settlement cycles (e.g., USD correspondent timing) override via `TimingDifferenceConfig.max_lag_days`. Auto-tuning from historical match latency is future work.

5. **Guards run independently — no cross-guard logic.** Each guard evaluates in isolation. A complex policy like "amount > 50K AND counterparty unknown → require dual approval" requires composing two guards. The architecture supports this; the seed library is intentionally simple.

6. **No persistence.** Exceptions + memory live in-memory per engine instance. Postgres persistence wires in a dedicated batch.

7. **No real-time concurrency control.** Greedy in-memory engine assumes single-process invocation. Multi-process deployment needs a database backend with appropriate row-locking.

8. **Pattern recall doesn't disambiguate variants.** If two different resolutions occurred for the same signature historically, the engine reports the most-recent — not the most-frequent or majority. Per Rule 1 (no fabrication of statistical mode), recent is honest. A future enhancement could surface "this signature has had 3 different resolutions historically" as additional context.

## What v10.20 ships next

**Specialized reconciliation types** (4 standards):
- ENH-185 CBK Regulatory Reconciliation
- ENH-186 Nostro/Vostro Reconciliation
- ENH-187 Intercompany & Internal Suspense Reconciliation
- ENH-RMS-R6 Real-time KEPSS / PesaLink Reconciliation

These extend the v10.18 matching engine + v10.19 workflow with regulator-specific rules + correspondent-banking specifics + real-time payment-system integration.

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG (v10.6–v10.10) | 13/13 | ✅ closed |
| Batch 2 — Credit (v10.11–v10.16) | 19/19 | ✅ closed |
| Enhancement — KESONIA (v10.17) | 1/1 | ✅ closed |
| **Batch 3 — RMS Reconciliation (v10.18–v10.22)** | **8/17** | **🟡 in flight (2 of 5 batches)** |
| Batch 4 — Audit/GRC | 0/17 | pending |
