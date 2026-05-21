# CHANGELOG v10.144 — ENH-133 Customer Needs & Gap Analysis

**Status:** **PHASE 1E PRODUCT 3/10 ACTIVE.** Third engine of the Product Module — registry-driven customer needs catalogue + per-customer gap analysis combining portfolio-count, propensity, and behavioural-signal dimensions.

**Audit:** `Score: 146/146 gates = 100.0% — PASS` (quoted from `python scripts/audit.py`). No new gate; engine-level drop. **G142 anti-drift floor 68 → 69**. G144 264/264; G145; G146; G117 unchanged. Engine self-tests 152/152. v10.144 tests 22/22 pass.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/customer_needs_analyzer.py` | ~520 | NEW. CustomerNeedsAnalyzer with 6 public methods + frozen CustomerGap dataclass |
| `data/customer_needs_registry.json` | 9 needs / 4 segments | NEW seed. Bank-curated needs catalogue + segment expectations |
| `utils/standards_registry.py` | +1 line | ENH-133 status flipped planned → active |
| `pages/7_admin.py` | +24 lines | Tier 4B extended with third engine entry |
| `tests/test_product_v10_144.py` | ~250 | NEW. 22 tests across 8 classes |
| `docs/Master_Prompt_v3.37.md` | ~1100 | Anti-drift sync v3.36 → v3.37 |
| `SCOPE_LEDGER.md` | updated | v10.144 row + status block + cadence correction |
| `CHANGELOG_v10.144.md` | this file | This document |

---

## The engine — `utils/customer_needs_analyzer.py`

Per Continuation.docx Standard #133: "Customer needs registry, gap analysis, and value proposition builder."

### Scope split with ENH-135

The standard mentions "value proposition builder" — that's ENH-135's scope (the CVP Builder, two drops away). ENH-133 ships the **needs registry foundation** + **gap analysis layer**. ENH-135 will consume this engine's outputs to draft per-segment value propositions.

### Three gap dimensions

For each customer, the engine combines:

1. **Portfolio-count gap** — `expected_products_held - actual_products_held`. The expectation is segment-driven (Mass=3, Mass Affluent=5, Affluent=6, Premium=8) per the `data/customer_needs_registry.json` seed. Customer below their segment's expected count has a portfolio gap.

2. **Propensity gaps** — the customer's own ranked `propensity_scores` list from `data/customer_intelligence.json`. This list is already the customer's revealed-preference unmet ladder (each entry is a product the propensity model says they're likely to acquire, i.e. don't yet hold). Engine carries it through unchanged — no re-ranking, no fabrication.

3. **Behavioural-signal gaps** — derived from `data/customer_intelligence.json` fields:
   - `RETENTION_RISK_MITIGATION` triggers when `churn_risk` exceeds segment max (e.g. 0.5 for Mass)
   - `SERVICE_QUALITY_RECOVERY` triggers when `complaints_12m` exceeds segment max
   - `RELATIONSHIP_MANAGEMENT` triggers when `last_contact_days` exceeds segment max
   - `DIGITAL_CONVENIENCE` triggers when `digital_engagement == "Low"`

### Severity classification with explicit rationale

```
HIGH    if portfolio_gap >= 3
        OR any behavioural_gap with severity == HIGH
        OR >= 2 behavioural gaps total

MEDIUM  if portfolio_gap >= 1
        OR any behavioural_gap (single, non-HIGH)

NONE    otherwise
```

The rule chain that fired is logged in `severity_rationale` as a tuple of strings (e.g. `("portfolio_gap_count=4>=3_threshold",)` or `("behavioural_gaps_HIGH=1>=1",)`) — operators can audit exactly why a customer was flagged.

### Public methods

- `get_customer_needs(customer_id)` — ranked needs combining propensity_scores + segment-archetype priorities
- `analyze_customer_gap(customer_id)` → `CustomerGap` (frozen)
- `get_segment_gap_summary(segment)` — segment aggregate with top behavioural gap frequencies + CLV at risk
- `get_top_unmet_needs(top_n)` — bank-wide ranking by frequency × CLV impact
- `get_high_priority_gaps(min_clv)` — filtered HIGH-severity list, sorted by CLV descending
- `bank_wide_gap_summary()` — totals + per-segment breakdown

### Honesty discipline

- **`products_held` is an integer count (not a list of product IDs)** in customer_intelligence.json. Engine is honest about that limitation — portfolio gap is at the count level. Per-customer per-product holdings would need a different data feed (likely from FLEXCUBE).
- **Propensity ordering preserved** — the engine doesn't override the customer's revealed-preference list with its own ranking.
- **Unknown customer returns explicit fallback** — `found=False` + `fallback_reason="customer_not_found"`. Never fabricates a segment.
- **`severity_rationale` is the audit trail.** Operators reviewing a flagged customer see the exact rule that fired.
- **Read-only contract.** Never writes to `performance.*` or any other table.

---

## Self-test on real data

`python -m utils.customer_needs_analyzer`:

```
Bank-wide: n=3000 HIGH=1845 (61.5%) MED=885 NONE=270
  Mass: n=1520 HIGH=686 avg_gap=0.49
  Mass Affluent: n=920 HIGH=646 avg_gap=1.67
  Affluent: n=402 HIGH=360 avg_gap=2.6
  Premium: n=158 HIGH=153 avg_gap=4.31
```

The honest finding: **Premium segment is the most under-served** — 153 of 158 customers HIGH-severity, average portfolio gap 4.31 against the 8-product expectation. The bank's own segment-of-choice strategy is the strictest baseline; meeting it is what the engine measures against. Mass segment is best-served (avg gap 0.49) — appropriate, since Mass expectations are lighter (3 products).

This is the kind of finding the standard was designed to surface. It's not flattering — it says the bank's Premium book hasn't been deepened to bank-of-choice levels — but it's actionable.

---

## Tests — `tests/test_product_v10_144.py`

22 tests across 8 classes:

- **TestEngineModule** (4) — exists / parses / class+dataclass present / 6 required methods
- **TestCustomerNeeds** (2) — existing customer ranked needs (propensity-first) / unknown fallback
- **TestGapAnalysis** (4) — unknown returns not_found / real customer full analysis / Premium severity path / propensity gaps carried through
- **TestAggregations** (5) — segment summary complete / unknown segment fallback / top unmet ranked / high-priority CLV filter / bank-wide composition adds up
- **TestRegistrySeed** (2) — registry exists+parses / 4 segment_expectations with required keys
- **TestRegistryAndAdmin** (3) — ENH-133 active / ENH-131+132 still active / admin Tier 4B has all three engines
- **TestNoRegression** (2) — audit gates intact / strategy module engines still active

All 22 pass via inline runner.

---

## Cadence correction

The v10.143 changelog mentioned shipping ENH-133 + ENH-134 as a "paired drop". On reflection, the standing rule **"never combine multiple standards into one ZIP file; deliver one standard per ZIP to prevent conflicts"** takes precedence. Each standard now ships in its own drop with full registry + admin + tests + master prompt + scope ledger + changelog. Module closure timeline pushed from ~v10.146 to ~v10.148.

The trade-off is real: more drops, more sequential work. The benefit is real too: clean rollback per standard, no merge conflicts when standards write to different files, audit trail per standard.

---

## Apply order

After v10.143:

```
1. utils/customer_needs_analyzer.py        → utils/
2. data/customer_needs_registry.json       → data/
3. utils/standards_registry.py             → utils/   (ENH-133 flip)
4. pages/7_admin.py                        → pages/   (Tier 4B extension)
5. tests/test_product_v10_144.py           → tests/
6. docs/Master_Prompt_v3.37.md             → docs/
7. SCOPE_LEDGER.md                         → root
8. CHANGELOG_v10.144.md                    → root
```

`git add -A && git commit -m "v10.144 ENH-133 Customer Needs & Gap Analysis — Phase 1E 3/10"`. Then `python scripts/audit.py` should print `Score: 146/146 gates = 100.0% — PASS`.

---

## Phase 1E Product trajectory (revised cadence)

| drop | scope | status |
|---|---|---|
| v10.142 | ENH-131 Product Profitability Intelligence | SHIPPED |
| v10.143 | ENH-132 Product Lifecycle Management | SHIPPED |
| **v10.144 (THIS)** | **ENH-133 Customer Needs & Gap Analysis** | **SHIPPED** |
| v10.145 | ENH-134 Competitive Intelligence for Products | next |
| v10.146 | ENH-135 CVP Builder | |
| v10.147 | ENH-136 Product Ranking + ENH-137 Dynamic Pricing | |
| v10.148 | ENH-138 + ENH-139 + ENH-140 → MODULE CLOSE + G147 + cockpit + G148 UI gate | |

**v10.145 next-up:** ENH-134 Competitive Intelligence for Products. Automated competitive monitoring and benchmarking. Will produce per-product competitive-positioning analysis that feeds ENH-135 CVP Builder.

---

## Summary

ENH-133 ships a registry-driven customer needs catalogue + three-dimensional gap analysis (portfolio + propensity + behavioural). The honest finding from running against the live 3000-customer dataset — 61.5% HIGH-severity gaps with Premium segment the most under-served — is the kind of evidence Eco Bank's Product Heads and Segment Heads need to act on. Phase 1E now 3/10. Total active 140/264 (53.0%).

**Quoting the audit script directly:** `Score: 146/146 gates = 100.0% — PASS`. v10.144 tests `22/22 pass`.
