# Changelog — v10.296 Phase 3 Arc 2: Treasury Live Cockpit

**Date:** 2026-05-11
**Phase:** 3 (second integration arc)
**Audit:** 187/187 gates PASS = 100.0%
**Tests:** 56/56 passing across 3 integration suites
**G162 Rebase:** 3986 → 3996 (+10 CBK) — page 110 description,
G187 audit gate text, and Tier 55 admin entry all reference CBK
Prudential Guidelines (LCR/NSFR minimums, IRRBB EAR/EVE limits,
Basel III capital adequacy as adopted by CBK).

---

## Summary

Second Phase 3 cockpit integration arc. Delivers the Treasury
equivalent of v10.295's CIMS live cockpit, but with **tighter
test discipline** per the Kaizen mantra:

1. **Tests written first** (TDD). 23 integration tests defined
   what `treasury_open_work` had to do BEFORE implementation
   existed. Red phase: 6 passing, 14 failing, 3 skipped. Green
   phase after implementation: 23/23 passing.

2. **New meta-test suite** that scans the filesystem and
   enforces Phase 3 discipline on EVERY current and future
   `*_live.py` page. 11 disciplines × 2 cockpits = 22 parametrized
   tests, plus 4 fixture-stability tests. Future cockpits inherit
   automatically.

3. **Real bugs caught by audit, not by demo.** Initial page 110
   used `Path("data/...").read_text()` directly — G2 (direct_io)
   caught this. Fixed by adding `treasury_liquidity_metrics`,
   `treasury_irrbb`, `treasury_capital_adequacy` to cockpit_read.

---

## Architecture observation

Treasury arc is structurally different from CIMS. CIMS engines
are record-registry-based (persistent JSON files of session
records, classifications, exceptions). Treasury engines are
**stateful in-memory compute engines**: callers feed positions
in via `register_deposit`, `register_hqla`, `add_inflow`, then
run computations (`run_lcr`, `run_nsfr`, `run_eve_sensitivity`)
that produce results, not records.

State for Treasury lives in **regulatory JSON files** that
external loaders populate (treasury_fx.json, irrbb.json,
liquidity_metrics.json, capital_adequacy.json) — these are
what CBK examiners would expect to see.

Implication: the cockpit pattern differs. CIMS cockpit shows
counts of open records. Treasury cockpit shows ratios computed
from JSON state plus breach status against regulatory limits.

This is documented in CHANGELOG_v10.296 so future arcs (Credit,
Compliance, Risk) can be evaluated against both patterns to pick
the right fit.

---

## What shipped

### `utils/cockpit_read.py` — extended

Added 4 new functions for Treasury:

- `treasury_open_work(data_dir)` — aggregates the Treasury work
  landscape into a single dict. Documented keys:
  `fx_positions_count`, `open_fx_deals`, `irrbb_breaches`,
  `lcr_pct`, `lcr_min_pct`, `lcr_breached`, `as_at`. Read-only;
  legacy-tolerant; handles malformed JSON gracefully.

- `treasury_liquidity_metrics(data_dir)` — safe loader for
  liquidity_metrics.json.

- `treasury_irrbb(data_dir)` — safe loader for irrbb.json.

- `treasury_capital_adequacy(data_dir)` — safe loader for
  capital_adequacy.json.

- Internal: `_safe_load_json(path)` helper.

Total cockpit_read public API: 13 functions (was 9 in v10.295).

### `pages/110_treasury_live.py` (NEW)

7-tab Treasury live cockpit at the G4 ceiling:

1. **Open work pulse** — 5 headline metrics (FX positions,
   open FX deals, IRRBB breaches, LCR with min threshold,
   read timestamp). Triage banners for LCR breach + IRRBB
   breach count.
2. **LCR & NSFR** — Liquidity ratios vs CBK minimum and
   internal target, with component breakdown when available.
3. **IRRBB scenarios** — All scenarios with EAR/EVE values
   and breach flags against CBK Prudential Guideline limits.
4. **FX positions** — Total records, breakdowns by currency /
   deal_type / status, recent rows.
5. **RWA & capital** — CET1/Tier1/Total capital ratios under
   Basel III as adopted by CBK.
6. **Cash forecast** — placeholder pending ENH-237 wire-up
   in a follow-on batch.
7. **Dashboard report** — Composed via
   `TreasuryDashboardEngine.generate_daily_treasury()`,
   showing engine wiring status. Currently 0 sections because
   upstream engines (ALM/Products/RWA/FTP/Forecast) aren't
   yet wired into the dashboard — this is the next Phase 3
   step for the Treasury arc.

All tabs use `@st.cache_data(ttl=10)` for live refresh.
Dashboard report tab uses `ttl=60` (heavier computation).
Manual `🔄 Refresh now` button clears cache and emits an
audit log event.

Uses `require_access("treasury_alm.treasury_live")` without
try/except swallow. Per Phase 3 standing rule.

### `scripts/audit.py` — G187 added

`gate_treasury_live_cockpit_integrated` locks the Treasury
cockpit discipline: page existence, hard require_access,
treasury_open_work API surface (with documented keys),
manifest entry at `treasury_alm.treasury_live`, TTL caching,
audit_log calls.

### `pages/_manifest.json` — page 110 registered

`department_primary: "treasury_alm"`,
`module_path: "treasury_alm.treasury_live"`, all 7 G160-required
fields present. Page count: 113 → 114.

### `pages/7_admin.py` — Tier 55 added

4 entries documenting the Treasury cockpit composers
(`treasury_open_work`, `treasury_liquidity_metrics`,
`treasury_irrbb`, `treasury_capital_adequacy`).

### `tests/integration/test_treasury_live_cockpit.py` (NEW)

23 integration tests organized into 8 sections:

1. **TreasuryDashboardEngine contract** — engine instantiable
   with no args, board_summary returns wired flags, ALM wiring
   reflected.
2. **JSON data loading** — real `treasury_fx.json`, `irrbb.json`,
   `liquidity_metrics.json` field contracts verified.
3. **Cockpit aggregator invariants** — well-formed dict shape,
   non-negative counts, missing-files tolerance, LCR breach
   detection (positive and negative cases), IRRBB breach count
   from synthetic data.
4. **Read-only guarantee** — file mtime and content unchanged
   after 5 cockpit calls.
5. **Edge cases & malformed input** — malformed JSON tolerated,
   extra fields forward-compat, legacy record shapes counted.
6. **Performance smoke** — 1000 FX records processed in < 1
   second.
7. **Page 110 manifest contract** — entry exists with right
   fields.
8. **API discipline** — pure dict return, idempotent calls.

All 23 PASS.

### `tests/integration/test_phase3_cockpit_discipline.py` (NEW)

Meta-test suite that scans `pages/*_live.py` at test time and
applies 11 discipline checks to each:

- No silent require_access try/except
- @st.cache_data(ttl=...) decorator present
- audit_log() called at least once
- Canonical imports only (no `utils.audit_log`, no
  `utils.access_helpers`)
- Tab count ≤ 7 (G4 ceiling)
- Manifest entry exists with all 7 fields
- module_path ends in `_live` (navigability)
- No direct filesystem reads (`Path("data/...")`,
  `.read_text()`, raw `open("data/...")`)
- cockpit_read public API stable (13 documented functions)
- cockpit_read helpers are pure reads (verified by calling
  with empty inputs and checking no tmp dir writes)
- Standing rules + backlog docs exist and are non-empty

11 per-cockpit checks × 2 cockpits (pages 109 + 110) = 22
parametrized tests, plus 4 fixture-stability tests = 22 total.
All pass.

Critical property: when a new `*_live.py` page lands, every
discipline check automatically applies to it. No future
cockpit can ship with the silent require_access swallow, no
TTL caching, or missing manifest description without these
tests failing.

### `data/audit_baselines.json` — G162 rebased

3986 → 3996 (+10 CBK) for v10.296 Treasury references in
page 110 description + G187 audit gate text + Tier 55 admin
entry.

---

## Test discipline upgrade (Kaizen)

v10.295 had 11 integration tests, all written after the
cockpit. v10.296 has:

- 23 Treasury cockpit tests (written BEFORE implementation,
  TDD red phase first)
- 22 meta-discipline tests (auto-applied to all current and
  future live cockpits)
- 11 CIMS cockpit tests retained from v10.295

Total: 56 integration tests across 3 suites, all passing.

The meta-test suite is the key Kaizen contribution: it codifies
the Phase 3 discipline in test form, so it can't drift. Without
it, "Phase 3 standing rules" lives only in a markdown doc that
developers might not read. With it, breaking a rule fails a
test before the audit even runs.

---

## Real issues caught during the build

1. **G2 direct_io violation** — initial page 110 used
   `Path("data/...").read_text()` directly in cache helpers.
   Fixed by routing through new `treasury_liquidity_metrics`,
   `treasury_irrbb`, `treasury_capital_adequacy` cockpit_read
   helpers. The test
   `test_no_direct_filesystem_reads[110_treasury_live.py]`
   now prevents this regression.

2. **G162 token surge** — page 110 + G187 + Tier 55 referenced
   CBK Prudential Guidelines 10 times across the three
   surfaces. Caught and rebased.

3. **Treasury vs CIMS architecture difference** — building this
   surfaced that the "record registry" pattern from CIMS doesn't
   fit Treasury's "compute engine + regulatory JSON" pattern.
   Documented in this changelog so future arc work picks the
   right pattern.

---

## Files changed

- `utils/cockpit_read.py` — 4 new functions, `_safe_load_json`
  helper
- `pages/110_treasury_live.py` — NEW (348 lines, 7 tabs)
- `pages/_manifest.json` — page 110 entry added
- `pages/7_admin.py` — Tier 55 added (4 entries)
- `scripts/audit.py` — G187 added and registered
- `data/audit_baselines.json` — G162 rebased to 3996
- `tests/integration/test_treasury_live_cockpit.py` — NEW
  (23 tests)
- `tests/integration/test_phase3_cockpit_discipline.py` — NEW
  (meta-test, 22 effective tests)
- `CHANGELOG_v10.296.md` — this file

---

## Audit results

```
Score: 187/187 gates = 100.0% — PASS
```

Including new G187 (Treasury cockpit lock) and tightened
G2 enforcement on the new cockpit.

---

## Platform state

- **Audit:** 187/187 gates green
- **Standards active:** 330/330 (no change)
- **Pages:** 114 (was 113, +1 page 110)
- **Tiers:** 55 (was 54, +1 Tier 55)
- **Gates:** G1-G187 (linear, no gaps)
- **Live cockpits:** 2 (CIMS, Treasury); G130 closed for both
  arcs
- **Integration test suites:** 3 (CIMS, Treasury, meta)
- **Integration tests passing:** 56/56
- **PG migration:** 48/79 tables (61%) — unchanged
- **API endpoints:** 192 across 19 modules — unchanged

---

## Next Phase 3 arc options

In rough order of leverage:

1. **Credit live cockpit.** Credit has 12 engines (#119-#130)
   and 1 cockpit page in scope. Likely pattern: Treasury-style
   (compute + JSON state) since credit decisions are
   computations, not record lifecycles.

2. **Compliance live cockpit.** CMS (#191-#200) is the natural
   target. Mix of patterns — KYC has record-registry shape
   (similar to CIMS), AML monitoring is more compute-heavy.

3. **CIMS field vocabulary harmonization (backlog B-001).**
   Without this, cross-engine joins miss real-world instructions
   that flow through capture as `COMPLAINT` but need SLA
   tracking as `DISPUTE_INVESTIGATION`. Pure cleanup, no new
   user-facing surface.

4. **Wire upstream engines into TreasuryDashboardEngine.**
   Currently the dashboard composes 0 sections because no
   upstream engine is wired. Wiring ALM/Products/RWA/FTP/
   Forecast would make tab 7 of the Treasury cockpit produce
   a real daily treasury pack.

5. **PG migration push** toward 75/79 (95%).

6. **API endpoint coverage expansion.**

The CIMS + Treasury pair has now validated **two distinct cockpit
patterns**. Future arcs should compress to ~1 batch since the
discipline is locked in tests and the two reference patterns are
documented.
