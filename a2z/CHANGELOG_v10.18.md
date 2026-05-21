# CHANGELOG v10.18 — RMS Arc Opens: Reconciliation Matching Engine

**Audit:** 121/121 PASS — **101st consecutive clean.**

## Important context — RMS = Reconciliation Management System

Before opening this arc I confirmed in the registry that **RMS in this codebase means Reconciliation Management System**, not Relationship Management System. Standards ENH-181 through ENH-190 + 7 research additions (ENH-RMS-R1..R7) all cover transaction reconciliation: GL vs bank statement matching, Nostro/Vostro, KEPSS/PesaLink, AI-powered matching, sub-monthly daily reconciliation. There's a pre-existing `pages/30_rms.py` UI focused on CBS-to-GL reconciliation that confirms this interpretation.

The user-facing memory snapshot mentioned "RMS — 90% AI matching, candidate sourcing, BSC integration" which combined two concepts; the candidate-sourcing/BSC piece belongs to a different (Relationship Manager) module already partially shipped in `utils/rm_profitability.py` (Standard #23). This arc is about reconciliation only.

## 5-batch RMS arc plan

| Batch | Theme | Standards |
|---|---|---|
| **v10.18** | **Core matching engine** | **ENH-181, 182, RMS-R1, RMS-R3 (4)** |
| v10.19 | Exception + workflow + governed exec | ENH-183, RMS-R2, RMS-R4, RMS-R5 (4) |
| v10.20 | Specialized recon (Nostro/CBK/IC/KEPSS) | ENH-185, 186, 187, RMS-R6 (4) |
| v10.21 | Realtime + AI learning + audit + sub-monthly | ENH-184, 188, 189, 190, RMS-R7 (5) |
| v10.22 | G122 audit gate + RMS arc closure | (locks 17) |

## What ships in v10.18

`utils/reconciliation_matching.py` — 972 lines, **Cat A**. 4 of 17 RMS standards active:

| Standard | Implemented as |
|---|---|
| **ENH-181** Multi-Source Data Ingestion | `DataSource` enum (13 sources: GL, CBS, Bank Statement, Sub-Ledger, Nostro, Vostro, Mobile Money, Card Network, KEPSS, PesaLink, SWIFT MT/MX, Suspense), `ingest_transactions()` with default + custom parser hook, errors surfaced explicitly per Rule 1 |
| **ENH-182** Intelligent Matching Engine | 7-algorithm `MatchAlgorithm` enum (EXACT_REFERENCE → EXACT_AMOUNT_DATE → AMOUNT_DATE_TOLERANCE → AMOUNT_NAME_COMBINED → FUZZY_NAME → ML_RANKED → UNMATCHED), `match_pair()` with confidence assignment + auto-match flag |
| **ENH-RMS-R1** 90%+ AI-Matching Threshold Target | `AUTO_MATCH_THRESHOLD = 0.90` enforced, `MatchingRunReport.meets_target_rate` boolean reflecting per-run achievement, board-level aggregation |
| **ENH-RMS-R3** Vendor Name Normalization Library | `normalize_vendor_name()` + Kenya-specific legal-suffix stripping (LIMITED, LTD, PLC, SACCO, ENTERPRISES, INVESTMENTS, etc. — 21 suffixes) + synonym expansion (PVT→PRIVATE, INTL→INTERNATIONAL, etc.), `name_similarity()` via Jaccard token similarity (deterministic, audit-friendly) |

## Regulatory provenance

- **CBK Prudential Guideline CBK/PG/02** — operational risk
- **CBK CRMF April 2021 §6** — internal controls + reconciliation
- **Kenya Banking Act §39** — bank books and records integrity
- **Basel BCBS 239** — risk data aggregation and reconciliation principles
- **PCAOB AS 2110** — audit risk assessment + walkthroughs
- **ICAEW Tech 04/02** — bank reconciliations + control framework
- **SOX §404** — internal control over financial reporting
- **ISO 20022** — financial messaging standard (KEPSS/PesaLink ready)

## Key design decisions

### Vendor name normalization is deterministic, not stochastic
`normalize_vendor_name()` is a 5-step deterministic pipeline:
1. uppercase + trim
2. remove punctuation (keep `&` and `'`)
3. apply 16-entry synonym map (PVT→PRIVATE, INTL→INTERNATIONAL, etc.)
4. strip trailing legal suffixes (21 entries: LIMITED, LTD, PLC, SACCO, COMPANY, etc.)
5. collapse whitespace

This is auditable — given the same input, it always produces the same output. No ML "smart matching" that's hard to defend at audit time.

`name_similarity()` uses **Jaccard token similarity** (intersection / union of token sets) which is also deterministic and easy to explain. Much better than Levenshtein for bank reconciliation where word order varies.

### 7-algorithm matching ladder
The engine tries algorithms in priority order and stops at first confident match:

| # | Algorithm | Score | Auto-match? | When |
|---|---|---|---|---|
| 1 | EXACT_REFERENCE | 1.00 | ✅ | Both transactions have identical reference |
| 2 | EXACT_AMOUNT_DATE | 0.99 | ✅ | Same value date + same amount (signed match for inter-bank) |
| 3 | AMOUNT_NAME_COMBINED | 0.92 | ✅ | Amount tolerance + date tolerance + good name similarity |
| 4 | AMOUNT_DATE_TOLERANCE | 0.85 | ❌ (review) | Amount tolerance + date tolerance, weak name |
| 5 | FUZZY_NAME | 0.65 | ❌ (investigation) | Strong name match, weak amount/date |
| 6 | ML_RANKED | (varies) | depends | Injected ML score above threshold |
| 7 | UNMATCHED | None | ❌ | Nothing fired |

### Greedy 1-to-1 assignment
After scoring all source × target candidate pairs, the engine sorts by descending score and assigns greedily — a target matched to one source is removed from the candidate pool. This prevents double-assignment (which would otherwise inflate auto-match rate while breaking conservation: total source amount ≠ total matched amount).

### Signed-amount matching for inter-bank
A bank's GL credit (+1000) matches the counterparty bank statement's debit (-1000). The engine tries **both orientations** (`a.amount == b.amount` OR `a.amount == -b.amount`) so inter-bank reconciliation works without callers manually flipping signs. Same-sign match is also accepted for intra-system reconciliation.

### Rule 7 — ML hookable, not silent
`ml_ranker: Optional[Callable]` accepts a custom matcher. When wired:
- Engine calls it for pairs that rule-based methods couldn't match
- Returns a score in [0, 1]
- Confidence and auto-match flag derived from same thresholds
- ML failures (exceptions) are caught — fall through to UNMATCHED, never crash

When `ml_ranker` is None, only rule-based algorithms run. `SPEC_DEVIATION_NOTE` documents this.

### Run-level reporting
`MatchingRunReport` aggregates per-run KPIs:
- Auto-match rate % (target ≥ 90% per ENH-RMS-R1)
- `meets_target_rate` boolean
- Counts by algorithm (visibility into what's matching what)
- Counts by confidence band (review queue size, investigation queue size)

`board_summary()` aggregates across multiple runs for governance reporting.

## Engine Hub integration

Tier 10 added to `pages/7_admin.py`:
- `reconciliation_matching` (`ReconciliationMatchingEngine`)

G117 coverage holds at ≥ 95%.

## Tests

- 27 self-tests in `reconciliation_matching.py`
- 22 integration tests in `tests/integration/test_v10_18_reconciliation_matching.py`

## Verified output

```
✓ reconciliation_matching self-test passed (27 tests)
Ran 337 tests in 38.189s OK
Audit: 121/121 gates PASS
```

## Standards registry — 4 RMS active

```
RMS (subcategory) — 4 of 17 active after v10.18:
  ENH-181:    Multi-Source Data Ingestion                   (v10.18) ← NEW
  ENH-182:    Intelligent Matching Engine                   (v10.18) ← NEW
  ENH-RMS-R1: 90%+ AI-Matching Threshold Target             (v10.18) ← NEW
  ENH-RMS-R3: Vendor Name Normalization Library             (v10.18) ← NEW

RMS still planned: 13 (for v10.19-v10.21; v10.22 closes)
```

## Honest acknowledgements

1. **The 21 Kenya legal suffixes are heuristic.** Production deployment may need to add bank-specific tokens (e.g., specific counterparties' brand suffixes). The list is in `_KENYA_LEGAL_SUFFIXES` and is straightforward to extend.

2. **Synonym map is small (16 entries).** Real bank deployments typically grow this to 100+ entries based on reconciliation breaks. The architecture supports extension; the seed list covers the most common Kenya/East Africa cases.

3. **Jaccard similarity is one of many options.** Levenshtein, Damerau-Levenshtein, and Soundex are alternatives. Jaccard wins for tokens-with-suffix-stripping because it's order-insensitive and doesn't penalize abbreviations after normalization.

4. **Date tolerance default is T+3.** This works for most non-realtime contexts. KEPSS/PesaLink real-time reconciliation (v10.20) will use T+0 by default with explicit override.

5. **Amount tolerance default is KES 0.50** (50 cents). This handles standard rounding/cents differences. Larger tolerances (e.g., for FX-denominated reconciliation) belong on the calling side as explicit overrides.

6. **Greedy 1-to-1 assignment is suboptimal.** A real production system would solve the assignment problem optimally (Hungarian algorithm, O(n³)). Greedy is fast and produces reasonable results; switching to optimal is mechanical.

7. **No persistence.** Match runs are computed in-memory; postgres persistence wires in later batches.

8. **No actual ML model ships.** `ml_ranker` is the hook (Rule 7). Real ML matching (using transformers, embeddings, or learned thresholds from historical confirmed matches) is per-deployment.

9. **Match results don't yet handle 1-to-many or many-to-1 cases.** ENH-183 (Exception Management & Workflow) in v10.19 will handle these, including timing-difference auto-handling per ENH-RMS-R4.

## What v10.19 ships next

**Exception management + workflow + memory layer + governed execution** (4 standards):
- ENH-183 Exception Management & Workflow
- ENH-RMS-R2 Memory-Layer Architecture (recurring exception patterns persisted)
- ENH-RMS-R4 Timing-Difference Auto-Handling (T+1/T+2 same-amount auto-resolved)
- ENH-RMS-R5 Governed Execution Layer (TruePath-style — guardrails on auto-actions)

These build on v10.18 by adding workflows for the unmatched + review-queue + investigation buckets.

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG (v10.6–v10.10) | 13/13 | ✅ closed |
| Batch 2 — Credit (v10.11–v10.16) | 19/19 | ✅ closed |
| Enhancement — KESONIA (v10.17) | 1/1 | ✅ closed |
| **Batch 3 — RMS Reconciliation (v10.18–v10.22)** | **4/17** | **🟡 in flight (1 of 5 batches)** |
| Batch 4 — Audit/GRC | 0/17 | pending |
