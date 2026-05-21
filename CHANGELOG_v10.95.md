# CHANGELOG v10.95 — Phase 1B continuation: 3 more CRUD modules

**Status:** Phase 1B continuation. Smooth execution drop. API endpoint coverage moves 99→123 (72.8%→90.4%). Phase 1B closes next drop (v10.96) above the 136 target.

**Audit:** 142/142 PASS (unchanged)
**Engine self-tests:** 152/152 (unchanged)
**Migration consistency:** 40/40 FLAT_MIGRATIONS entries verified clean

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.95 | After v10.95 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| **API endpoints** | 99 / 136 (72.8%) | **123 / 136 (90.4%)** | **+24** |
| CRUD factory modules | 10 | **13** | +3 |

**No new research_addition standards in this drop.** Maintenance work; continuation_doc count held at floor.

---

## What landed (in order)

### 1. Pre-flight check passed cleanly

The 3 v10.94-flagged candidates verified for all 4 prerequisites:

| Module | Source JSON | Schema | FLAT_MIGRATIONS | TABLE_USE_DB |
|---|---|---|---|---|
| compliance_cases | ✓ 115 records | ✓ | ✓ | True (flipped from False at v10.93) |
| referrals | ✓ 200 records | ✓ | ✓ | True (flipped from False at v10.93) |
| consent_register | ✓ 200 records | ✓ | ✓ | True (added at v10.93) |

Same green-pass shape as v10.94 — the v10.93 TABLE_USE_DB sync continues to pay off.

### 2. 3 new CRUD modules (+24 endpoints)

| Module | Records | Searchable | Order by | Why this priority |
|---|---|---|---|---|
| `compliance_cases` | 115 | status, risk_level, flag_type, client_cif, assigned_officer, case_type | raised_date DESC | Compliance arc tracking; risk_level + status drive operational triage; flag_type segments case taxonomy (Adverse Media, Sanctions Hit, PEP Match, etc.) |
| `referrals` | 200 | status, referral_source, converted, fee_paid, branch, rm_assigned, product_interested | referral_date DESC | Channel attribution analytics; referral_source segments Staff/Branch/Partner/MOU; converted + fee_paid surface operational state |
| `consent_register` | 200 | status, consent_type, granted, legal_basis, customer_cif, cbk_category, channel | granted_date DESC | DPO compliance; consent_type segments regulatory category; legal_basis (Consent/Contract/Legitimate Interest/Legal Obligation) drives reviewability |

Each gets the standard 8 CRUD verbs via `make_crud_router()`. All inherit JWT auth, audit logging, and PG/JSON fallback automatically.

The `searchable` whitelists are tuned to operational query patterns:
- compliance_cases: 6 columns covering triage (status, risk_level), taxonomy (flag_type, case_type), attribution (client_cif, assigned_officer)
- referrals: 7 columns covering channel attribution + workflow state
- consent_register: 7 columns covering compliance review + customer attribution

For `consent_register`, `legal_basis` searchability is the regulatory-audit-friendly pivot — a regulator asking "show me all customers under Consent legal basis" gets a one-call answer.

### 3. SCOPE_LEDGER.md Phase 1B section updated

Updated the table with v10.95 column showing 123/136. Removed the 3 v10.95 candidates from the "remaining" list. Updated forecast: **one more drop closes Phase 1B above the 136 target** with cushion.

---

## What v10.96 covers — Phase 1B close-out

Phase 1B closes. Targets in priority order from the 5 remaining CRUD-ready candidates:

1. **`staff_history`** (394 records) — HR movements; supports the staff-incentives + commission workflow
2. **`revenue_assurance`** (300 records) — revenue leakage tracking; revenue_assurance arc data (arc closed at G133+G134)
3. **`edms_documents`** (500 records) — document management; needed for compliance + legal arc workflows

That batch adds +24 endpoints → 147/136 (108%) — exceeds target with operational-priority cushion. Phase 1B is closed.

If Joshua prefers a tighter close (no cushion), only 2 modules can be wired in v10.96 → 139/136 (102%). Either path closes Phase 1B; the 3-module path provides more operational coverage.

After Phase 1B closes (v10.96), Phase 1C begins — test coverage push from ~45% → 80%. First action: baseline coverage measurement via `coverage.py`. Then targeted tests for under-tested modules. Phase 1C is a multi-drop arc; will likely take 5-10 drops to reach 80%.

After Phase 1 (1A + 1B + 1C) closes, Phase 2 begins — activating the 11 untouched planned subcategories. Recommended sequence: customer_360 first.

Phase 3 (the four deferred items per Joshua's directive) waits for Phase 1 + Phase 2 to close.

---

## Files changed

- **MOD** `utils/api.py` (3 new `make_crud_router()` calls after `cims_tickets`)
- **MOD** `SCOPE_LEDGER.md` (Phase 1B table + remaining candidates list updated; close forecast tightened)
- **NEW** `CHANGELOG_v10.95.md` (this file)

## Files NOT changed (deliberately)

- `utils/db.py` — no schema or TABLE_USE_DB changes
- `scripts/audit.py` — G16 still passes, G142 still locks the floor
- `scripts/audit_completion_state.py` — methodology from v10.92 still produces correct counts
- `scripts/migrate_to_postgres.py` — Phase 1A frozen
- `standards_registry.py` — no new standards
- `utils/api_crud.py` — factory unchanged; just consumed by 3 more module calls
- All closed-arc files — closure invariants preserved

## Honest acknowledgements

**Three drops in a row of "+3 modules / +24 endpoints" cadence.** v10.93, v10.94, v10.95 all delivered the same shape. That's the right outcome — the infrastructure (CRUD factory, TABLE_USE_DB synced, audit script methodology) is stable enough that execution drops are predictable. Phase 1B's structural work happened in v10.92-93; the rest is execution.

**The "+24 endpoints" isn't free progress.** Each `make_crud_router()` call gets 8 endpoints from the factory, but each call requires real configuration: schema-aware searchable column whitelist (must match actual table columns), order-by choice (must be a column the table indexes), pk_column (must match the schema's primary key, defaults to "id"). Those choices reflect operational understanding of the table — not just mechanical wiring.

**The factory's 8 endpoints aren't all equally useful for every module.** For `consent_register`, the `dashboard` endpoint returning generic module summary metrics may not capture what DPO operations actually want (e.g., consent breakdowns by purpose, expiring-soon alerts). Same caveat as v10.92's note: future enhancement could allow per-module dashboard customization. For now, the count of 8 is the audit-script-correct number; the count of "operationally tuned" endpoints might be 5-6 per module.

**The `consent_register` CRUD endpoints expose PII.** customer_cif, customer_name, purpose, channel, data_processor — all are fields a DPO would consider sensitive. JWT auth gates them, but there's no per-row access control beyond the JWT. For DPO compliance, more granular access (e.g., which consent records can a particular role see?) is likely needed in production. Holding off — JWT + audit logging is the platform's current security baseline; per-row RLS like aml_alerts has would be a future enhancement specifically for DPO-sensitive tables.

**`compliance_cases` doesn't have RLS the way `aml_alerts` does.** AML alerts are RLS-protected to Risk & Compliance + Internal Audit only. compliance_cases is similar in sensitivity (cases involve risk classification, flag types like "Adverse Media", "PEP Match", etc.) but doesn't currently have RLS. Worth flagging for future hardening — adding compliance_cases to the same RLS pattern as aml_alerts would be a 3-line schema change (`ALTER TABLE … ENABLE ROW LEVEL SECURITY` + a `CREATE POLICY` block + done). Not blocking the CRUD wiring; the JWT auth still gates access.

**No tests added.** Same as v10.94 — the `tests/test_api_crud.py` validates the factory pattern but doesn't test specific module wiring. Phase 1C will address this. With 13 wired CRUD modules now, there's enough surface area to write a parameterized test that validates basic CRUD operations against each module's real table. Phase 1C should make this its first deliverable.

**Phase 1B's close at v10.96 is mechanically achievable.** 3 more modules from the candidates list = 147 endpoints (108% of target). The decision is whether to ship 3 modules and exceed by 11, or 2 modules and exceed by 3. v10.95's recommendation is 3 — the marginal cost is one extra `app.include_router()` call, the marginal benefit is one more operational table covered.

---

**v10.95 ships under the anti-drift protocol.** API endpoints 99 → 123 (72.8% → 90.4% of 136 target). Phase 1A remains COMPLETE; Phase 1B IN PROGRESS, closing next drop. v10.96 wires the final 2-3 CRUD modules (staff_history, revenue_assurance, edms_documents) to close Phase 1B above target.
