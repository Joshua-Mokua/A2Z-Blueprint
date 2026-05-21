# A2Z MIS 360 — v10.193 Changelog

## CBK PRUDENTIAL RETURNS — engine extension from 5/8 to 8/8

**Release date:** 2026-05-06
**Audit score:** 159/159 gates = 100.0% PASS (unchanged from v10.192)

---

## Summary

This release extends the CBK Regulatory Reporting Engine
(`utils/cbk_regulatory_reporting.py`, ENH-252) from 5 returns to 8
returns by adding the three remaining standard CBK Prudential
schedule generators. This closes the platform-level deferral that
read "5/8 CBK reports" in the userMemories and brings the Diagnostic
CBK returns surface to its design completeness.

This is a real platform-level deferral closure — not a module
ratchet, not a UI fix — picked because of all four candidate
deferrals (PG migration, FATCA/CRS XML, CBK reports, React SPA), the
CBK reports have the highest direct relevance for an Ecobank Kenya
deployment. A Kenyan bank cannot operate without filing these
returns; the platform now diagnostically generates all eight of them
from the same engine surface.

---

## What shipped

### The 3 new returns

| Code | Schedule | Threshold | Reference |
|------|----------|-----------|-----------|
| **NPL** | Non-Performing Loans classification & provisioning | NPL gross ratio ≤ 10% | CBK PG/04 + IFRS 9 staging |
| **IRR** | Interest Rate Risk in the Banking Book | Δ EVE ≤ 15% of Tier 1 | CBK PG/03 §5 + BCBS SRP31 |
| **OPR** | Operational Risk Capital Charge | OPR-RWA share ≤ 25% of total RWA | CBK PG/03 §6 + Basel II §649 |

### Engine changes

`utils/cbk_regulatory_reporting.py` extends along the established
pattern:

1. **3 new enum values** added to `CbkReturnCode`: `NPL`, `IRR`, `OPR`.
2. **3 new frozen input dataclasses** added: `NplStaging`,
   `IrrComponents`, `OperationalRiskComponents` — each with
   `__post_init__` validation matching the existing
   `CapitalComponents` / `LiquidityComponents` style (negative-value
   rejection, division-by-zero protection, semantic invariants
   like "provisions cannot exceed Stage 3").
3. **4 new threshold class constants** added on the engine:
   `NPL_RATIO_MAX_PCT = 0.10`,
   `IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1 = 0.15`,
   `OPR_ALPHA = 0.15` (Basel II Standardised Approach alpha),
   `OPR_RWA_SHARE_MAX_PCT = 0.25`.
4. **3 new generator methods** added: `generate_npl`, `generate_irr`,
   `generate_opr` — each composes its inputs, computes the
   regulator-relevant ratio, classifies severity via the existing
   `_classify_severity` helper (NONE / MARGINAL / BREACH /
   SEVERE_BREACH), and returns a `CbkReturnPackage` with full
   `computed_metrics` + `inputs_used` + `framework_refs` per Rule 1
   provenance discipline.

### Engine API consistency

Every new generator follows the existing 5-return contract exactly:

```python
package = engine.generate_<code>(<components>)
package.return_code            # → CbkReturnCode.NPL/IRR/OPR
package.computed_metrics       # → Dict[str, Decimal] with the ratio + composites
package.threshold              # → the regulator threshold (Decimal)
package.threshold_direction    # → "min" or "max"
package.breach_severity        # → BreachSeverity enum
package.breach_description     # → human-readable summary
package.inputs_used            # → Dict[str, str] for full audit
package.framework_refs         # → tuple of citations (CBK + Basel II)
```

The engine remains diagnostic-only per Rule 7: it computes ratios
and classifies breaches but never serialises XBRL/XML/CSV, never
submits to the CBK portal, never auto-corrects breaches, and never
modifies balances. These remain the caller's responsibility.

### Tests

7 new self-tests added to the module's existing 17:

- `_test_npl_passing` — 8% NPL ratio → NONE
- `_test_npl_breach` — 15% NPL ratio → SEVERE_BREACH; coverage 40%
- `_test_npl_validates_provisions_exceed_stage3` — input validation
- `_test_irr_passing` — Δ EVE 8% of Tier 1 → NONE
- `_test_irr_breach` — Δ EVE 28% of Tier 1 → SEVERE_BREACH
- `_test_opr_passing` — OPR-RWA share 22.5% → NONE; charge 1.8B
- `_test_opr_excludes_negative_year` — Basel II §651 zero-year
  exclusion verified (denominator is 2 not 3)

```
$ python utils/cbk_regulatory_reporting.py
✓ cbk_regulatory_reporting self-test passed (24 tests)
```

---

## Why this batch (honest reasoning)

Of the four platform-level deferrals carried forward, this was
picked because:

1. **It's regulatory-mandatory.** A Kenyan commercial bank cannot
   operate without filing these prudential returns. Every other
   deferral is internal infrastructure (PG migration), customer-
   reporting (FATCA/CRS), or UI polish (React SPA).
2. **The scope is bounded.** Each return is a self-contained
   compose-input + compute-ratio + classify-severity unit. No
   cross-engine wiring, no schema changes, no UI surface required.
3. **The pattern was already proven.** The 5 existing generators
   (CAR/LIQ/SBL/LXP/FXE) had the contract worked out. Adding 3
   more was extension, not invention.
4. **It was the smallest concrete commitment that closed a real
   gap.** "5/8 CBK reports" was a specific number that could go to
   "8/8" cleanly. Larger commitments (e.g., FATCA/CRS XML) would
   require schema-level work that doesn't fit a single batch.

---

## Audit ratchet

```
v10.192 (entering this release): 159/159 = 100% PASS
v10.193 (this release):           159/159 = 100% PASS
                                  no new gates
```

This is an engine-extension release. No new audit gate was added
for the same reason as v10.192: the engine's contract didn't change
(it's still the same `CbkReturnPackage` shape, the same severity
enum, the same diagnostic-only Rule 7 stance). The closure ratchets
G150-G159 continue to lock the 5 closed modules. A future batch
could add a G160 verifying every `CbkReturnCode` enum value has a
corresponding `generate_*` method, but doing so now would lock 8/8
without leaving room for future regulatory schedule additions.

---

## Files changed

```
utils/cbk_regulatory_reporting.py    (ENH-252 extended: +3 enums, +3 dataclasses, +3 generators, +4 thresholds, +7 tests)
CHANGELOG_v10.193.md                 (this file)
```

Single-file engine change. No page changes, no API changes, no
audit-script changes, no nav changes.

---

## How to apply

```bash
unzip -o a2z_v10.193_cbk_returns_extension.zip
python utils/cbk_regulatory_reporting.py    # → ✓ 24 tests pass
python scripts/audit.py                     # → 159/159 PASS (unchanged)
```

---

## Honest scope statement

This release is a **diagnostic-engine extension**. It does not:

- **Submit returns to the CBK portal.** Per Rule 7, the engine
  produces structured `CbkReturnPackage` objects; the caller is
  responsible for serialising to whatever format CBK currently
  accepts (XBRL, XML, CSV, or PDF) and submitting via the bank's
  own approved channel.
- **Auto-correct breaches.** When a return classifies as BREACH or
  SEVERE_BREACH, the engine reports the fact; the bank's risk and
  compliance teams take action.
- **Modify balances.** The engine reads the inputs supplied by the
  caller and computes ratios. It never writes back to general
  ledger, RWA tables, or the IFRS 9 staging tables.
- **Track filing history.** That's the responsibility of
  `pages/74_cbk_returns.py` (the CBK Returns Centre), which logs
  submission/on-time-status/findings and is unrelated to the
  diagnostic engine.
- **Cover all 47 prudential returns** mentioned in the CBK Returns
  Centre page. The 47-return universe includes operational
  schedules (BSD-1, BSD-2, weekly liquidity returns, monthly
  branch reports, etc.) that are tracking-only and don't have
  ratio-classification semantics. The 8 returns in this engine are
  the ones with computed ratios and breach thresholds.

---

## What's next (open candidates, not committed)

Of the four original platform-level deferrals:

- ~~CBK reports: 5/8~~ → **CBK reports: 8/8** ✓ (closed by this release)
- PG migration: 19/52 tables — internal infrastructure
- FATCA/CRS XML — regulatory but lower frequency
- React SPA / React Native — UI work

The next reasonable target depends on operational priorities at
Ecobank. If FATCA/CRS filings are due soon, that's the next
candidate. If multi-process state via PostgreSQL is blocking
production deployment, PG migration is the candidate. If neither
is urgent, the next module activation (Customer Behavioral
Intelligence has 5 of 12 standards with engines that exist but
aren't formally activated) is a smaller commitment.

No commitment is made by this release.
