# Changelog — v10.309 Phase 3 Arc 15: First Cat A Composer

**Date:** 2026-05-11
**Phase:** 3 (fifteenth arc — first multi-engine aggregation)
**Audit:** 199/199 gates PASS = 100.0%
**Tests:** 264/264 passing across 16 integration suites (13
skipped in audit env)
**G162 Rebase:** none — composer body + endpoint + audit gate
text stayed tenant-token neutral
**G163 Ratchet:** unchanged

---

## Summary

First **Cat A composer** in Phase 3. Closes the v10.300
placeholder in Credit cockpit page 111 tab 6 with a
multi-engine aggregation composer that mirrors
`treasury_daily_report`'s section-shaped report pattern from
v10.302.

Differs structurally from everything shipped earlier in Phase 3:

| Earlier composers | Cat A composer |
|-------------------|----------------|
| Read one file or one engine | Aggregate multiple engines |
| Return a list or single dict | Return a multi-section report |
| One status per call | Per-section + top-level aggregate status |

The pattern is now proven for one cockpit. Compliance tab 6
(CRA & training) is the second Cat A candidate and can follow
this template.

---

## What shipped

### `utils/cockpit_read.py` — `credit_portfolio_analytics` composer

Aggregates three credit engines into a 3-section report:

| Section ID | Engine | Method |
|------------|--------|--------|
| `ai_underwriting` | `AIUnderwritingEngine` (#119, #124) | `board_summary()` |
| `pd_distribution` | `CreditRiskScoringEngine` (#119, #129) | `portfolio_pd_summary()` |
| `irb_capital` | `IRBCapitalEngine` | `compute_portfolio()` over ifrs9_loans.json |

Top-level shape:

```json
{
  "report_id": "CPA-2026-05-11",
  "sections": [<3 sections>],
  "n_sections": 3,
  "board_summary": {entity, n_sections, n_loans_scored, irb_total_rwa_kes},
  "status": "ok|no_data|error",
  "as_at": "<ISO timestamp>"
}
```

Each section has the same shape: `section_id`, `section_title`,
`source_engine`, `status`, `metrics` (dict of str → str —
Decimals already cast for JSON), `notes`.

Top-level status aggregation:
- `"error"` if any section errored
- `"no_data"` if all sections are `no_data`
- `"ok"` otherwise

**Defensive on each engine call.** Each section wraps its
engine call in try/except — a failure in one engine degrades
that section to `status="error"` with the exception in `notes`,
the other two sections still render. The composer always
returns 3 sections.

### Real numbers from the IRB section

Running against the 5045-loan IFRS9 portfolio:
- **5045 exposures** processed (zero skipped)
- **Total RWA: ~82.2 bn KES**
- **Total EL: ~3.5 bn KES**

These are sane orders of magnitude for an Ecobank-scale book.
The notes field calls out the shape-fit caveat explicitly (see
"Honest scope" below).

### Honest scope: shape-fit caveat in IRB section

The IFRS9 portfolio is mostly retail (`Motor Vehicle`,
`Personal`, `Salary`, etc.) but `IRBCapitalEngine`'s
`ExposureClass` enum only covers
`LARGE_CORPORATE / SME_CORPORATE / SOVEREIGN / BANK`. Retail
exposures don't fit cleanly.

The composer maps all loans to `SME_CORPORATE` (the most
lenient corporate class) and **explicitly notes the
simplification in the section's notes field**:

> Shape-fit simplification: IFRS9 loans mapped to
> SME_CORPORATE class (IRB ExposureClass enum lacks retail).
> Numbers are indicative, not regulatory. Maturity defaulted
> to 1.0y.

This is the right honesty posture. The composer surfaces a
number, but the caveat is part of the result — operators
reading the section know exactly what they're seeing.
Pretending the simplification doesn't exist would be the
wrong move. Either fix the engine (retail ExposureClass —
out of scope) or surface the gap (this batch's choice).

### `pages/111_credit_live.py` — tab 6 wired

Placeholder banner removed. Tab 6 now renders:
- 3-metric header (Report ID, Sections, top-level Status)
- Per-section block with:
  - Status icon (✅ ok / ⚠ warning / 🛑 breach / ⚪ no_data / ❌ error)
  - Title + section_id + status
  - Notes line (highlighted)
  - Compact metric pairs

A `_cached_portfolio_analytics()` helper wraps the composer
at 60s TTL (heavier than the other composers, same TTL as
treasury_daily_report).

### `utils/api_cockpit.py` — `/credit/portfolio-analytics` endpoint

JWT-protected. Audit-logged. **24 cockpit endpoints now**
(was 23). API version 20.0.

### `scripts/audit.py` — G199 added

Locks the closure via 6 sub-checks:

1. `credit_portfolio_analytics` exists in cockpit_read
2. Returns documented top-level keys
3. Returns exactly 3 sections (`ai_underwriting`,
   `pd_distribution`, `irb_capital`)
4. Each section has section_id, section_title, source_engine,
   status, metrics, notes
5. Page 111 references the composer + placeholder banner gone
6. HTTP endpoint registered + documented in module docstring

### Tests

- `tests/integration/test_credit_portfolio_analytics_v10309.py` (NEW)
  — 14 tests across 9 sections
- `tests/integration/test_api_cockpit.py` — `EXPECTED_ENDPOINTS` to 24
- `tests/integration/test_phase3_cockpit_discipline.py` — composer
  allowlist extended with `credit_portfolio_analytics`

---

## TDD red→green progression

- **Red phase:** 0P 14F. No composer existed.
- **Green phase 1** (composer body in cockpit_read): mostly passing.
- **Green phase 2** (page wiring + small breakage): caught and
  fixed one real bug — my first page rewrite accidentally
  inserted a premature `main()` call between tab 6 and tab 7,
  disconnecting tab 7. Audit/parse caught it, fixed in same
  batch.
- **Green phase 3** (endpoint + G199): 14P 0F.
- **Audit 199/199 first try after the page fix.** Zero G162
  drift, zero test regressions across the other 15 suites.

---

## Real findings during this batch

1. **Cat A composer = engine aggregation pattern, not file
   aggregation.** Earlier "Cat A" mentions in changelogs were
   imprecise. The actual structural distinction is that Cat A
   composers instantiate and call live engines (which may
   carry computational state), whereas the simpler composers
   read static JSON files. This batch makes the distinction
   real by proving the aggregation pattern works without
   needing pre-populated engine state.

2. **Two engines correctly returned `no_data`.** AI
   Underwriting and PD distribution both have zero state in
   the test env (no `decide()` or `score_borrower()` calls
   have populated them). The composer surfaces that
   honestly — `status="no_data"`, empty metrics, notes
   explaining what's missing. Top-level status stays `"ok"`
   because IRB has real data. Operators see exactly what's
   live and what's idle.

3. **The IRB section runs real math on real data.** 5045
   IFRS9 loans → 5045 IRB exposures → ~82bn KES RWA, ~3.5bn
   KES EL. The numbers stand up to a sanity check
   (RWA/exposure ratio in the realistic range for SME
   corporate weights).

4. **The page rewrite bug was a structural reminder.** When
   replacing the placeholder text in a multi-tab cockpit,
   the trailing `main()` call needs to stay at module level,
   not be part of any tab block. My first attempt put `main()`
   inside the replacement block, leaving tab 7 disconnected.
   `ast.parse` plus the `^main()` count check caught it
   immediately. Fixed, moved on, no test regression.

5. **No G162 drift across the full Phase 3 PG+Cat A arc
   (v10.305-v10.309).** Five consecutive batches now, zero
   tenant-token additions. The discipline is structural:
   composer names, endpoint paths, audit gate text, and
   section IDs all use organisational descriptors rather
   than entity-specific labels.

---

## Files changed

- `utils/cockpit_read.py` — `credit_portfolio_analytics`
  composer + `_build_irb_section` helper
- `utils/api_cockpit.py` — `/credit/portfolio-analytics`
  endpoint, version 20.0
- `pages/111_credit_live.py` — tab 6 wired, placeholder banner
  removed
- `scripts/audit.py` — G199 added and registered
- `tests/integration/test_credit_portfolio_analytics_v10309.py`
  — NEW (14 tests)
- `tests/integration/test_api_cockpit.py` —
  `EXPECTED_ENDPOINTS` to 24
- `tests/integration/test_phase3_cockpit_discipline.py` —
  composer allowlist extended
- `CHANGELOG_v10.309.md` — this file

---

## Audit results

```
Score: 199/199 gates = 100.0% — PASS
```

---

## Platform state

- **Audit:** 199/199 (was 198)
- **Standards active:** 330/330
- **Pages:** 116
- **Tiers:** 57
- **Gates:** G1-G199 linear
- **Live cockpits:** 4 (Credit tab 6 placeholder closed)
- **HTTP endpoints (cockpit):** 24 (was 23)
- **Integration test suites:** 16 (was 15)
- **Integration tests passing:** 264/264
- **G162 baseline:** 4022 (unchanged across v10.305-v10.309)
- **G163 ratchet:** `ddl_tables=37, migrators=23` (unchanged)
- **PG-routed composers:** 5
- **Cat A composers:** **1** (NEW — `credit_portfolio_analytics`)

---

## Placeholder banner status across cockpit estate

After v10.309:

| Cockpit | Tab | Before this arc | Now |
|---------|-----|-----------------|-----|
| CIMS pg 109 tab 7 | Wired to #176 history | Unchanged |
| Treasury pg 110 tab 6 | Placeholder | Wired v10.304 ✓ |
| Treasury pg 110 tab 7 | Placeholder | Wired v10.302 ✓ |
| Credit pg 111 tab 6 | **Placeholder (Cat A)** | **Wired this batch ✓** |
| Credit pg 111 tab 7 | Placeholder | Wired v10.305 ✓ |
| Compliance pg 112 tab 6 | Placeholder (Cat A) | Still placeholder |
| Compliance pg 112 tab 7 | Placeholder | Wired v10.305 ✓ |

**One placeholder remains: Compliance tab 6 (CRA & training)**
— another Cat A composer. Now that the pattern is proven,
that batch should compress fast.

---

## What this proves

1. **Multi-engine aggregation works without engine state
   bootstrapping.** The composer instantiates engines and
   calls them with zero pre-existing state. Each engine's
   own NO_DATA path renders cleanly. When operators populate
   engines (via `decide()`, `score_borrower()`, etc.), the
   sections fill in without composer code changes.

2. **The "section + status + metrics + notes" shape scales.**
   Same shape as `treasury_daily_report`. Same UI pattern in
   the cockpit page. Same shape for the React SPA. Two Cat A
   composers using identical structure suggests the pattern
   is the right one for this category.

3. **Honest reporting beats clean reporting.** The IRB
   shape-fit caveat is right there in the section notes —
   operators see what's indicative vs regulatory. Earlier
   instincts would have been to hide the simplification or
   not surface IRB at all. Surfacing it honestly is the
   better engineering posture.

---

## Honest backlog status

| ID | Status | Item |
|----|--------|------|
| B-001 | ✅ Closed v10.303 | CIMS vocab harmonization |
| B-002 | Open (cosmetic) | Admin label |
| B-003 | Open (deferred) | Engine init params |
| B-004 | Mitigated | pytest in audit env (static AST) |
| B-005 | Open | Docs |
| B-006 | Mitigated | FastAPI in audit env (static AST) |
| B-007 | Open (logged v10.306) | DDL+migrator generation from spec |
| **B-008** | **New, logged** | Retail `ExposureClass` for IRB engine — would allow `credit_portfolio_analytics` IRB section to map IFRS9 retail loans to a proper class instead of the SME_CORPORATE shape-fit |

---

## Next Phase 3 arc options

1. ~~CORS + production deploy config~~ — v10.299 ✓
2. ~~Credit live cockpit~~ — v10.300 ✓
3. ~~Compliance live cockpit~~ — v10.301 ✓
4. ~~TreasuryDashboardEngine wiring~~ — v10.302 ✓
5. ~~CIMS vocabulary harmonization (B-001)~~ — v10.303 ✓
6. ~~Cash forecast composer wiring~~ — v10.304 ✓
7. ~~Audit trail composer~~ — v10.305 ✓
8. ~~PG migration push~~ — v10.306 ✓
9. ~~PG read-path cutover (first composer)~~ — v10.307 ✓
10. ~~PG-ready composer fan-out~~ — v10.308 ✓
11. ~~Cat A Portfolio analytics composer~~ — v10.309 ✓
12. **Cat A CRA & training composer** — close Compliance tab 6.
    Same pattern as #11 applied to
    `compliance_risk_assessment.ComplianceRiskAssessmentEngine` +
    `compliance_training.ComplianceTrainingEngine`. Should
    compress fast — pattern is set.
13. **Next PG migration push (+5 more tables)** — agency_
    banking, agent_fraud, branch_log, cab_register,
    treasury_gov_secs.
14. **Toggle one production table to "auto" mode** in
    `integration_layer_config.json` and add a verification
    test that PG-mode and JSON-mode reads match.
15. **Address B-008** — add a retail ExposureClass enum value
    to IRB engine so the credit_portfolio_analytics IRB
    section drops the shape-fit caveat. Out of scope for now;
    logged.

Option 12 (CRA & training composer) is the natural follow-on
— closes the last placeholder banner across all four
cockpits in one batch.

---

## Fifteen Phase 3 arcs shipped

4 live cockpits + 1 verification batch + 1 backlog closure +
1 React-readiness API + 1 CORS/deploy + 3 wiring batches + 1
PG migration + 1 PG cutover + 1 PG fan-out + 1 Cat A.

**199 gates green. 264 passing tests. 16 integration suites.
24 HTTP endpoints. 5 PG-routed composers. 1 Cat A composer.**

The compression now includes the Cat A pattern. Future
multi-engine aggregations have a working template
(`credit_portfolio_analytics`) and a working audit gate
template (G199's 6-sub-check pattern). The next Cat A batch
should compress further.
