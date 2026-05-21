# CHANGELOG v10.96 — Phase 1B CLOSED (147/136 endpoints, 108.1%)

**Status:** Phase 1B close-out. API endpoint coverage hits **147/136 (108.1%)** — 11 endpoints above target with operational-priority cushion. Phase 1B is closed; v10.97 begins Phase 1C (test coverage push).

**Audit:** 142/142 PASS (unchanged)
**Engine self-tests:** 152/152 (unchanged)
**Migration consistency:** 40/40 FLAT_MIGRATIONS entries verified clean

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.96 | After v10.96 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| **API endpoints** | 123 / 136 (90.4%) | **147 / 136 (108.1%)** | **+24** |
| CRUD factory modules | 13 | **16** | +3 |

**No new research_addition standards in this drop.** Maintenance close-out; continuation_doc count held at floor.

---

## Phase 1B: COMPLETE

The original 136-endpoint target set at project start is exceeded with cushion. **Final composition:**

- **19 direct decorators** in `utils/api.py`, `utils/auth_jwt.py`, `utils/performance_insights.py` — domain-specific computed endpoints (auth, BSC summary, pipeline summary, dashboard rollups, performance insights)
- **128 CRUD endpoints** = 16 modules × 8 verbs (list/get/create/update/delete/export/search/dashboard) — generic data access for high-value operational tables

**Total: 147 endpoints (108.1% of 136 target).**

The 11-endpoint cushion is fine. The candidates wired in the last 4 drops (v10.93-v10.96) are all genuinely useful operational tables — IFRS 9 ECL, agent transactions, debt recovery, customer instructions, compliance cases, referrals, DPO consent, revenue leakage, document management, clearing settlements. None are ceremonial.

---

## What landed (in order)

### 1. Substituted candidates after composite-PK pre-flight

The v10.95 plan named `staff_history`, `revenue_assurance`, `edms_documents` for v10.96. Pre-flight check found:

- `staff_history` has no `id` field — uses composite key `(staff_code, effective_date)` per the v10.90 schema design
- `commission_records` (alternate candidate) has same issue — composite key `(staff_code, period)`

The factory's `pk_column` parameter only supports a single column. Composite-PK tables don't fit the CRUD factory cleanly because `GET /{module}/{id}` semantics require a single ID to identify a row.

Substituted `clearing_records` (clean — has `id` field). Final v10.96 batch: **revenue_assurance, edms_documents, clearing_records**.

The composite-PK tables (`staff_history`, `commission_records`) are documented in SCOPE_LEDGER as "tables NOT wired as CRUD: composite primary keys; factory pattern requires single PK column. Wire via direct decorators if needed."

### 2. 3 new CRUD modules (+24 endpoints) — Phase 1B close

| Module | Records | Searchable | Order by | Why this priority |
|---|---|---|---|---|
| `revenue_assurance` | 300 | status, type, fee_type, period, branch, recovered, client_cif | date_raised DESC | revenue_assurance arc data (arc closed at G133+G134); status + type drive triage; period enables trend analytics |
| `edms_documents` | 500 | status, category, document_type, client_cif, branch, is_expired, requires_review, access_level | uploaded_date DESC | Document management; used by compliance + legal arcs; 500 records is largest among remaining candidates |
| `clearing_records` | 120 | status, system, reconciled, currency, settlement_tat_met, officer_username | value_date DESC | Clearing house settlement; status segments workflow (Pending/Settled/Failed/Reversed); reconciled flags need-attention items |

For `edms_documents`, the 8-column searchable whitelist is the largest in any module — reflecting that document management has many filter dimensions. For `clearing_records`, `settlement_tat_met` is the operational SLA filter.

### 3. SCOPE_LEDGER.md Phase 1B section finalized

Updated table shows the full v10.92→v10.96 progression. Phase 1B section declares **STATUS: COMPLETE**. The "tables NOT wired as CRUD" section explicitly documents the 3 categories:
- Composite-PK tables (staff_history, commission_records)
- Subcategory-not-active tables (bnc_policies, treasury_fx, treasury_fd, trade_finance)
- Lower-priority operational data (bid_bonds, agents_data, agent_fraud_alerts)

Phase 1C section updated with kickoff plan: baseline coverage measurement first, then parameterized CRUD smoke tests against the 16 wired modules.

---

## Composite-PK tables: future direct-decorator candidates

`staff_history` and `commission_records` aren't in the CRUD set, but they're operationally important and PG-ready. When their workflows need API access, the right pattern is:

```python
# Read-only list/get with composite identification
@app.get("/api/v1/staff_history/{staff_code}")
def staff_history_for(staff_code: str, user=Depends(get_current_user)):
    # Returns all movement records for one staff member
    ...

@app.get("/api/v1/commission_records/{staff_code}/{period}")
def commission_record(staff_code: str, period: str, user=Depends(get_current_user)):
    # Returns single record by composite key
    ...
```

These can be added in v10.97+ if specific consumers need them. They count as direct decorators (not CRUD), so they don't change the CRUD module count but contribute to the direct-decorator count.

---

## What v10.97 covers — Phase 1C kickoff

Phase 1C: test coverage push from ~45% → 80%.

**First action: baseline coverage measurement.** Run `coverage.py` against the existing test suite. The result tells us:
- Which modules are well-covered (likely the closed-arc engines from v10.46-v10.86 — they all have self-tests)
- Which modules are under-covered (likely api.py, api_crud.py despite the factory tests, plus utils/db.py migration paths)
- Where the easiest 10-percentage-point gains live

**Second action: parameterized CRUD smoke test.** With 16 wired modules, a single parameterized test can validate basic CRUD operations against each module's real table:

```python
@pytest.mark.parametrize("module,table,json_file", CRUD_MODULES)
def test_crud_list(module, table, json_file):
    response = client.get(f"/api/v1/{module}", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

That's 16 tests in one fixture — high signal-to-effort ratio.

**Third action onwards: targeted module tests.** Whichever modules have the worst coverage scores get focused testing in subsequent drops. Estimated 5-10 drops total to reach 80%.

After Phase 1C closes (~v10.106), Phase 1 is fully closed. Phase 2 begins — activating the 11 untouched planned subcategories (customer_360 first per ledger sequence).

---

## Files changed

- **MOD** `utils/api.py` (3 new `make_crud_router()` calls — final Phase 1B batch)
- **MOD** `SCOPE_LEDGER.md` (Phase 1B declared COMPLETE; final progression table; tables-NOT-wired explicitly documented; Phase 1C kickoff plan)
- **NEW** `CHANGELOG_v10.96.md` (this file)

## Files NOT changed (deliberately)

- `utils/db.py` — no schema or TABLE_USE_DB changes
- `scripts/audit.py` — G16 still passes (CRUD coverage), G142 still locks the floor
- `scripts/audit_completion_state.py` — methodology from v10.92 still produces correct counts
- `scripts/migrate_to_postgres.py` — Phase 1A frozen
- `standards_registry.py` — no new standards
- `utils/api_crud.py` — factory unchanged; just consumed by 3 more module calls
- All closed-arc files — closure invariants preserved

## Honest acknowledgements

**Phase 1B closing 11 endpoints above target is an artifact of the factory's 8-per-module shape.** I couldn't ship 1.6 modules to land exactly on 136. The choice was 13 modules → 123 (under) or 14 modules → 131 (under) or 16 modules → 147 (over). 16 was the right call because the 3 v10.96 modules are operationally useful (revenue_assurance, edms_documents, clearing_records), not filler. But the +11 cushion is structural, not a deliberate decision to "exceed by 8%."

**The composite-PK pre-flight catch was important.** If I'd wired `staff_history` without checking, the factory would have generated routes that semantically don't work — `GET /api/v1/staff_history/{id}` would have no clean implementation because there's no single ID column. Either the route would fail at request time, or the factory would silently use a non-PK column as the lookup. The pre-flight check prevented shipping broken endpoints. Lesson reinforces the v10.93 lesson: pre-flight before wiring, every drop.

**The 147/136 number isn't apples-to-apples with the original target.** The 136 target was set early in the project before the CRUD factory existed. It reflected a then-current view of "how many endpoints would the platform have when complete." Some of those original 136 may have been intended as direct decorators (specific computed endpoints), not as factory-generated CRUD verbs. The current 147 includes 128 from the factory; the 19 direct decorators are well below what the original plan likely envisioned for that category. This is fine — the platform's actual needs are met by the current mix — but the comparison isn't a perfect like-for-like.

**Tables NOT wired as CRUD aren't a problem.** The list (staff_history, commission_records, bnc_policies, treasury_fx, treasury_fd, trade_finance, bid_bonds, agents_data, agent_fraud_alerts) totals 9 tables. For each, there's an explicit reason — composite PK, subcategory not active, or low priority. None of these are accidentally-skipped tables. If a specific consumer needs API access to one of these, the right path is direct decorators (for composite-PK) or wiring CRUD when the surrounding subcategory work happens (for subcategory-not-active).

**Phase 1C is the longest remaining workstream.** PG migration (Phase 1A) closed in 4 drops over 4 sessions. API endpoints (Phase 1B) closed in 5 drops over 5 sessions. Test coverage (Phase 1C) is estimated at 5-10 drops because each percentage-point gain requires writing real tests against real code, not configuring a factory call. The first drop will likely be lower-velocity than v10.92-v10.96 because the baseline measurement + first parameterized test setup take longer than wiring 3 CRUD modules.

**v10.97 might NOT be a +24 cadence drop.** Test coverage drops have a different shape than CRUD wiring drops. The right metric for Phase 1C is "percentage points gained per drop," not "endpoints added." A drop that gains 8 percentage points (45% → 53%) is more valuable than a drop that gains 2 percentage points but adds 30 lines of code. Joshua should expect Phase 1C drops to feel different from Phase 1B drops.

---

**v10.96 ships under the anti-drift protocol.** Phase 1A COMPLETE (53/52 PG tables). Phase 1B COMPLETE (147/136 API endpoints). Phase 1C begins in v10.97 with baseline coverage measurement + parameterized CRUD smoke test.
