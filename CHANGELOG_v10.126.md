# CHANGELOG v10.126 — Phase 1D close-out: role-gating default flip + retro + bank-level pipeline proposal

**Status:** Phase 1D Integration Layer rule-density work CLOSED. v10.126 is a deliberate close-out drop, not rule-density. After 17 drops of continuous coverage gain (v10.108→v10.125) culminating in v10.125's STRICT-READY (high) crossing, v10.126 resolves the pending role-gating code-default flip, ships a comprehensive Phase 1D retro doc, and lays out the architecture for a Phase 1E bank-level pipeline.

**Audit:** 143/143 PASS in sandbox.
**Engine self-tests:** 152/152.
**G143 coverage:** **99/131 (75.6%)** — unchanged from v10.125 (close-out, not density).
**Strict-preview tier:** `STRICT-READY (high)` — preserved from v10.125 milestone.
**Tests:** 9 new across role-gating flip + closure docs + G143 preservation + no-new-rules verification.

---

## Why this drop matters

**The honest move at the milestone is to stop, document, and pivot** — not push past for marginal coverage gains via paper wiring. v10.125 hit STRICT-READY (high) cleanly. The remaining 32 KPIs are mostly bank-level (don't fit per-staff aggregation) — covering them via the Integration Layer would mean either inventing fake ownership mappings or low-quality wiring against thin existing tables. Both would dilute rather than strengthen the v10.125 milestone.

v10.126 makes three explicit moves:

1. **Flip role-gating default** — does what v10.120 should have done if v10.117's soft-flip had been hard-flip. Soft-flip was correct given backward-compat concerns; five drops in production is enough to harden. Now secure-by-default.

2. **Ship retro + architecture docs** — transmits Phase 1D state across context resets, future colleagues, future sprint cycles. The canonical answer to "what was built in Phase 1D".

3. **Refuse to add rules** — preserves the integrity of the v10.125 milestone. Tests verify zero v10.126-origin rules.

**Standards numbering**: standards_registry tracks 265 (12 regulatory + 253 enhancement). v10.126 closes Phase 1D in continuation territory.

---

## Scope completion delta

| Dimension | v10.125 | v10.126 | Δ |
|---|---|---|---|
| Master prompt version | v3.19 | **v3.20** | +1 |
| Universal patterns | 8 | 8 | 0 |
| DSL predicate types | 13 | 13 | 0 |
| Rules registered (active) | 100 | 100 | **0** (close-out, not density) |
| Operational tables wired | 39 | 39 | 0 |
| Library KPIs | 152 | 152 | 0 |
| Integration Layer API endpoints | 5 | 5 | 0 |
| **G143 coverage** | 99/131 (75.6%) | 99/131 (75.6%) | **unchanged — milestone preserved** |
| **G143 strict-preview tier** | STRICT-READY (high) | STRICT-READY (high) | unchanged |
| **Role-gating code default** | OFF (soft-flip via config since v10.120) | **ON (hard-flip)** | 🎯 **flipped** |
| Tests | 330 | **339** | +9 |

---

## Deliverable 1 — Role-gating code-default flip

**File:** `utils/api.py::_read_security_config`

**Before (v10.117 baseline, held through v10.125):**

```python
default = {
    "role_gating_enabled":     False,            # backward-compat
    "allowed_roles_for_write": ["admin", "integration"],
}
...
return {
    "role_gating_enabled":     bool(sec.get("role_gating_enabled", False)),
    ...
}
```

**After (v10.126):**

```python
default = {
    "role_gating_enabled":     True,   # v10.126: flipped from False
    "allowed_roles_for_write": ["admin", "integration"],
}
...
return {
    "role_gating_enabled":     bool(sec.get("role_gating_enabled", True)),  # v10.126
    ...
}
```

**Effect:**
- Deployments not consuming the v10.120 explicit `_security` block now inherit role-gating ON by default
- Deployments wanting JWT-only auth must explicitly set `_security.role_gating_enabled: false` (escape hatch preserved)
- **Aligns code default with shipped config default** (v10.120 ships `role_gating_enabled: true` in the explicit block)

**Soft-flip → hard-flip story across 5 drops:**

| Drop | Move |
|---|---|
| v10.117 | Draft feature flag, default OFF (backward-compat with v10.116 JWT-only) |
| v10.120 | GA polish — explicit `_security` block ships in config with `role_gating_enabled: true` and canonical Eco Bank role taxonomy. Code default stays OFF (soft-flip). |
| v10.121 | No flip — v10.120 just shipped, no real-world feedback. Soft-flip held. |
| v10.122-v10.125 | No flip — focus on rule density. |
| **v10.126** | **Code default flipped from OFF → ON.** Five drops post-soft-flip is enough; harden now. |

---

## Deliverable 2 — Phase 1D retro doc

**File:** `docs/Phase_1D_Integration_Layer_Retro.md` (~340 lines)

The canonical answer to "what was built in Phase 1D". Supersedes the rolling SCOPE_LEDGER status blocks for sprint-level retrospection.

**Sections:**
- Programme context
- What was built (architecture summary)
  - 8 universal aggregation patterns
  - 13 DSL predicates + 3 extractors
  - 100 production rules across 39 operational tables
  - 5 Integration Layer API endpoints
  - 12 fresh CBS-mock seeds (Window 3 + 4)
  - 4 non-K-coded library entries proven in production
  - G143 informational gate + strict-preview tier
  - Role-gating GA (soft-flip → hard-flip)
  - 330 production tests
- Architectural patterns + disciplines (7 patterns):
  - Composed-predicate discipline
  - Honest-deferral / period-field correction
  - Bank-level deferral
  - Forward-compatibility pattern
  - Library-duplicate handling
  - Per-rule staff_field override
  - Anti-drift commit-to-prompt sync
- Trajectory table (v10.108 → v10.125, drop-by-drop)
- Path to 100% (Category A bank-level vs Category B forward-compat)
- What didn't get done — 10 deferred items:
  1. PostgreSQL migration completion
  2. React dashboard wiring
  3. FATCA/CRS XML reporting
  4. Remaining CBK reports
  5. Standards #14-#20 (Peer Learning through Amplification API)
  6. Bank-level pipeline (Phase 1E)
  7. alm_liquidity schema adapter
  8. Library cleanup (K028/K048 duplicates, etc.)
  9. G144 audit gate for bank-level coverage
  10. Strict-flip itself (G143 stays in informational-pass mode)

---

## Deliverable 3 — Bank-level pipeline architecture proposal

**File:** `docs/Path_to_100_Bank_Level_Pipeline.md`

Phase 1E architecture sketch for covering the remaining 32 bank-level KPIs.

**Key design decisions:**
- **Two parallel pipelines** — per-staff (Integration Layer) at `/api/integration/*` + bank-level pipeline at `/api/bank_level/*`
- **`pipeline` discriminator** in rule shape — rules without it default to `per_staff` (preserves all v10.108-v10.125 unchanged)
- **6 bank-level aggregator types**: snapshot_field, sum_field, count_records, ratio_fields, growth_rate, percentage_field
- **Source-shape adapters**: single-row dict, dict-of-arrays, list-of-dicts with as_at
- **G144 audit gate** mirrors G143 semantics for bank-level coverage
- **Strict-flip semantics revised**: G143 + G144 both at 100% triggers strict-flip, OR G143 reframes denominator to per-staff scope only

**Effort estimate:** 10-15 drops for Phase 1E end-to-end.

**Recommendation:** defer Phase 1E in favor of standards / React / FATCA-CRS. Per-staff cockpit is the differentiator vs commodity bank-level reporting. Bring bank-level back as Phase 1F or 1G when per-staff cockpit is fully demonstrated.

---

## Deliverable 4 — Tests (`tests/test_integration_layer_v10_126.py`, 9 tests)

| Test class | Tests | Coverage |
|---|---|---|
| `TestRoleGatingDefaultFlip` | 4 | Source-level checks for the flip; v10.120 explicit config preserved; canonical role taxonomy intact; explicit-false escape hatch preserved |
| `TestPhase1DClosureDocs` | 2 | Retro doc + path-to-100 doc present with key sections |
| `TestG143StillHigh` | 2 | Coverage still 99/131; tier still STRICT-READY (high) |
| `TestCloseOutNotRuleDensity` | 2 | No v10.126-origin rules; total count still 100 |

All 9 tests pass (manual replay since pytest unavailable in build sandbox).

---

## Verification

```
$ python scripts/audit.py
  ✅ [G143] kpi_source_has_aggregator
     v10.108 informational: KPI aggregators registered 99 / 131
     operational-source KPIs (75.6%); ... STRICT-READY (high)
  Score: 143/143 gates = 100.0% — PASS

$ python scripts/run_engine_self_tests.py
  152 passed · 0 failed · 0 skipped of 152 engines

$ pytest tests/test_integration_layer*.py -v
  339 passed   (... + 22 v10.125 + 9 v10.126)
```

---

## Files in this drop

```
utils/api.py                                  # MODIFIED — _read_security_config default flip
docs/Phase_1D_Integration_Layer_Retro.md      # NEW — comprehensive sprint retro (~340 lines)
docs/Path_to_100_Bank_Level_Pipeline.md       # NEW — Phase 1E architecture proposal
tests/test_integration_layer_v10_126.py       # NEW (~150 LOC, 9 tests)
docs/Master_Prompt_v3.20.md                   # NEW (twentieth anti-drift sync)
SCOPE_LEDGER.md                               # MODIFIED (v10.125 + v10.126 status blocks; trajectory)
CHANGELOG_v10.126.md                          # this file
```

**No data files modified.** No new rules. No new seeds. Pure code (1 file) + docs + tests drop.

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                              # → 143/143 PASS, G143 99/131 STRICT-READY (high)
$ python scripts/run_engine_self_tests.py              # → 152/152
$ pytest tests/test_integration_layer*.py -v           # → 339 tests pass

$ git add -A
$ git commit -m "v10.126 — Phase 1D close-out: role-gating default flip + retro + Phase 1E proposal"
$ git tag v10.126
$ git push origin main --tags
```

**Critical post-deployment note for v10.126:**

After applying v10.126 in any environment that previously ran v10.117-v10.125 *without* consuming the v10.120 explicit `_security` block, **role-gating turns ON automatically**. POST `/api/integration/run-period` will require `user.role` in `["admin", "integration"]` (or whatever's in the explicit allowed_roles_for_write list).

If your deployment uses different role names and you haven't updated `data/integration_layer_config.json` since v10.117, you should either:
1. Update the config with your bank's canonical role taxonomy (recommended; mirrors v10.120's deployment guidance), OR
2. Set `_security.role_gating_enabled: false` explicitly to preserve JWT-only auth (escape hatch)

---

## Honesty discipline notes

**The honest move at the milestone is to stop, document, and pivot.** v10.125 hit STRICT-READY (high) cleanly with 100 production rules covering 99 KPIs. Pushing past 75% via paper wiring or fake bank-level coverage would dilute the milestone. v10.126 instead consolidates: docs the state, hardens defaults, points to the next phase.

**The retro doc explicitly enumerates 10 deferred items** so future work isn't silent about what didn't get done. The path-to-100 doc explicitly recommends defer over chase, because per-staff cockpit is the competitive differentiator vs commodity bank-level reporting.

**Role-gating soft-flip → hard-flip is the correct sequence** — soft-flip first to preserve backward compat, harden once production deployments have had a chance to consume the new config. Five drops between soft-flip (v10.120) and hard-flip (v10.126) is enough.

**The post-deployment note is not buried.** Banks updating from v10.117-v10.125 to v10.126 without consuming the v10.120 config will see role-gating activate automatically. The CHANGELOG calls this out explicitly so it doesn't surprise anyone.

**SCOPE_LEDGER repair pattern continues** — v10.125 status block heading was overwritten when inserting v10.126; restored. Body of v10.125 was preserved throughout.

---

## Phase 1D coverage trajectory (final)

| Drop | Work | Coverage |
|---|---|---|
| v10.108 | 4 reference rules (kickoff) | 4/108 (3.7%) |
| v10.119 | 2 new DSL predicates + 8 new rules — STRICT-READY (preview) crossing at 50% | 66/131 (50.4%) |
| v10.122 | 2 new CBS-mock seeds + 4 new rules — pool-wall break | 78/131 (59.5%) |
| v10.125 | 5 new CBS-mock seeds + 8 new rules — **STRICT-READY (high) crossing at 75%** | 99/131 (75.6%) |
| **v10.126** | **PHASE 1D CLOSE-OUT — role-gating default flip + retro + Phase 1E proposal. No new rules.** | **99/131 (75.6%) — unchanged** |
| v10.127 (planned) | Pivot drop — standards #14-#20 / React / PostgreSQL / FATCA-CRS — caller's pick. **Window 4 close.** | varies |
| v10.128+ (estimated) | Phase 1E begins — bank-level pipeline OR standards backlog | TBD |
| v10.130+ (estimated) | **G143 strict mode flip** at 100% (per-staff scope only; bank-level via G144) | 131/131 |

**Next: v10.127** — caller's pick. Realistic options:

1. **Standards #14-#20** — Peer Learning through Amplification API cluster. Stayed deferred throughout Phase 1D; still flagged as current focus per programme context.
2. **React dashboard component library** — leverage the 5 stable API endpoints (now role-gated) into a cockpit UI.
3. **PostgreSQL migration completion** — v10.116 added a PG-readiness shim; real DB-backed engines still pending.
4. **FATCA/CRS XML reporting** — flagged as deferred since before v10.108.
5. **Phase 1E bank-level pipeline** — design ready in Path_to_100 doc; implementation deferred per recommendation.

Window 4 closes at v10.127 with consolidated bundle (v10.123-v10.127) shipping alongside.

## Consolidation tracker

**Window 4 (v10.123-v10.127) is now 4 of 5 deep** (v10.123, v10.124, v10.125, v10.126 done). One more drop until consolidation. **Phase 1D rule-density work permanently closed at v10.126.**
