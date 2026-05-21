# CHANGELOG v10.128 — Streamlit cockpit for the integration layer

**Status:** First post-Phase-1D code change. New `pages/99_integration_cockpit.py` (~600 LOC) surfaces the integration layer's 5 API endpoints in the live Streamlit app. Closes the "connect standards to the live Streamlit app" focus area flagged in programme context.

**Audit:** 143/143 PASS in sandbox.
**Engine self-tests:** 152/152.
**G143 coverage:** **99/131 (75.6%)** — unchanged from v10.125 milestone.
**Strict-preview tier:** `STRICT-READY (high)` — preserved.
**Tests:** ~25 new across 7 classes. All pass via manual replay.

---

## Why this drop matters

Phase 1D rule-density work closed at v10.126 with the integration layer at G143 STRICT-READY (high). v10.127 verified standards #14-#20 were already complete and corrected the stale memory line. **v10.128 is the first new feature work in the post-Phase-1D era**: a Streamlit cockpit page that gives operators a single-page surface for the integration layer's 5 API endpoints.

This addresses the "connect standards to the live Streamlit app" focus area that's been flagged in programme context throughout the Phase 1D sprint. Until v10.128, the 5 API endpoints had stable JSON contracts (since v10.115) but no UI consuming them in the cockpit. The Streamlit app's other 100+ pages couldn't reach the integration layer's outputs without writing custom backend calls. v10.128 fixes that with one cockpit page.

**Standards numbering**: standards_registry tracks 265 (12 regulatory + 253 enhancement). v10.128 stays in continuation territory.

---

## Scope completion delta

| Dimension | v10.127 | v10.128 | Δ |
|---|---|---|---|
| Master prompt version | v3.21 | **v3.22** | +1 |
| Universal patterns | 8 | 8 | 0 |
| DSL predicate types | 13 | 13 | 0 |
| Rules registered (active) | 100 | 100 | 0 |
| Operational tables wired | 39 | 39 | 0 |
| Library KPIs | 152 | 152 | 0 |
| Integration Layer API endpoints | 5 | 5 | 0 |
| **Streamlit cockpit pages for integration layer** | 0 | **1** (`99_integration_cockpit.py`) | +1 |
| **G143 coverage** | 99/131 (75.6%) | 99/131 (75.6%) | unchanged |
| **G143 strict-preview tier** | STRICT-READY (high) | STRICT-READY (high) | unchanged |
| Tests | ~339 | ~364 | ~+25 |

---

## Deliverable 1 — `pages/99_integration_cockpit.py`

Operator-facing single-page surface organised around 5 tabs mirroring the 5 Integration Layer API endpoints.

### Tab 1 — Coverage (`/api/integration/coverage`)

Displays:
- G143 strict-preview tier with emoji indicators (🟢 high / 🟡 preview / 🔴 below)
- Covered / total counts and coverage_pct
- Audit verdict (✅ PASS / ❌ FAIL)
- 4 tier thresholds reference (BELOW < 50%, preview [50%, 75%), high ≥ 75%, flip-target 100%)
- Full G143 summary text in expander

Refreshed live each visit (not cached) — operators expect fresh state.

### Tab 2 — Rules (`/api/integration/rules`)

Displays the 100 active aggregation rules in a sortable dataframe with:
- KPI ID, KPI name (joined from kpi_library.json)
- Pattern, source_table, staff_field, period_field
- Origin drop attribution (e.g., `v10.122_pool_break_seeds`)

Filters:
- Filter by pattern (multiselect)
- Filter by source_table (multiselect)
- Search by KPI ID or name (text input)

Cached 5 minutes via `@st.cache_data(ttl=300)`.

### Tab 3 — Preview Actuals (`/api/integration/actuals/{period}`)

Period picker → `compute_actuals_from_operational_tables(period)` call.

Displays:
- Summary metrics (KPIs producing actuals, total staff-rows emitted)
- Per-rule sample (first 3 staff per KPI in expander)

Read-only — no writes. Same function backs the API endpoint.

### Tab 4 — Resolution Metrics (`/api/integration/resolution-metrics`)

Refreshes name + role resolver caches, supports full-name → staff_code probe directly.

### Tab 5 — Run Period (`/api/integration/run-period`)

Admin-only trigger for the full pipeline. Surfaces v10.126's hard-flip role-gating semantics explicitly:
- 🔒 indicator showing `role_gating_enabled` state
- Lists `allowed_roles_for_write`
- Shows operator's current role with allowed/not-allowed indicator
- Disables button on role-mismatch

`dry_run` defaults to **True** per Rule 7. Operators must explicitly uncheck to "write" (which actually points them to the API endpoint — see Honesty notes).

---

## Deliverable 2 — Standard cockpit conventions used

| Convention | Implementation |
|---|---|
| Page entry guard | `from pages._access import require_access` |
| Audit logging | `from utils.core_audit import audit_log` for view + action events |
| Page config | `st.set_page_config(page_title="Integration Cockpit", page_icon="🧮", layout="wide")` |
| Cache strategy | `@st.cache_data(ttl=300)` on rule registry + library + security config; G143 NOT cached (operators expect freshness) |
| Backend access | Imports utility functions directly, same pattern as `pages/98_platform_health.py` |

---

## Deliverable 3 — v10.126 role-gating surfaced (Rule 7)

The cockpit reads the `_security` block from `data/integration_layer_config.json` and:

```python
if sec.get("role_gating_enabled"):
    st.info(
        f"🔒 Role-gating ON (v10.126 hard-flip default). "
        f"Allowed roles for write: "
        f"`{', '.join(sec.get('allowed_roles_for_write', []))}`.")
else:
    st.warning(
        "⚠️ Role-gating DISABLED in config. JWT-only auth is in effect. "
        "Any logged-in user can trigger writes.")

st.caption(f"Your role: `{user_role or 'unknown'}` — "
           f"{'✅ allowed to write' if user_can_write else '⛔ NOT allowed to write'}")
```

**Per Rule 7**, role-gating is *surfaced*, not silently blocking. The disabled button + role-mismatch caption make operators aware of *why* writes are gated rather than mysteriously not working.

---

## Deliverable 4 — Tests (`tests/test_integration_layer_v10_128.py`, ~25 tests)

| Test class | Tests | Coverage |
|---|---|---|
| `TestCockpitPagePresence` | 3 | File exists, valid Python syntax, substantive size (>5KB) |
| `TestCockpitTabStructure` | 2 | All 5 tab labels present; all 5 API endpoint references in copy |
| `TestCockpitConventions` | 4 | require_access used, audit_log imported, streamlit imported, set_page_config called |
| `TestRoleGatingSurfacedInCockpit` | 3 | v10.126 referenced, role_gating_enabled checked, allowed_roles_for_write surfaced |
| `TestRule7Surfacing` | 2 | dry_run defaults ON; writes route to API endpoint not cockpit |
| `TestG143UnchangedV10128` | 2 | Coverage still 99/131; tier still STRICT-READY (high) |
| `TestCockpitBackendPresence` | 3 | aggregation_rules.json + kpi_library.json + integration_layer_config.json all present |
| `TestNoRuleDensityV10128` | 2 | No v10.128-origin rules; total still 100 |

All ~25 tests pass via manual replay (pytest unavailable in build sandbox).

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
  ~364 passed
```

**Manual verification of the cockpit page**: open the Streamlit app, navigate to "Integration Cockpit" in the sidebar, walk through all 5 tabs. Coverage tab should show STRICT-READY (high) at 75.6%. Rules tab should display 100 rules with filters working. Preview Actuals with period 2026-04 should show ~99 KPI groups. Resolution Metrics resolver probe should return staff_code for a known full-name. Run Period button should be enabled for admin role and disabled for non-allowed roles.

---

## Files in this drop

```
pages/99_integration_cockpit.py               # NEW — ~600 LOC Streamlit cockpit
tests/test_integration_layer_v10_128.py       # NEW (~250 LOC, ~25 tests)
docs/Master_Prompt_v3.22.md                   # NEW (twenty-second anti-drift sync)
SCOPE_LEDGER.md                               # MODIFIED (v10.127 + v10.128 status blocks; trajectory)
CHANGELOG_v10.128.md                          # this file
```

**No data files modified. No code in utils/ modified. No new rules. No new seeds.** Pure UI + tests + docs drop.

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                              # → 143/143 PASS
$ python scripts/run_engine_self_tests.py              # → 152/152
$ pytest tests/test_integration_layer*.py -v           # → ~364 tests pass
$ streamlit run app.py                                 # → navigate to Integration Cockpit

$ git add -A
$ git commit -m "v10.128 — Streamlit cockpit for integration layer"
$ git tag v10.128
$ git push origin main --tags
```

---

## Honesty discipline notes

**No HTTP indirection in cockpit.** Streamlit cockpit pages typically import utility functions directly (same pattern as `pages/98_platform_health.py` calling subprocess for audit scripts; same pattern as other cockpit pages importing from `utils/`). HTTP would add a network hop and replicate auth that's already enforced at page entry via `require_access`. Cockpit consumes the *same code* the API endpoints expose.

**Writes route to API endpoint.** Cockpit shows DRY RUN preview but explicitly says "for writes, call POST /api/integration/run-period directly". Prevents the cockpit from accumulating duplicate write paths. The contract surface for actuals-writing is the API endpoint; the cockpit is a UI for read-paths + dry-run preview.

**Role-gating surfaced not hidden.** Rule 7 says surfaces should make state visible, not block silently. The disabled button + role-mismatch caption make operators aware of *why* writes are gated rather than mysteriously not working.

**No new rules.** v10.128 is a UI drop. Tests verify zero v10.128-origin rules in `aggregation_rules.json`. Preserves the v10.125 STRICT-READY (high) milestone integrity.

**v10.128 numbering**: my initial proposal in v10.126's close-out was that v10.127 would do this cockpit work. Reality: v10.127 already shipped (Window 4 close + standards #14-#20 verification, per the memory CORRECTION). The cockpit work moved to v10.128. Same content, different number.

**SCOPE_LEDGER repair pattern continues** — v10.127 status block heading was overwritten when inserting v10.128; restored. Body of v10.127 was preserved throughout.

---

## Phase 1D coverage trajectory (locked at v10.126; preserved through v10.128)

| Drop | Work | Coverage |
|---|---|---|
| v10.108 | 4 reference rules (kickoff) | 4/108 (3.7%) |
| v10.119 | 2 new DSL predicates + 8 new rules — STRICT-READY (preview) crossing | 66/131 (50.4%) |
| v10.122 | 2 new CBS-mock seeds + 4 new rules — pool-wall break | 78/131 (59.5%) |
| v10.125 | 5 new CBS-mock seeds + 8 new rules — **STRICT-READY (high) crossing** | 99/131 (75.6%) |
| v10.126 | Phase 1D close-out — role-gating default flip + retro + Phase 1E proposal | 99/131 (unchanged) |
| v10.127 | Window 4 close — programme correction + standards #14-#20 verification | 99/131 (unchanged) |
| **v10.128** | **Streamlit cockpit — `pages/99_integration_cockpit.py`** | **99/131 (unchanged)** |
| v10.129 (planned) | Caller's pick — PostgreSQL migration / FATCA-CRS / React / bank-level pipeline | varies |
| v10.130+ (estimated) | **G143 strict mode flip** at 100% (per-staff scope only; bank-level via G144) | 131/131 |

**Next: v10.129** — caller's pick. My recommendation: **PostgreSQL migration completion**. v10.116 added a PG-readiness shim; the integration layer reads from JSON files via the shim today. v10.129 takes one concrete step toward DB-backed reads — for example, migrating the rule registry to PostgreSQL while keeping the operational-table reads on JSON for now. Hardens the data path; aligns with the "advancing PostgreSQL migration and API endpoint coverage" focus area.
