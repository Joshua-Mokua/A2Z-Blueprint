# CHANGELOG v10.269 — Phase 1E Charter (Bank-Level Pipeline planning batch)

**Date:** 2026-05-07
**Theme:** Opens the Phase 1E sub-campaign per the canonical
planning-doc-first pattern (v8.11 Living Doc plan, v8.13 IP Strategy
plan). Documents architecture, scope, sequence, acceptance criteria,
and honest scope-limits BEFORE any engine code is written.
**Audit gates: 163/163 PASS. Lines added: 291 (charter doc).**

## What v10.269 ships

`docs/Phase_1E_Bank_Level_Pipeline_Plan.md` — 291-line canonical
charter for the Phase 1E sub-campaign, structured as:

- Why this charter exists (closes Phase 1D retro's "Decision: defer
  Category A" for go-forward planning)
- Programme context
- Scope reconnaissance (live survey: 37 bank-level candidates across
  11 source files; 152 KPIs total; 100 covered by Phase 1D)
- Three structural shapes the engine must handle (flat-snapshot /
  nested-snapshot / list-of-records)
- Architecture diagram (`utils/bank_aggregator.py` + new rules JSON +
  new API endpoint + BSC engine wiring)
- 8-aggregator catalog (SNAPSHOT_FIELD, SNAPSHOT_PATH,
  RATIO_OF_FIELDS, GROWTH_RATE, SUM_LIST, COUNT_LIST, MEAN_LIST,
  PERIOD_FILTER_THEN_SUM)
- Honesty rules (5, inherited from Mandatory Standard #11)
- 10-item acceptance criteria (all-of, no partial closure)
- 7-batch sub-campaign sequence (v10.269 charter →
  v10.270 foundation → v10.271–v10.273 rules in 3 batches →
  v10.274 API+BSC → v10.275 G144 + retro)
- Explicit out-of-scope list (forecasting, branch-level, daily
  resolution, alerts, PG persistence, multi-tenant)
- 7 risks with mitigations
- 6 spirit statements
- 7 honest acknowledgements
- "What closing the standards arc looks like" section explaining the
  meaning of v10.275 closure

## Live scope reconnaissance results

Captured in the charter itself, but worth quoting here:

```
Total active KPIs:                     152
Phase 1D rules cover:                  100 (per-staff, all 8 patterns)
Bank-level candidates (CBS autofit):    37
Operational unwired (still per-staff):  15
Total to wire in Phase 1E:              37 (the 32 from retro + 5 added since)
```

The 32 from the Phase 1D retro grew to 37 because 5 KPIs were added
to the library after the v10.125 retro was written. The acceptance
criterion is updated to "all bank-level KPIs in the library at
closure time" rather than the historical 32.

## Why charter-first

The Phase 1D retro (`docs/Phase_1D_Integration_Layer_Retro.md`)
explicitly said:

> Building the bank-level pipeline is a Phase 1E concern — different
> design constraints, different test patterns, different semantics.
> It deserves its own sprint cycle, not bolted onto Phase 1D.

Bolting Phase 1E onto Phase 1D would have: (a) compromised the
per-staff engine's purity; (b) introduced silent dimensional drift
between staff and bank dimensions; (c) made the audit-locked G143
ratchet less meaningful. The charter locks these design decisions
before code is written so they cannot drift mid-sub-campaign.

## The 8-aggregator catalog (intentional symmetry with Phase 1D)

| Aggregator | Phase 1D analogue (per-staff) |
|---|---|
| SNAPSHOT_FIELD | (no analogue — per-staff doesn't have snapshot files) |
| SNAPSHOT_PATH | (no analogue) |
| RATIO_OF_FIELDS | RATIO (per-staff has the same name) |
| GROWTH_RATE | (no analogue — per-staff is point-in-time) |
| SUM_LIST | SUM |
| COUNT_LIST | COUNT |
| MEAN_LIST | TAT_FIELD / MEAN_FIELD |
| PERIOD_FILTER_THEN_SUM | (Phase 1D uses period filtering implicitly) |

8 aggregators (intentional — same count as Phase 1D's 8 universal
patterns). The naming preserves symmetry where the semantic is
identical (SUM, COUNT, MEAN, RATIO) and diverges where the shape
genuinely differs (SNAPSHOT_FIELD, GROWTH_RATE).

## Audit

```
Before: 163/163 PASS
After:  163/163 PASS (no engine changes, no gate count change)
G162:   3,663 holding at baseline (pure documentation)
G163:   GROWING (DDL 27→32, MIGRATORS 17→18) — unchanged from v10.268
```

Per the canonical planning-doc batch convention, no audit gate count
change. G144 (the bank-level coverage ratchet) ships with the
substantive engine work in v10.275.

## Files changed

```
docs/Phase_1E_Bank_Level_Pipeline_Plan.md   NEW  291 lines
```

Single-file batch. Pure documentation. Sets up the next 6 batches.

## Strategic context

This batch opens the THIRD significant sub-campaign of the v10.x
era:
- v10.193–v10.218: Discipline (cockpit absorption + tenant cleanup)
- v10.219–v10.260: Cleanup (PG migration sub-campaign + dotted-form
  rollout + ratchet trio)
- v10.261–v10.268: Feature work (CBK persistence layer)
- **v10.269+: Phase 1E (bank-level pipeline)**

The pattern is consistent: every major arc opens with a
planning/audit batch that locks design choices before code is
written. This prevents the "we're already coding, can't change the
direction now" trap that kills sub-campaigns mid-flight.

## Honest acknowledgements

1. **The charter is opinionated.** 8 aggregators is a design choice;
   a different team might choose 6 or 12. The 8-count matches Phase
   1D for symmetry.

2. **Scope reconnaissance is current.** New KPIs added to the
   library after this batch will be in scope at closure (acceptance
   criterion is "all bank-level KPIs in the library at closure" not
   "the 37 from this charter").

3. **The 7-batch estimate is honest.** Phase 1D retro estimated 5–8;
   this lands in the middle. If a rules batch hits friction the
   estimate could grow to 8 or 9; the discipline is to add the batch
   not skip the work.

4. **G144 is not yet shipped.** It's specified in the charter and
   ships with v10.275. Anyone reading audit output before v10.275
   will see 163 gates, not 164.

5. **66 consecutive clean batches at charter time** (v10.193 →
   v10.268). The streak is a discipline indicator, not a
   self-congratulation. v10.269 maintains it; v10.270+ batches will
   need to maintain it through code changes.

6. **No engine code in this batch.** v10.270 is the foundation
   batch. Reviewers who skim CHANGELOGs looking for "what shipped"
   will see only the planning doc; that's by design.

## What's next

v10.270 — Phase 1E foundation:
- `utils/bank_aggregator.py` engine module (~600 lines)
- 8 aggregator function implementations
- Self-tests for each aggregator
- `data/bank_aggregation_rules.json` empty-but-valid registry
- Optional: a single proof-of-pattern rule (K080 Tier 1 Capital from
  capital_adequacy.json) to validate the end-to-end shape

After v10.270, the engine is complete. v10.271–v10.273 fill in the
37 rules. v10.274 wires the API + BSC. v10.275 ships G144 + the
retrospective.

7 batches to closure. Charter shipped.
